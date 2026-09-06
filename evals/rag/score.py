"""Independently score strict raw RAG captures against the V1 acceptance gates."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import sys

from capture_schema import FullRetrievalHit, ScoreCapture, read_capture_jsonl
from validate import validate
from twinops.rag.operational import OperationalEvidence, TrustedOperationalContext
from twinops.rag.public_models import ManualCitation, TelemetryCitation
from twinops.rag.public_service import (
    DEFAULT_LIMITATIONS,
    OUT_OF_SCOPE_MESSAGES,
    _deterministic_current_state,
    _refusal_for,
)


_MANUAL_INSUFFICIENT = (
    "O manual ativo não contém evidência suficiente para responder "
    "a esta pergunta com segurança."
)


def _read_manifest(path: Path) -> list[dict]:
    errors = validate(path, require_complete=True)
    if errors:
        raise ValueError("; ".join(errors))
    return [
        json.loads(raw)
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]


def _index_exact(captures: list[ScoreCapture]) -> dict[str, ScoreCapture]:
    by_id = {capture.case_id: capture for capture in captures}
    if len(by_id) != len(captures):
        raise ValueError("capture case ids must be unique")
    return by_id


def _timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _trusted_context(capture: ScoreCapture) -> TrustedOperationalContext:
    snapshot = capture.operational_snapshot
    if snapshot is None:
        raise ValueError("retrieval flow requires an operational snapshot")
    return TrustedOperationalContext(
        operational_state=snapshot.operational_state,
        assessment_id=snapshot.assessment_id,
        assessment_status=snapshot.assessment_status,
        quality_status=snapshot.quality_status,
        window_start=_timestamp(snapshot.window_start),
        window_end=_timestamp(snapshot.window_end),
        received_at=_timestamp(snapshot.received_at),
        freshness_ms=snapshot.freshness_ms,
        evidence=tuple(
            OperationalEvidence(
                evidence_id=item.evidence_id,
                feature=item.feature,
                value=item.value,
                unit=item.unit,
                window_seconds=item.window_seconds,
            )
            for item in snapshot.evidence
        ),
        quality_flags=tuple(snapshot.quality_flags),
    )


def _anchor_matches_hit(anchor: dict, hit: FullRetrievalHit) -> bool:
    return (
        anchor["chunkId"] == hit.chunk_id
        and anchor["documentSha256"] == hit.document_sha256
        and anchor["pageStart"] == hit.page_start
        and anchor["pageEnd"] == hit.page_end
        and anchor["contentHash"] == hit.content_hash
        and anchor["exactQuote"] in hit.text
    )


def _validate_hit_identity(case: dict, hit: FullRetrievalHit, capture: ScoreCapture) -> None:
    corpus = capture.retrieval.corpus
    if (
        hit.manufacturer != corpus.manufacturer
        or hit.equipment_model != corpus.equipment_model
    ):
        raise ValueError("retrieval hit identity does not match corpus")
    if case["caseKind"] == "real_manual":
        identity = case["manualIdentity"]
        if (
            hit.manufacturer != identity["manufacturer"]
            or hit.equipment_model != identity["equipmentModel"]
            or hit.revision != identity["revision"]
            or hit.source_url != identity["sourceUrl"]
        ):
            raise ValueError("retrieval hit identity does not match manual")


def _validate_manual_citation(
    citation: ManualCitation,
    capture: ScoreCapture,
) -> FullRetrievalHit:
    if capture.retrieval is None:
        raise ValueError("preflight response cannot contain manual citations")
    hit = next(
        (item for item in capture.retrieval.hits if item.chunk_id == citation.chunk_id),
        None,
    )
    if hit is None or not (
        citation.document_id == hit.document_id
        and citation.manufacturer == hit.manufacturer
        and citation.equipment_model == hit.equipment_model
        and citation.revision == hit.revision
        and citation.source_url == hit.source_url
        and citation.page_start == hit.page_start
        and citation.page_end == hit.page_end
        and citation.section == hit.section
        and citation.content_hash == hit.content_hash
        and citation.excerpt in hit.text
        and hit.absolute_score >= capture.retrieval.corpus.min_relevance_score
    ):
        raise ValueError("manual citation is not a retrieved exact excerpt")
    return hit


def _validate_telemetry_citation(
    citation: TelemetryCitation,
    capture: ScoreCapture,
) -> None:
    snapshot = capture.operational_snapshot
    evidence = next(
        (item for item in snapshot.evidence if item.evidence_id == citation.evidence_id),
        None,
    )
    if evidence is None or not (
        citation.assessment_id == snapshot.assessment_id
        and citation.feature == evidence.feature
        and citation.value == evidence.value
        and citation.unit == evidence.unit
        and citation.window_start == snapshot.window_start
        and citation.window_end == snapshot.window_end
        and citation.received_at == snapshot.received_at
        and citation.freshness_ms == snapshot.freshness_ms
        and citation.window_seconds == evidence.window_seconds
        and citation.quality_status == snapshot.quality_status
    ):
        raise ValueError("telemetry citation does not match operational snapshot")


def _validate_answer_support(case: dict, capture: ScoreCapture) -> None:
    response = capture.response
    manual_citations = [
        item for item in response.citations if isinstance(item, ManualCitation)
    ]
    telemetry_citations = [
        item for item in response.citations if isinstance(item, TelemetryCitation)
    ]
    citation_keys = [
        (item.type, getattr(item, "chunk_id", None), getattr(item, "evidence_id", None))
        for item in response.citations
    ]
    if len(set(citation_keys)) != len(citation_keys):
        raise ValueError("response citations must be unique")
    cited_hits = [
        _validate_manual_citation(citation, capture) for citation in manual_citations
    ]
    for citation in telemetry_citations:
        _validate_telemetry_citation(citation, capture)

    if manual_citations:
        quotes = list(dict.fromkeys(item.excerpt for item in manual_citations))
        generated = "Segundo o manual:\n" + "\n".join(f"- {quote}" for quote in quotes)
        extractive = f"Trecho mais relevante recuperado do manual: {quotes[0]}"
        if response.answer.manual not in {generated, extractive}:
            raise ValueError("manual answer is not deterministic/extractive from citations")
    elif response.grounding_status == "manual_insufficient":
        if response.answer.manual != _MANUAL_INSUFFICIENT:
            raise ValueError("manual-insufficient text is not deterministic")
    elif response.grounding_status == "out_of_scope":
        reason = _refusal_for(case["question"])
        if reason is None or response.answer.manual != OUT_OF_SCOPE_MESSAGES[reason]:
            raise ValueError("out-of-scope refusal is not deterministic")
    elif response.grounding_status == "degraded_fallback":
        if response.answer.manual != "Não foi possível consultar o manual técnico neste momento.":
            raise ValueError("empty fallback text is not deterministic")
    else:
        raise ValueError("grounded answer requires a valid manual citation")

    expectation = case["manualExpectation"]
    if expectation == "supported":
        expected_ids = _expected_manual_ids(case)
        if not expected_ids.intersection(hit.chunk_id for hit in cited_hits):
            raise ValueError("answer does not cite expected manual evidence")
        if response.grounding_status not in {
            "grounded",
            "operational_unavailable",
            "degraded_fallback",
        }:
            raise ValueError("supported case has incorrect grounding")
    elif expectation == "absent":
        if response.grounding_status != "manual_insufficient" or manual_citations:
            raise ValueError("absent case was not refused as manual-insufficient")
    else:
        if response.grounding_status != "out_of_scope" or response.citations:
            raise ValueError("out-of-scope case was not refused without citations")

    if response.grounding_status == "out_of_scope":
        if telemetry_citations:
            raise ValueError("out-of-scope response must not cite operational data")
    elif capture.operational_snapshot.assessment_id is not None:
        if {item.evidence_id for item in telemetry_citations} != {
            item.evidence_id for item in capture.operational_snapshot.evidence
        }:
            raise ValueError("response omitted or invented operational evidence")

def _validate_case(case: dict, capture: ScoreCapture) -> None:
    if capture.question != case["question"]:
        raise ValueError("capture question does not match manifest")
    if capture.generation_model != capture.response.models.generation:
        raise ValueError("generation model does not match response")
    if capture.response.fallback_used != (
        capture.response.grounding_status == "degraded_fallback"
    ):
        raise ValueError("fallback flag does not match grounding")
    if capture.response.human_validation_required is not True:
        raise ValueError("response must require human validation")
    if capture.response.latency_ms != capture.latency_ms:
        raise ValueError("captured latency does not match public response")
    if capture.response.limitations != list(DEFAULT_LIMITATIONS):
        raise ValueError("response limitations are not canonical")

    if capture.flow_stage == "preflight_refusal":
        if capture.retrieval is not None or capture.operational_snapshot is not None:
            raise ValueError("preflight refusal must not invent retrieval or snapshot")
        if case["manualExpectation"] != "out_of_scope":
            raise ValueError("only out-of-scope cases may use preflight refusal")
        if (
            capture.response.grounding_status != "out_of_scope"
            or capture.response.corpus is not None
            or capture.response.models.embedding != "unavailable"
        ):
            raise ValueError("preflight refusal has unexpected grounding/corpus/model")
        unavailable = TrustedOperationalContext.unavailable(
            operational_state="unavailable"
        )
        if capture.response.answer.current_state != _deterministic_current_state(
            unavailable
        ):
            raise ValueError("preflight current state is not explicitly unavailable")
        _validate_answer_support(case, capture)
        return

    if capture.retrieval is None or capture.operational_snapshot is None:
        raise ValueError("retrieval flow requires retrieval and snapshot captures")
    corpus = capture.retrieval.corpus
    if corpus.min_relevance_score <= 0:
        raise ValueError("scored corpus is not calibrated")
    if capture.response.grounding_status == "out_of_scope":
        raise ValueError("out-of-scope response must use preflight capture")
    if capture.response.corpus != corpus:
        raise ValueError("response corpus does not match retrieval corpus")
    if capture.response.models.embedding != corpus.embedding_model:
        raise ValueError("embedding model does not match retrieval corpus")
    for hit in capture.retrieval.hits:
        _validate_hit_identity(case, hit, capture)

    context = _trusted_context(capture)
    if case.get("expectedOperationalState") is not None and (
        context.operational_state != case["expectedOperationalState"]
    ):
        raise ValueError("operational state does not match manifest")
    if capture.response.answer.current_state != _deterministic_current_state(context):
        raise ValueError("current-state answer is not server deterministic")
    _validate_answer_support(case, capture)


def _expected_manual_ids(case: dict) -> set[str]:
    evidence = case["expectedManualEvidence"]
    if case["caseKind"] == "synthetic_fixture":
        if not all(
            isinstance(anchor, str) and anchor.startswith("fixture:")
            for anchor in evidence
        ):
            raise ValueError("synthetic fixture evidence must use fixture anchors")
        return set(evidence)
    return {anchor["chunkId"] for anchor in evidence}


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def score(manifest_path: Path, captures_path: Path) -> dict[str, float]:
    cases = _read_manifest(manifest_path)
    captures = read_capture_jsonl(captures_path, ScoreCapture)
    by_id = _index_exact(captures)
    if set(by_id) != {case["id"] for case in cases}:
        raise ValueError("answer captures must match manifest cases exactly")

    expected_total = recalled = 0
    refusal_total = correct_refusals = 0
    for case in cases:
        capture = by_id[case["id"]]
        _validate_case(case, capture)
        if case["caseKind"] != "real_manual":
            continue
        if case["manualExpectation"] == "supported":
            if capture.retrieval is None:
                raise ValueError("supported case requires retrieval")
            threshold = capture.retrieval.corpus.min_relevance_score
            for anchor in case["expectedManualEvidence"]:
                expected_total += 1
                recalled += int(
                    any(
                        hit.absolute_score >= threshold
                        and _anchor_matches_hit(anchor, hit)
                        for hit in capture.retrieval.hits
                    )
                )
        else:
            refusal_total += 1
            if capture.flow_stage == "preflight_refusal":
                no_supported_hit = True
            else:
                if capture.retrieval is None:
                    raise ValueError("retrieval refusal requires retrieval capture")
                threshold = capture.retrieval.corpus.min_relevance_score
                no_supported_hit = not any(
                    hit.absolute_score >= threshold for hit in capture.retrieval.hits
                )
            correct_status = capture.response.grounding_status in {
                "manual_insufficient",
                "out_of_scope",
            }
            correct_refusals += int(no_supported_hit and correct_status)

    if expected_total == 0 or refusal_total == 0:
        raise ValueError("real-manual support and refusal cases are required")
    metrics = {
        "citation_validity": 1.0,
        "invented_evidence": 0.0,
        "invented_procedure": 0.0,
        "recall_at_6": recalled / expected_total,
        "refusal_accuracy": correct_refusals / refusal_total,
        "failure_probability_presentations": 0.0,
        "p95_latency_ms": _p95([capture.latency_ms for capture in captures]),
    }
    if not (
        metrics["recall_at_6"] >= 0.9
        and metrics["refusal_accuracy"] == 1.0
        and metrics["p95_latency_ms"] <= 12_000
    ):
        raise RuntimeError(json.dumps(metrics, sort_keys=True))
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("captures", type=Path)
    args = parser.parse_args(argv)
    try:
        metrics = score(args.manifest, args.captures)
    except Exception as exc:
        print(f"score_failed detail={exc}", file=sys.stderr)
        return 1
    print(
        "score_ok "
        f"citation_validity={metrics['citation_validity']:.3f} "
        f"invented_evidence={int(metrics['invented_evidence'])} "
        f"invented_procedure={int(metrics['invented_procedure'])} "
        f"recall_at_6={metrics['recall_at_6']:.3f} "
        f"refusal_accuracy={metrics['refusal_accuracy']:.3f} "
        f"failure_probability_presentations="
        f"{int(metrics['failure_probability_presentations'])} "
        f"p95_latency_ms={metrics['p95_latency_ms']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
