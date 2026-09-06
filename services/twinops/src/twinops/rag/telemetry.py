"""Closed-schema, content-free observability for the RAG request pipeline."""

import json
import logging
import math
import re


_LOGGER = logging.getLogger("twinops.rag")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}")
_SAFE_OUTCOME = re.compile(r"[a-z][a-z0-9_]{0,39}")
_STAGES = frozenset(
    {
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
    }
)


def log_rag_stage(
    stage: str,
    *,
    outcome: str,
    duration_ms: float | None = None,
    remaining_budget_ms: float | None = None,
    asset_id: str | None = None,
    corpus_id: str | None = None,
    model: str | None = None,
    count: int | None = None,
    http_status: int | None = None,
    trace_id: str | None = None,
) -> None:
    """Emit one JSON event whose call signature cannot accept user content."""

    if stage not in _STAGES:
        raise ValueError("unknown RAG stage")
    if not isinstance(outcome, str) or _SAFE_OUTCOME.fullmatch(outcome) is None:
        raise ValueError("RAG stage outcome is invalid")

    payload: dict[str, object] = {
        "event": "rag_stage",
        "stage": stage,
        "outcome": outcome,
    }
    for key, value in (
        ("assetId", asset_id),
        ("corpusId", corpus_id),
        ("model", model),
        ("traceId", trace_id),
    ):
        if value is not None:
            payload[key] = _validated_identifier(value)
    if duration_ms is not None:
        payload["durationMs"] = _validated_duration(duration_ms)
    if remaining_budget_ms is not None:
        payload["remainingBudgetMs"] = _validated_duration(
            remaining_budget_ms
        )
    if count is not None:
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("RAG stage count is invalid")
        payload["count"] = count
    if http_status is not None:
        if (
            not isinstance(http_status, int)
            or isinstance(http_status, bool)
            or not 100 <= http_status <= 599
        ):
            raise ValueError("RAG stage HTTP status is invalid")
        payload["httpStatus"] = http_status

    level = logging.INFO if outcome in {"ok", "grounded"} else logging.WARNING
    _LOGGER.log(
        level,
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _validated_identifier(value: str) -> str:
    if not isinstance(value, str) or _SAFE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError("RAG stage requires a safe identifier")
    return value


def _validated_duration(value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError("RAG stage duration is invalid")
    return round(numeric, 3)
