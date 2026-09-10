"""Explicit, paid native Gemini smoke; outputs sanitized invocation proof only.

Run from the repository root with PYTHONPATH=services/twinops/src. Reads the
authorized local .env.local without logging credentials or provider bodies.
All operational evidence in this probe is a labeled synthetic fixture.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx

from twinops.rag.generation import (
    ChatGatewayError,
    GeminiChatClient,
    build_gateway_messages,
    validate_generated_payload,
)


def local_environment(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    values.update(os.environ)
    return values


async def run(*, history_tool: bool, timeout: float, model_override: str | None = None) -> int:
    values = local_environment(Path(".env.local"))
    api_key = values.get("GEMINI_API_KEY", "")
    model = model_override or values.get("TWINOPS_RAG_GENERATION_MODEL", "gemini-3.5-flash-lite")
    if not api_key:
        print(json.dumps({"status": "not_called", "reason": "missing_api_key"}))
        return 2
    origin = {"datasetId": "synthetic-provider-smoke", "observedAt": "2026-09-10T12:00:00Z", "sourceRow": 5}
    initial = {
        "mode": "synthetic_test", "assetId": "provider-smoke", "revision": "fixture-1",
        "origin": origin, "sensors": {
            "s1": {"component": "motor", "latest": {"velocityRms": 0.04, "unit": "mm/s"},
                   "assessment": {"status": "insufficient_data"}},
            "s2": {"component": "pump", "latest": {"velocityRms": 0.03, "unit": "mm/s"},
                   "assessment": {"status": "insufficient_data"}},
        },
    }
    rows = [{"sensorId": "s2", "observedAt": "2026-09-10T11:59:59Z", "sourceRow": 4,
             "measurements": {"velocityRms": 0.03}, "qualityFlags": [], "gapBefore": False}]
    operational = SimpleNamespace(
        to_prompt_context=lambda: initial,
        analysis_context={"historyRows": rows if history_tool else []},
    )
    question = (
        "Consulte read_operational_history para S2 com limite 5 e informe a linha de origem anterior disponível; "
        "explique por que não é possível confirmar uma tendência."
        if history_tool else
        "Compare as velocidades atuais de S1 e S2 e explique a limitação do ML disponível."
    )
    try:
        async with httpx.AsyncClient() as http:
            client = GeminiChatClient(http, api_key=api_key, model=model, timeout_seconds=timeout)
            result = await client.generate(build_gateway_messages(
                question=question, history=(), operational=operational,
            ))
            validate_generated_payload(result)
        proof = {**result.generation_metadata,
                 "syntheticFixture": True, "narrativeCharacters": len(result.current_state),
                 "citations": len(result.manual_citations)}
        if history_tool and not result.generation_metadata.get("toolCalls"):
            proof["toolProof"] = "not_requested_by_model"
        print(json.dumps(proof))
        return 0
    except ChatGatewayError as error:
        print(json.dumps({**error.generation_metadata, "reason": error.reason,
                          "httpStatus": error.status_code}))
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-tool", action="store_true")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--model", help="Explicit native Gemini model for comparison")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(history_tool=args.history_tool, timeout=args.timeout,
                                    model_override=args.model)))
