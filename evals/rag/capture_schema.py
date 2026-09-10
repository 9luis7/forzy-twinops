"""Strict raw capture contracts shared by offline RAG evaluation tools."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_PROJECT_SRC = Path(__file__).resolve().parents[2] / "services" / "twinops" / "src"
if str(_PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(_PROJECT_SRC))

from twinops.rag.public_models import AssistantQueryResponse, CorpusAnchor


class _CaptureModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=False,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class RankedHit(_CaptureModel):
    chunk_id: str = Field(alias="chunkId", min_length=1)
    absolute_score: float = Field(alias="absoluteScore", ge=0, le=1)
    rank_score: float = Field(alias="rankScore", ge=0, le=1)
    vector_rank: int | None = Field(alias="vectorRank", ge=1, le=12)
    lexical_rank: int | None = Field(alias="lexicalRank", ge=1, le=12)

    @model_validator(mode="after")
    def require_a_source_rank(self):
        if self.vector_rank is None and self.lexical_rank is None:
            raise ValueError("retrieval hit requires at least one source rank")
        return self


def _validate_ordered_hits(hits: list[RankedHit]) -> list[RankedHit]:
    chunk_ids = [hit.chunk_id for hit in hits]
    if len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("retrieval chunk ids must be unique")
    if hits != sorted(hits, key=lambda hit: (-hit.rank_score, hit.chunk_id)):
        raise ValueError("retrieval hits must retain deterministic fused order")
    for attribute in ("vector_rank", "lexical_rank"):
        ranks = [getattr(hit, attribute) for hit in hits if getattr(hit, attribute) is not None]
        if len(set(ranks)) != len(ranks):
            raise ValueError(f"{attribute} values must be unique")
    return hits


class CalibrationCapture(_CaptureModel):
    case_id: str = Field(alias="caseId", min_length=1)
    question: str = Field(min_length=1, max_length=500)
    hits: list[RankedHit] = Field(max_length=6)

    @model_validator(mode="after")
    def validate_hits(self):
        _validate_ordered_hits(self.hits)
        return self


class FullRetrievalHit(RankedHit):
    document_id: str = Field(alias="documentId", min_length=1)
    manufacturer: str = Field(min_length=1)
    equipment_model: str = Field(alias="equipmentModel", min_length=1)
    revision: str = Field(min_length=1)
    source_url: str = Field(alias="sourceUrl", pattern=r"^https://")
    document_sha256: str = Field(
        alias="documentSha256", pattern=r"^[0-9a-f]{64}$"
    )
    page_start: int = Field(alias="pageStart", ge=1)
    page_end: int = Field(alias="pageEnd", ge=1)
    section: str | None
    text: str = Field(min_length=1)
    content_hash: str = Field(alias="contentHash", pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_pages(self):
        if self.page_end < self.page_start:
            raise ValueError("retrieval hit page range is invalid")
        return self


class RetrievalCapture(_CaptureModel):
    corpus: CorpusAnchor
    hits: list[FullRetrievalHit] = Field(max_length=6)

    @model_validator(mode="after")
    def validate_hits(self):
        _validate_ordered_hits(self.hits)
        return self


class OperationalEvidenceCapture(_CaptureModel):
    evidence_id: str = Field(alias="evidenceId", min_length=1)
    feature: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    window_seconds: float | None = Field(alias="windowSeconds", default=None, ge=0)


class OperationalSnapshotCapture(_CaptureModel):
    operational_state: str = Field(alias="operationalState", min_length=1)
    assessment_id: str | None = Field(alias="assessmentId", default=None)
    assessment_status: str | None = Field(alias="assessmentStatus", default=None)
    quality_status: str | None = Field(alias="qualityStatus", default=None)
    window_start: str | None = Field(alias="windowStart", default=None)
    window_end: str | None = Field(alias="windowEnd", default=None)
    received_at: str | None = Field(alias="receivedAt", default=None)
    freshness_ms: float | None = Field(alias="freshnessMs", default=None, ge=0)
    quality_flags: list[str] = Field(alias="qualityFlags", max_length=100)
    evidence: list[OperationalEvidenceCapture] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_availability(self):
        anchors = (
            self.assessment_id,
            self.assessment_status,
            self.quality_status,
            self.window_start,
            self.window_end,
            self.received_at,
            self.freshness_ms,
        )
        if self.assessment_id is None:
            if any(value is not None for value in anchors) or self.evidence:
                raise ValueError("unavailable snapshot must not contain assessment evidence")
        elif any(value is None for value in anchors):
            raise ValueError("available snapshot requires complete assessment anchors")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("operational evidence ids must be unique")
        return self


class ScoreCapture(_CaptureModel):
    capture_protocol: Literal["legacy-extractive-v1", "generative-service-fixture-v2"] = Field(
        default="legacy-extractive-v1", alias="captureProtocol",
    )
    case_id: str = Field(alias="caseId", min_length=1)
    question: str = Field(min_length=1, max_length=500)
    flow_stage: Literal["retrieval", "preflight_refusal"] = Field(alias="flowStage")
    retrieval: RetrievalCapture | None
    generation_model: str = Field(alias="generationModel", min_length=1)
    operational_snapshot: OperationalSnapshotCapture | None = Field(
        alias="operationalSnapshot"
    )
    response: AssistantQueryResponse
    latency_ms: float = Field(alias="latencyMs", ge=0)

    @model_validator(mode="after")
    def validate_flow_stage(self):
        if self.flow_stage == "preflight_refusal":
            if self.retrieval is not None or self.operational_snapshot is not None:
                raise ValueError(
                    "preflight refusal must not contain retrieval or snapshot"
                )
        elif self.retrieval is None or self.operational_snapshot is None:
            raise ValueError("retrieval flow requires retrieval and snapshot")
        return self


CaptureT = TypeVar("CaptureT", bound=_CaptureModel)


def read_capture_jsonl(path: Path, model: type[CaptureT]) -> list[CaptureT]:
    rows: list[CaptureT] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
            rows.append(model.model_validate(value))
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise ValueError(f"capture line {number} is invalid") from exc
    return rows
