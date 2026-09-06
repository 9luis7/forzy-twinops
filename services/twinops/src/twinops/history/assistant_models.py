"""Bounded historical requests and provenance distinct from live telemetry."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from twinops.rag.public_models import AssistantQueryRequest, AssistantQueryResponse


class HistoricalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, allow_inf_nan=False)


class HistoricalSelection(HistoricalModel):
    from_time: str | None = Field(default=None, alias="from", max_length=64, strict=True)
    to_time: str | None = Field(default=None, alias="to", max_length=64, strict=True)
    end_row: int = Field(alias="endRow", ge=1, strict=True)
    limit: int = Field(ge=1, le=300, strict=True)


class HistoricalQueryRequest(AssistantQueryRequest):
    selection: HistoricalSelection
    context_revision: str = Field(alias="contextRevision", pattern=r"^[0-9a-f]{64}$", strict=True)


class HistoricalContextSelection(HistoricalSelection):
    observed_at: str = Field(alias="observedAt")
    total_pairs: int = Field(alias="totalPairs", ge=1)
    returned_pairs: int = Field(alias="returnedPairs", ge=1, le=300)
    has_previous: bool = Field(alias="hasPrevious")
    previous_end_row: int | None = Field(alias="previousEndRow")
    has_next: bool = Field(alias="hasNext")
    next_end_row: int | None = Field(alias="nextEndRow")


class HistoricalFeature(HistoricalModel):
    id: str
    feature: str
    value: float
    unit: str
    window_seconds: float | None = Field(default=None, alias="windowSeconds", ge=0)


class HistoricalSensorEvidence(HistoricalModel):
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    component: Literal["motor", "bomba"]
    position_assumed: Literal[True] = Field(default=True, alias="positionAssumed")
    observed_at: str = Field(alias="observedAt")
    source_row: int = Field(alias="sourceRow", ge=1)
    assessment_id: str | None = Field(alias="assessmentId")
    status: str
    quality_status: str = Field(alias="qualityStatus")
    quality_flags: list[str] = Field(alias="qualityFlags")
    window_start: str | None = Field(alias="windowStart")
    window_end: str | None = Field(alias="windowEnd")
    trained_until: str | None = Field(alias="trainedUntil")
    score_semantics: str | None = Field(alias="scoreSemantics")
    evidence: list[HistoricalFeature]


class HistoricalQueryResponse(HistoricalModel):
    schema_version: Literal["historical-assistant-1.0"] = Field(default="historical-assistant-1.0", alias="schemaVersion")
    context_revision: str = Field(alias="contextRevision", pattern=r"^[0-9a-f]{64}$")
    dataset_id: str = Field(alias="datasetId")
    selection: HistoricalContextSelection
    response: AssistantQueryResponse
    historical_evidence: list[HistoricalSensorEvidence] = Field(alias="historicalEvidence", min_length=2, max_length=2)
