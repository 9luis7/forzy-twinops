import json

import pytest

from twinops.rag.telemetry import log_rag_stage


def test_stage_event_has_a_closed_sanitized_schema(caplog):
    caplog.set_level("INFO", logger="twinops.rag")

    log_rag_stage(
        "query_embedding",
        outcome="ok",
        duration_ms=12.5,
        remaining_budget_ms=8450.0,
        asset_id="forzy-motor-01",
        corpus_id="00000000-0000-4000-8000-000000000001",
        model="gemini-embedding-2",
        count=1,
        http_status=200,
        trace_id="00000000-0000-4000-8000-000000000002",
    )

    payload = json.loads(caplog.records[-1].message)
    assert payload == {
        "assetId": "forzy-motor-01",
        "corpusId": "00000000-0000-4000-8000-000000000001",
        "count": 1,
        "durationMs": 12.5,
        "event": "rag_stage",
        "httpStatus": 200,
        "model": "gemini-embedding-2",
        "outcome": "ok",
        "remainingBudgetMs": 8450.0,
        "stage": "query_embedding",
        "traceId": "00000000-0000-4000-8000-000000000002",
    }


def test_stage_logger_rejects_untrusted_fields_and_log_injection(caplog):
    caplog.set_level("DEBUG", logger="twinops.rag")
    secret = "private-manual-chunk-never-log"

    with pytest.raises(TypeError):
        log_rag_stage("total", outcome="ok", question=secret)
    with pytest.raises(ValueError, match="safe identifier"):
        log_rag_stage(
            "total",
            outcome="ok",
            asset_id=f"forzy-motor-01\n{secret}",
        )

    assert secret not in caplog.text


@pytest.mark.parametrize(
    "stage",
    [
        "corpus_lookup",
        "snapshot",
        "query_embedding",
        "vector_search",
        "lexical_search",
        "fusion",
        "prompt_assembly",
        "generation",
        "validation",
        "remaining_budget",
        "total",
    ],
)
def test_contract_accepts_every_required_stage(stage, caplog):
    caplog.set_level("INFO", logger="twinops.rag")

    log_rag_stage(stage, outcome="ok", duration_ms=0.0)

    assert json.loads(caplog.records[-1].message)["stage"] == stage
