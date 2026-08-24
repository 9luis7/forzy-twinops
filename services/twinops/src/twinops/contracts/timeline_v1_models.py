"""Strict, canonical public contracts for the immutable TwinOps timeline."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urldefrag, urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from jsonschema import Draft7Validator
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    model_validator,
)
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

from twinops.contracts.v2_models import AssetConditionAssessmentV2, MeasurementsV2

PUBLIC_UTC_MILLIS_RE = re.compile(
    r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r"T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d\.\d{3}Z$"
)
_UUID_V5_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ROOT = Path(__file__).resolve().parents[5]
_SCHEMA_DIR = _ROOT / "contracts" / "timeline" / "v1"
_TIMELINE_SCHEMA_PREFIX = "forzy://contracts/timeline/v1/"
_SCHEMA_NAMES = (
    "historical-sensor-reading",
    "timeline-point",
    "historical-assessment",
    "collection-policy",
    "timeline-event-candidate",
    "timeline-overview",
    "timeline-page",
    "timeline-decision-facts",
    "timeline-context",
)

NonEmptyStringV1 = Annotated[str, Field(min_length=1)]


class TimelineRangeOverflow(ValueError):
    """Raised when no exclusive public-millisecond upper bound exists."""


def parse_uuid_json_v1(value: object) -> UUID:
    if isinstance(value, UUID):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = UUID(value)
        except ValueError as exc:
            raise ValueError("expected a canonical UUID string") from exc
    else:
        raise ValueError("expected a canonical UUID string")
    if str(parsed) != str(value):
        raise ValueError("expected a canonical lowercase UUID string")
    return parsed


def _parse_uuid5_json_v1(value: object) -> UUID:
    parsed = parse_uuid_json_v1(value)
    if not _UUID_V5_RE.fullmatch(str(parsed)):
        raise ValueError("expected a canonical UUIDv5 string")
    return parsed


def parse_public_utc_millis_v1(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and PUBLIC_UTC_MILLIS_RE.fullmatch(value):
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise ValueError("timeline_invalid_public_millisecond") from exc
    else:
        raise ValueError("timeline_invalid_public_millisecond")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("timeline_invalid_public_millisecond")
    parsed = parsed.astimezone(timezone.utc)
    if parsed.year < 1 or parsed.microsecond % 1_000:
        raise ValueError("timeline_invalid_public_millisecond")
    return parsed


def serialize_public_utc_millis_v1(value: datetime) -> str:
    parsed = parse_public_utc_millis_v1(value)
    return f"{parsed:%Y-%m-%dT%H:%M:%S}.{parsed.microsecond // 1_000:03d}Z"


def _parse_sha256_v1(value: object) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError("expected sha256:<64 lowercase hex>")
    return value


Sha256V1 = Annotated[str, BeforeValidator(_parse_sha256_v1)]
UuidV1 = Annotated[
    UUID,
    BeforeValidator(parse_uuid_json_v1),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
]
Uuid5V1 = Annotated[
    UUID,
    BeforeValidator(_parse_uuid5_json_v1),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
]
UtcTimestampV1 = Annotated[
    datetime,
    BeforeValidator(parse_public_utc_millis_v1),
    PlainSerializer(serialize_public_utc_millis_v1, return_type=str, when_used="json"),
]
TimelineMeasurementsV1 = MeasurementsV2
TimelineSourceKindV1 = Literal["historical_archive", "live_collection"]
TimelineTimestampQualityV1 = Literal[
    "source_without_offset_assumed_timezone", "assumed_from_retrieval"
]
TimelineGapTypeV1 = Literal[
    "source_discontinuity",
    "archive_sampling_gap",
    "live_expected_collection_gap",
    "expected_idle",
    "unclassified_coverage_gap",
]
TimelineGapMessageCodeV1 = Literal[
    "timeline_gap_source_discontinuity",
    "timeline_gap_archive_sampling",
    "timeline_gap_live_expected_collection",
    "timeline_gap_expected_idle",
    "timeline_gap_unclassified_coverage",
]


class ContractModelTimelineV1(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        allow_inf_nan=False,
        populate_by_name=False,
    )

    @model_validator(mode="before")
    @classmethod
    def public_aliases_only(cls, value: object) -> object:
        def reject_internal_keys(node: object) -> None:
            if isinstance(node, list):
                for child in node:
                    reject_internal_keys(child)
            elif isinstance(node, dict):
                for key, child in node.items():
                    if not isinstance(key, str) or "_" in key:
                        raise ValueError("public timeline JSON accepts alias keys only")
                    reject_internal_keys(child)

        if isinstance(value, dict):
            reject_internal_keys(value)
        return value

    def model_dump_public(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=False)

    def model_dump_public_json(self) -> str:
        return self.model_dump_json(by_alias=True, exclude_none=False)


class HistoricalProvenanceV1(ContractModelTimelineV1):
    source_system: Literal["forzy-csv"] = Field(alias="sourceSystem")
    batch_id: Sha256V1 = Field(alias="batchId")
    source_file_sha256: Sha256V1 = Field(alias="sourceFileSha256")
    record_ordinal: int = Field(alias="recordOrdinal", ge=1)
    source_line_number: int = Field(alias="sourceLineNumber", ge=4)
    row_sha256: Sha256V1 = Field(alias="rowSha256")
    ingested_at: UtcTimestampV1 = Field(alias="ingestedAt")


class LiveTimelineProvenanceV1(ContractModelTimelineV1):
    source_system: Literal["forzy-api"] = Field(alias="sourceSystem")
    reading_id: Uuid5V1 = Field(alias="readingId")
    scheduled_at: UtcTimestampV1 = Field(alias="scheduledAt")
    received_at: UtcTimestampV1 = Field(alias="receivedAt")
    collection_policy_id: NonEmptyStringV1 | None = Field(alias="collectionPolicyId")


class TimelineQualityV1(ContractModelTimelineV1):
    status: Literal["ok", "degraded", "insufficient_data"]
    flags: list[NonEmptyStringV1]


class TimelineClosedRangeV1(ContractModelTimelineV1):
    start: UtcTimestampV1
    end: UtcTimestampV1


class HistoricalAssessmentPersistenceV1(ContractModelTimelineV1):
    episode_id: NonEmptyStringV1 | None = Field(alias="episodeId")
    episode_started_at: UtcTimestampV1 | None = Field(alias="episodeStartedAt")
    persistence_seconds: float = Field(alias="persistenceSeconds", ge=0)
    persistence_count: int = Field(alias="persistenceCount", ge=0)


class HistoricalAssessmentEvidenceV1(ContractModelTimelineV1):
    id: NonEmptyStringV1
    feature: NonEmptyStringV1
    value: float
    unit: NonEmptyStringV1
    baseline: float | None
    deviation: float | None
    direction: Literal["up", "down", "stable", "unknown"] | None
    window_seconds: float | None = Field(alias="windowSeconds", ge=0)


class TimelineRequestedRangeV1(ContractModelTimelineV1):
    from_: UtcTimestampV1 | None = Field(alias="from")
    to: UtcTimestampV1 | None


class TimelineHalfOpenRangeV1(ContractModelTimelineV1):
    from_: UtcTimestampV1 = Field(alias="from")
    to: UtcTimestampV1


class TimelineSensorCountsV1(ContractModelTimelineV1):
    s1: int = Field(ge=0)
    s2: int = Field(ge=0)


class TimelineAggregationSummaryV1(ContractModelTimelineV1):
    requested_max_points: int = Field(alias="requestedMaxPoints", ge=40, le=4000)
    original_point_count: int = Field(alias="originalPointCount", ge=0)
    returned_point_count: int = Field(alias="returnedPointCount", ge=0)
    omitted_point_count: int = Field(alias="omittedPointCount", ge=0)
    reduced_series_count: int = Field(alias="reducedSeriesCount", ge=0)


class TimelineOperatingCycleV1(ContractModelTimelineV1):
    operating_cycle_id: Uuid5V1 = Field(alias="operatingCycleId")
    source_kind: Literal["historical_archive"] = Field(alias="sourceKind")
    batch_id: Sha256V1 = Field(alias="batchId")
    start_at: UtcTimestampV1 = Field(alias="startAt")
    end_at: UtcTimestampV1 = Field(alias="endAt")
    duration_seconds: float = Field(alias="durationSeconds", ge=0)
    total_points: int = Field(alias="totalPoints", ge=1)
    sensor_counts: TimelineSensorCountsV1 = Field(alias="sensorCounts")
    candidate_count: int = Field(alias="candidateCount", ge=0)
    gap_before_seconds: float | None = Field(alias="gapBeforeSeconds", ge=0)
    previous_operating_cycle_id: Uuid5V1 | None = Field(
        alias="previousOperatingCycleId"
    )
    assumptions: list[NonEmptyStringV1]


class TimelineSegmentV1(ContractModelTimelineV1):
    segment_id: Uuid5V1 = Field(alias="segmentId")
    source_kind: TimelineSourceKindV1 = Field(alias="sourceKind")
    start_at: UtcTimestampV1 = Field(alias="startAt")
    end_at: UtcTimestampV1 = Field(alias="endAt")
    total_points: int = Field(alias="totalPoints", ge=1)
    sensor_counts: TimelineSensorCountsV1 = Field(alias="sensorCounts")
    timestamp_quality: TimelineTimestampQualityV1 = Field(alias="timestampQuality")
    batch_id: Sha256V1 | None = Field(alias="batchId")
    collection_policy_id: NonEmptyStringV1 | None = Field(alias="collectionPolicyId")
    assumptions: list[NonEmptyStringV1]


class TimelineGapV1(ContractModelTimelineV1):
    gap_id: Uuid5V1 = Field(alias="gapId")
    left_segment_id: Uuid5V1 | None = Field(alias="leftSegmentId")
    right_segment_id: Uuid5V1 | None = Field(alias="rightSegmentId")
    start_at: UtcTimestampV1 = Field(alias="startAt")
    end_at: UtcTimestampV1 = Field(alias="endAt")
    gap_type: TimelineGapTypeV1 = Field(alias="gapType")
    duration_seconds: float = Field(alias="durationSeconds", gt=0)
    rule_version: Literal["timeline-gap-v1"] = Field(alias="ruleVersion")
    message_code: TimelineGapMessageCodeV1 = Field(alias="messageCode")


class TimelineSeriesPointV1(ContractModelTimelineV1):
    point_id: Uuid5V1 = Field(alias="pointId")
    event_at: UtcTimestampV1 = Field(alias="eventAt")
    value: float


class TimelineSeriesAggregationV1(ContractModelTimelineV1):
    method: Literal["none", "time_bucket_envelope_v1"]
    requested_max_points: int = Field(alias="requestedMaxPoints", ge=40, le=4000)
    original_point_count: int = Field(alias="originalPointCount", ge=0)
    returned_point_count: int = Field(alias="returnedPointCount", ge=0)
    omitted_point_count: int = Field(alias="omittedPointCount", ge=0)


class TimelineSeriesV1(ContractModelTimelineV1):
    segment_id: Uuid5V1 = Field(alias="segmentId")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    source_kind: TimelineSourceKindV1 = Field(alias="sourceKind")
    metric: Literal[
        "vibrationVelocityRms", "vibrationAcceleration", "temperature"
    ]
    points: list[TimelineSeriesPointV1]
    aggregation: TimelineSeriesAggregationV1


class TimelineOverviewCapabilitiesV1(ContractModelTimelineV1):
    historical: bool
    live: bool


class HistoricalSensorReadingV1(ContractModelTimelineV1):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    reading_id: Uuid5V1 = Field(alias="readingId")
    sample_pair_id: Uuid5V1 = Field(alias="samplePairId")
    operating_cycle_id: Uuid5V1 = Field(alias="operatingCycleId")
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    event_at: UtcTimestampV1 = Field(alias="eventAt")
    source_timestamp_text: NonEmptyStringV1 = Field(alias="sourceTimestampText")
    source_kind: Literal["historical_archive"] = Field(alias="sourceKind")
    timestamp_quality: Literal["source_without_offset_assumed_timezone"] = Field(
        alias="timestampQuality"
    )
    measurements: TimelineMeasurementsV1
    quality_flags: list[NonEmptyStringV1] = Field(alias="qualityFlags")
    provenance: HistoricalProvenanceV1

    @model_validator(mode="after")
    def invariants(self) -> Self:
        assert_timeline_invariants_v1(
            self.model_dump_public(), "historical-sensor-reading"
        )
        return self


class TimelinePointV1(ContractModelTimelineV1):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    point_id: Uuid5V1 = Field(alias="pointId")
    sample_pair_id: Uuid5V1 = Field(alias="samplePairId")
    operating_cycle_id: Uuid5V1 | None = Field(alias="operatingCycleId")
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    event_at: UtcTimestampV1 = Field(alias="eventAt")
    source_kind: TimelineSourceKindV1 = Field(alias="sourceKind")
    timestamp_quality: TimelineTimestampQualityV1 = Field(alias="timestampQuality")
    measurements: TimelineMeasurementsV1
    quality_flags: list[NonEmptyStringV1] = Field(alias="qualityFlags")
    provenance: HistoricalProvenanceV1 | LiveTimelineProvenanceV1

    @model_validator(mode="after")
    def invariants(self) -> Self:
        assert_timeline_invariants_v1(self.model_dump_public(), "timeline-point")
        return self


class HistoricalAssessmentV1(ContractModelTimelineV1):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    assessment_id: Uuid5V1 = Field(alias="assessmentId")
    fold_id: NonEmptyStringV1 = Field(alias="foldId")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    operating_cycle_id: Uuid5V1 = Field(alias="operatingCycleId")
    training_window: TimelineClosedRangeV1 = Field(alias="trainingWindow")
    assessment_window: TimelineClosedRangeV1 = Field(alias="assessmentWindow")
    assessment_at: UtcTimestampV1 = Field(alias="assessmentAt")
    anchor_point_id: Uuid5V1 = Field(alias="anchorPointId")
    status: Literal["normal", "watch", "alert", "insufficient_data"]
    anomaly_score: float | None = Field(alias="anomalyScore")
    deterioration_score: float | None = Field(alias="deteriorationScore")
    score_semantics: Literal[
        "relative_to_walk_forward_historical_baseline_not_failure_probability"
    ] = Field(alias="scoreSemantics")
    persistence: HistoricalAssessmentPersistenceV1
    quality: TimelineQualityV1
    evidence: list[HistoricalAssessmentEvidenceV1]
    model_family: NonEmptyStringV1 = Field(alias="modelFamily")
    model_version: NonEmptyStringV1 = Field(alias="modelVersion")
    model_hash: Sha256V1 = Field(alias="modelHash")
    fold_hash: Sha256V1 = Field(alias="foldHash")
    report_hash: Sha256V1 = Field(alias="reportHash")
    component_tag: None = Field(alias="componentTag")
    human_validation_required: Literal[True] = Field(alias="humanValidationRequired")
    limitations: list[NonEmptyStringV1]

    @model_validator(mode="after")
    def invariants(self) -> Self:
        assert_timeline_invariants_v1(
            self.model_dump_public(), "historical-assessment"
        )
        return self


class CollectionPolicyV1(ContractModelTimelineV1):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    collection_policy_id: NonEmptyStringV1 = Field(alias="collectionPolicyId")
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    timezone: Literal["America/Sao_Paulo"]
    active_weekdays: list[Literal["monday", "tuesday", "wednesday"]] = Field(
        alias="activeWeekdays"
    )
    window_start_local: Literal["12:00:00"] = Field(alias="windowStartLocal")
    window_end_local: Literal["14:00:00"] = Field(alias="windowEndLocal")
    poll_interval_seconds: Literal[5] = Field(alias="pollIntervalSeconds")
    gap_threshold_seconds: Literal[15] = Field(alias="gapThresholdSeconds")
    effective_from: UtcTimestampV1 = Field(alias="effectiveFrom")
    effective_to: UtcTimestampV1 | None = Field(alias="effectiveTo")
    configuration_hash: Sha256V1 = Field(alias="configurationHash")

    @model_validator(mode="after")
    def invariants(self) -> Self:
        assert_timeline_invariants_v1(self.model_dump_public(), "collection-policy")
        return self


class TimelineEventCandidateV1(ContractModelTimelineV1):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    candidate_id: Uuid5V1 = Field(alias="candidateId")
    anchor_point_id: Uuid5V1 = Field(alias="anchorPointId")
    operating_cycle_id: Uuid5V1 | None = Field(alias="operatingCycleId")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    event_at: UtcTimestampV1 = Field(alias="eventAt")
    source_kind: TimelineSourceKindV1 = Field(alias="sourceKind")
    status: Literal["watch", "alert"]
    persistence_count: int = Field(alias="persistenceCount", ge=1)
    episode_started_at: UtcTimestampV1 = Field(alias="episodeStartedAt")
    data_trust: Literal["sufficient", "degraded", "insufficient"] = Field(
        alias="dataTrust"
    )
    quality: TimelineQualityV1
    batch_id: Sha256V1 | None = Field(alias="batchId")
    model_family: NonEmptyStringV1 = Field(alias="modelFamily")
    model_version: NonEmptyStringV1 = Field(alias="modelVersion")
    fold_id: NonEmptyStringV1 | None = Field(alias="foldId")
    candidate_ranking_version: Literal["forzy-review-priority-v1"] = Field(
        alias="candidateRankingVersion"
    )

    @model_validator(mode="after")
    def invariants(self) -> Self:
        assert_timeline_invariants_v1(
            self.model_dump_public(), "timeline-event-candidate"
        )
        return self


class TimelineDecisionFactsV1(ContractModelTimelineV1):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    condition_state: Literal[
        "normal", "watch", "alert", "insufficient_data", "unknown"
    ] = Field(alias="conditionState")
    condition_temporal_scope: Literal[
        "current", "last_known", "historical", "none"
    ] = Field(alias="conditionTemporalScope")
    condition_as_of: UtcTimestampV1 | None = Field(alias="conditionAsOf")
    condition_episode_started_at: UtcTimestampV1 | None = Field(
        alias="conditionEpisodeStartedAt"
    )
    condition_source: Literal[
        "live_assessment", "historical_walk_forward", "none"
    ] = Field(alias="conditionSource")
    collection_state: Literal[
        "received_now",
        "last_known",
        "expected_idle",
        "unavailable",
        "historical_context",
        "historical_gap",
    ] = Field(alias="collectionState")
    collection_expectation: Literal[
        "expected_now", "expected_idle", "not_applicable"
    ] = Field(alias="collectionExpectation")
    data_availability: Literal["complete", "partial", "gap", "unavailable"] = Field(
        alias="dataAvailability"
    )
    data_freshness: Literal["fresh", "stale", "historical", "unknown"] = Field(
        alias="dataFreshness"
    )
    data_trust: Literal["sufficient", "degraded", "insufficient"] = Field(
        alias="dataTrust"
    )

    @model_validator(mode="after")
    def invariants(self) -> Self:
        assert_timeline_invariants_v1(
            self.model_dump_public(), "timeline-decision-facts"
        )
        return self


class TimelineContextChannelsV1(ContractModelTimelineV1):
    s1: TimelinePointV1 | None
    s2: TimelinePointV1 | None


class TimelineContextProvenanceV1(ContractModelTimelineV1):
    point_source_kind: TimelineSourceKindV1 | None = Field(alias="pointSourceKind")
    point_source_system: Literal["forzy-csv", "forzy-api"] | None = Field(
        alias="pointSourceSystem"
    )
    active_historical_batch_id: Sha256V1 | None = Field(
        alias="activeHistoricalBatchId"
    )
    collection_policy_id: NonEmptyStringV1 | None = Field(alias="collectionPolicyId")
    assessment_source: Literal[
        "live_assessment", "historical_walk_forward", "none"
    ] = Field(alias="assessmentSource")


class TimelineContextCapabilitiesV1(ContractModelTimelineV1):
    historical_navigation: bool = Field(alias="historicalNavigation")
    paired_channels: bool = Field(alias="pairedChannels")
    causal_assessment: bool = Field(alias="causalAssessment")
    baseline_comparison: bool = Field(alias="baselineComparison")
    previous_cycle_comparison: bool = Field(alias="previousCycleComparison")


class TimelineOverviewV1(ContractModelTimelineV1):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    query_fingerprint: Sha256V1 = Field(alias="queryFingerprint")
    active_historical_batch_id: Sha256V1 | None = Field(alias="activeHistoricalBatchId")
    requested_range: TimelineRequestedRangeV1 = Field(alias="requestedRange")
    effective_range: TimelineHalfOpenRangeV1 | None = Field(alias="effectiveRange")
    available_range: TimelineHalfOpenRangeV1 | None = Field(alias="availableRange")
    aggregation_summary: TimelineAggregationSummaryV1 = Field(
        alias="aggregationSummary"
    )
    segments: list[TimelineSegmentV1]
    gaps: list[TimelineGapV1]
    operating_cycles: list[TimelineOperatingCycleV1] = Field(alias="operatingCycles")
    series: list[TimelineSeriesV1]
    event_candidates: list[TimelineEventCandidateV1] = Field(alias="eventCandidates")
    capabilities: TimelineOverviewCapabilitiesV1

    @model_validator(mode="after")
    def invariants(self) -> Self:
        assert_timeline_invariants_v1(self.model_dump_public(), "timeline-overview")
        return self


class TimelinePageV1(ContractModelTimelineV1):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    query_fingerprint: Sha256V1 = Field(alias="queryFingerprint")
    active_historical_batch_id: Sha256V1 | None = Field(alias="activeHistoricalBatchId")
    items: list[TimelinePointV1]
    next_cursor: NonEmptyStringV1 | None = Field(alias="nextCursor")
    has_more: bool = Field(alias="hasMore")
    limit: int = Field(ge=1, le=4000)

    @model_validator(mode="after")
    def invariants(self) -> Self:
        assert_timeline_invariants_v1(self.model_dump_public(), "timeline-page")
        return self


class TimelineContextV1(ContractModelTimelineV1):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    selected_at: UtcTimestampV1 = Field(alias="selectedAt")
    segment_id: Uuid5V1 | None = Field(alias="segmentId")
    anchor: TimelinePointV1 | None
    channels: TimelineContextChannelsV1
    assessment: HistoricalAssessmentV1 | AssetConditionAssessmentV2 | None
    decision_facts: TimelineDecisionFactsV1 = Field(alias="decisionFacts")
    provenance: TimelineContextProvenanceV1
    capabilities: TimelineContextCapabilitiesV1
    limitations: list[NonEmptyStringV1]

    @model_validator(mode="after")
    def invariants(self) -> Self:
        assert_timeline_invariants_v1(self.model_dump_public(), "timeline-context")
        return self

    def model_dump_public(self) -> dict[str, object]:
        payload = super().model_dump_public()
        if isinstance(self.assessment, AssetConditionAssessmentV2):
            payload["assessment"] = self.assessment.to_public_dict()
        return payload

    def model_dump_public_json(self) -> str:
        return json.dumps(
            self.model_dump_public(),
            ensure_ascii=False,
            separators=(",", ":"),
        )


def public_millisecond_successor_v1(value: datetime) -> datetime:
    parsed = parse_public_utc_millis_v1(value)
    terminal = datetime(9999, 12, 31, 23, 59, 59, 999_000, tzinfo=timezone.utc)
    if parsed == terminal:
        raise TimelineRangeOverflow("timeline_range_overflow")
    return parsed + timedelta(milliseconds=1)


def _timestamp(value: object) -> datetime:
    return parse_public_utc_millis_v1(value)


def _duration_seconds(start: object, end: object) -> float:
    return (_timestamp(end) - _timestamp(start)).total_seconds()


def _uuid5_url_v1(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, name))


def _assert_unique_canonical_strings(values: object, label: str) -> None:
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise ValueError(f"{label} must contain non-empty strings")
    if values != sorted(set(values)):
        raise ValueError(f"{label} must be unique and canonically ordered")


def _assert_finite_json_tree(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("timeline numbers must be finite")
    if isinstance(value, list):
        for child in value:
            _assert_finite_json_tree(child)
    elif isinstance(value, dict):
        for child in value.values():
            _assert_finite_json_tree(child)


def _assert_historical_reading(value: dict[str, object]) -> None:
    _timestamp(value["eventAt"])
    _timestamp(value["provenance"]["ingestedAt"])
    _assert_unique_canonical_strings(value["qualityFlags"], "qualityFlags")


def _assert_point(value: dict[str, object]) -> None:
    _timestamp(value["eventAt"])
    _assert_unique_canonical_strings(value["qualityFlags"], "qualityFlags")
    provenance = value["provenance"]
    historical = value["sourceKind"] == "historical_archive"
    if not isinstance(provenance, dict):
        raise ValueError("timeline point provenance must be an object")
    if historical:
        if (
            value["timestampQuality"] != "source_without_offset_assumed_timezone"
            or value["operatingCycleId"] is None
            or provenance.get("sourceSystem") != "forzy-csv"
        ):
            raise ValueError("sourceKind and provenance must describe the same source")
        _timestamp(provenance["ingestedAt"])
    else:
        if (
            value["timestampQuality"] != "assumed_from_retrieval"
            or provenance.get("sourceSystem") != "forzy-api"
            or _timestamp(provenance["scheduledAt"]) > _timestamp(provenance["receivedAt"])
            or _timestamp(value["eventAt"]) != _timestamp(provenance["receivedAt"])
        ):
            raise ValueError("sourceKind and provenance must describe the same source")


def _assert_historical_assessment(value: dict[str, object]) -> None:
    training = value["trainingWindow"]
    assessment = value["assessmentWindow"]
    persistence = value["persistence"]
    quality = value["quality"]
    if not all(isinstance(item, dict) for item in (training, assessment, persistence, quality)):
        raise ValueError("historical assessment nested facts must be objects")
    training_start, training_end = _timestamp(training["start"]), _timestamp(training["end"])
    assessment_start, assessment_end = _timestamp(assessment["start"]), _timestamp(assessment["end"])
    assessment_at = _timestamp(value["assessmentAt"])
    if not (
        training_start <= training_end
        and assessment_start <= assessment_end
        and training_end < assessment_start
        and assessment_end <= assessment_at
    ):
        raise ValueError("historical assessment windows are not causal")
    _assert_unique_canonical_strings(quality["flags"], "assessment quality flags")
    _assert_unique_canonical_strings(value["limitations"], "assessment limitations")
    evidence = value["evidence"]
    evidence_ids = [item["id"] for item in evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("assessment evidence IDs must be unique")

    episode_id = persistence["episodeId"]
    episode_started_at = persistence["episodeStartedAt"]
    seconds = persistence["persistenceSeconds"]
    count = persistence["persistenceCount"]
    status = value["status"]
    if status in {"watch", "alert"}:
        if (
            episode_id is None
            or episode_started_at is None
            or count < 1
            or value["anomalyScore"] is None
            or value["deteriorationScore"] is None
        ):
            raise ValueError("watch/alert require scores and causal episode facts")
        episode_start = _timestamp(episode_started_at)
        if not (training_end < episode_start <= assessment_end <= assessment_at):
            raise ValueError("historical assessment episode is not causal")
        if seconds != _duration_seconds(episode_started_at, assessment["end"]):
            raise ValueError("persistenceSeconds must use original causal timestamps")
    else:
        if episode_id is not None or episode_started_at is not None or seconds != 0 or count != 0:
            raise ValueError("non-episode assessment persistence must be null/zero")
        scores = (value["anomalyScore"], value["deteriorationScore"])
        if status == "insufficient_data" and scores != (None, None):
            raise ValueError("non-evaluable assessments require null scores")
        if status == "normal" and any(score is None for score in scores):
            raise ValueError("evaluable normal assessments require scores")


def _assert_collection_policy(value: dict[str, object]) -> None:
    if value["activeWeekdays"] != ["monday", "tuesday", "wednesday"]:
        raise ValueError("activeWeekdays must be ordered and complete")
    if value["effectiveTo"] is not None and _timestamp(value["effectiveTo"]) <= _timestamp(
        value["effectiveFrom"]
    ):
        raise ValueError("effectiveTo must be later than effectiveFrom")
    selected_keys = (
        "schemaVersion",
        "collectionPolicyId",
        "assetId",
        "timezone",
        "activeWeekdays",
        "windowStartLocal",
        "windowEndLocal",
        "pollIntervalSeconds",
        "gapThresholdSeconds",
    )
    canonical = json.dumps(
        {key: value[key] for key in selected_keys},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if value["configurationHash"] != expected:
        raise ValueError("configurationHash does not match canonical policy")


def _assert_candidate(value: dict[str, object]) -> None:
    if _timestamp(value["episodeStartedAt"]) > _timestamp(value["eventAt"]):
        raise ValueError("episodeStartedAt must not follow eventAt")
    quality = value["quality"]
    _assert_unique_canonical_strings(quality["flags"], "candidate quality flags")
    historical = value["sourceKind"] == "historical_archive"
    if historical:
        if any(value[key] is None for key in ("operatingCycleId", "batchId", "foldId")):
            raise ValueError("historical candidates require archive facts")
    elif value["batchId"] is not None or value["foldId"] is not None:
        raise ValueError("live candidate cannot claim archive facts")
    quality_status = quality["status"]
    trust = value["dataTrust"]
    if quality_status == "degraded" and trust == "sufficient":
        raise ValueError("candidate trust is better than quality evidence")
    if quality_status == "insufficient_data" and trust != "insufficient":
        raise ValueError("insufficient quality requires insufficient trust")
    identity_name = "|".join(
        (
            "timeline-event-candidate-v1",
            value["sourceKind"],
            value["batchId"] or "none",
            value["anchorPointId"],
            value["modelFamily"],
            value["modelVersion"],
            value["foldId"] or "none",
        )
    )
    if value["candidateId"] != _uuid5_url_v1(identity_name):
        raise ValueError("candidateId does not match its frozen UUIDv5 identity")


def _assert_decision_facts(value: dict[str, object]) -> None:
    scope = value["conditionTemporalScope"]
    source = value["conditionSource"]
    as_of = value["conditionAsOf"]
    episode = value["conditionEpisodeStartedAt"]
    if as_of is not None:
        _timestamp(as_of)
    if episode is not None:
        _timestamp(episode)
    if (scope == "none") != (source == "none"):
        raise ValueError("condition temporal scope and source must agree")
    if scope == "none" and (as_of is not None or episode is not None):
        raise ValueError("none condition facts require null timestamps")
    if source != "none" and as_of is None:
        raise ValueError("condition evidence requires conditionAsOf")
    if episode is not None and (as_of is None or _timestamp(episode) > _timestamp(as_of)):
        raise ValueError("condition episode facts are invalid")
    if value["collectionState"] == "historical_gap":
        expected = {
            "conditionState": "unknown",
            "conditionTemporalScope": "none",
            "conditionAsOf": None,
            "conditionEpisodeStartedAt": None,
            "conditionSource": "none",
            "collectionState": "historical_gap",
            "collectionExpectation": "not_applicable",
            "dataAvailability": "gap",
            "dataFreshness": "historical",
            "dataTrust": "insufficient",
        }
        if any(value[key] != expected[key] for key in expected):
            raise ValueError("historical gap facts are crossed")
    if value["collectionState"] == "historical_context":
        if not (
            value["collectionExpectation"] == "not_applicable"
            and value["dataAvailability"] in {"complete", "partial"}
            and value["dataFreshness"] == "historical"
            and scope != "current"
        ):
            raise ValueError("historical context facts are crossed")
    if value["conditionSource"] == "historical_walk_forward" and scope != "historical":
        raise ValueError("historical assessment requires historical temporal scope")
    if value["collectionState"] == "expected_idle" and value[
        "collectionExpectation"
    ] != "expected_idle":
        raise ValueError("expected-idle collection facts are crossed")
    if value["dataAvailability"] in {"gap", "unavailable"} and scope == "current":
        raise ValueError("gap or unavailable data cannot claim current condition")
    if value["collectionState"] == "unavailable" and value[
        "dataAvailability"
    ] != "unavailable":
        raise ValueError("unavailable collection facts are crossed")
    if value["conditionState"] == "normal" and (
        value["dataTrust"] != "sufficient" or value["dataAvailability"] != "complete"
    ):
        if not (
            scope == "none"
            and source == "none"
            and as_of is None
            and episode is None
        ):
            raise ValueError("degraded normality must suppress temporal condition claims")


def _assert_overview(value: dict[str, object]) -> None:
    requested = value["requestedRange"]
    for bound in (requested["from"], requested["to"]):
        if bound is not None:
            _timestamp(bound)
    if requested["from"] is not None and requested["to"] is not None:
        if _timestamp(requested["from"]) >= _timestamp(requested["to"]):
            raise ValueError("requestedRange must be increasing")

    segments = value["segments"]
    segment_by_id: dict[str, dict[str, object]] = {}
    segment_keys: list[tuple[datetime, str]] = []
    for segment in segments:
        segment_id = segment["segmentId"]
        if segment_id in segment_by_id:
            raise ValueError("segment IDs must be unique")
        segment_by_id[segment_id] = segment
        segment_keys.append((_timestamp(segment["startAt"]), segment_id))
        if _timestamp(segment["startAt"]) > _timestamp(segment["endAt"]):
            raise ValueError("segment startAt must not follow endAt")
        counts = segment["sensorCounts"]
        if counts["s1"] + counts["s2"] != segment["totalPoints"]:
            raise ValueError("segment sensor counts must equal totalPoints")
        _assert_unique_canonical_strings(segment["assumptions"], "segment assumptions")
        historical = segment["sourceKind"] == "historical_archive"
        if historical:
            if not (
                segment["batchId"] is not None
                and segment["collectionPolicyId"] is None
                and segment["timestampQuality"]
                == "source_without_offset_assumed_timezone"
            ):
                raise ValueError("archive segment source facts are crossed")
            if value["activeHistoricalBatchId"] != segment["batchId"]:
                raise ValueError("archive segment must use the active historical batch")
        elif not (
            segment["batchId"] is None
            and segment["timestampQuality"] == "assumed_from_retrieval"
        ):
            raise ValueError("live segment source facts are crossed")
    if segment_keys != sorted(segment_keys):
        raise ValueError("segments must use deterministic total order")

    message_by_type = {
        "source_discontinuity": "timeline_gap_source_discontinuity",
        "archive_sampling_gap": "timeline_gap_archive_sampling",
        "live_expected_collection_gap": "timeline_gap_live_expected_collection",
        "expected_idle": "timeline_gap_expected_idle",
        "unclassified_coverage_gap": "timeline_gap_unclassified_coverage",
    }
    gaps = value["gaps"]
    gap_keys: list[tuple[datetime, datetime, str]] = []
    seen_gap_ids: set[str] = set()
    gap_pairs: set[tuple[str | None, str | None]] = set()
    for gap in gaps:
        if gap["gapId"] in seen_gap_ids:
            raise ValueError("gap IDs must be unique")
        seen_gap_ids.add(gap["gapId"])
        start, end = _timestamp(gap["startAt"]), _timestamp(gap["endAt"])
        gap_keys.append((start, end, gap["gapId"]))
        if start >= end or gap["durationSeconds"] != (end - start).total_seconds():
            raise ValueError("gap duration must equal its open interval")
        if gap["messageCode"] != message_by_type[gap["gapType"]]:
            raise ValueError("gap type and message code must agree")
        left_id, right_id = gap["leftSegmentId"], gap["rightSegmentId"]
        identity_name = "|".join(
            (
                "timeline-gap-v1",
                gap["gapType"],
                left_id or "none",
                right_id or "none",
                gap["startAt"],
                gap["endAt"],
                gap["ruleVersion"],
            )
        )
        if gap["gapId"] != _uuid5_url_v1(identity_name):
            raise ValueError("gapId does not match its frozen UUIDv5 identity")
        if left_id is None and right_id is None:
            raise ValueError("a gap must border at least one segment")
        left = segment_by_id.get(left_id) if left_id is not None else None
        right = segment_by_id.get(right_id) if right_id is not None else None
        if left_id is not None and (left is None or _timestamp(left["endAt"]) != start):
            raise ValueError("leftSegmentId does not border the gap")
        if right_id is not None and (right is None or _timestamp(right["startAt"]) != end):
            raise ValueError("rightSegmentId does not border the gap")
        if left is not None and right is not None:
            different_sources = left["sourceKind"] != right["sourceKind"]
            if different_sources != (gap["gapType"] == "source_discontinuity"):
                raise ValueError("source discontinuity gap type is crossed")
            if not different_sources:
                if left["sourceKind"] == "historical_archive" and gap["gapType"] != "archive_sampling_gap":
                    raise ValueError("archive segments require archive sampling gaps")
                if left["sourceKind"] == "live_collection":
                    policies = {left["collectionPolicyId"], right["collectionPolicyId"]}
                    if gap["gapType"] == "unclassified_coverage_gap" and None not in policies:
                        raise ValueError("classified live policy cannot claim an unclassified gap")
                    if gap["gapType"] in {"live_expected_collection_gap", "expected_idle"} and (
                        None in policies or len(policies) != 1
                    ):
                        raise ValueError("classified live gaps require one persisted policy")
        gap_pairs.add((left_id, right_id))
    if gap_keys != sorted(gap_keys):
        raise ValueError("gaps must use deterministic order")
    for left, right in zip(segments, segments[1:], strict=False):
        if _timestamp(left["endAt"]) > _timestamp(right["startAt"]):
            raise ValueError("segments must not overlap")
        if _timestamp(left["endAt"]) < _timestamp(right["startAt"]) and (
            left["segmentId"], right["segmentId"]
        ) not in gap_pairs:
            raise ValueError("every inter-segment coverage gap must be explicit")

    candidates = value["eventCandidates"]
    candidate_counts: dict[str, int] = {}
    for candidate in candidates:
        _assert_candidate(candidate)
        cycle_id = candidate["operatingCycleId"]
        if cycle_id is not None:
            candidate_counts[cycle_id] = candidate_counts.get(cycle_id, 0) + 1
        if candidate["sourceKind"] == "historical_archive" and candidate["batchId"] != value["activeHistoricalBatchId"]:
            raise ValueError("historical candidate must use the active batch")

    cycles = value["operatingCycles"]
    cycle_keys: list[tuple[datetime, str]] = []
    previous_id: str | None = None
    previous_cycle: dict[str, object] | None = None
    seen_cycle_ids: set[str] = set()
    cycle_by_id: dict[str, dict[str, object]] = {}
    for index, cycle in enumerate(cycles):
        cycle_id = cycle["operatingCycleId"]
        if cycle_id in seen_cycle_ids:
            raise ValueError("operating cycle IDs must be unique")
        seen_cycle_ids.add(cycle_id)
        cycle_by_id[cycle_id] = cycle
        cycle_keys.append((_timestamp(cycle["startAt"]), cycle_id))
        counts = cycle["sensorCounts"]
        if counts["s1"] + counts["s2"] != cycle["totalPoints"]:
            raise ValueError("cycle sensor counts must equal totalPoints")
        duration = _duration_seconds(cycle["startAt"], cycle["endAt"])
        if duration < 0 or cycle["durationSeconds"] != duration:
            raise ValueError("cycle duration must equal its inclusive endpoints")
        if cycle["batchId"] != value["activeHistoricalBatchId"]:
            raise ValueError("operating cycles must use the active historical batch")
        if cycle["previousOperatingCycleId"] != previous_id:
            raise ValueError("previousOperatingCycleId must name the immediate predecessor")
        if cycle["candidateCount"] != candidate_counts.get(cycle_id, 0):
            raise ValueError("cycle candidateCount must match returned candidates")
        if index == 0:
            if cycle["gapBeforeSeconds"] is not None:
                raise ValueError("the first cycle cannot claim a previous gap")
        else:
            expected_gap = _duration_seconds(previous_cycle["endAt"], cycle["startAt"])
            if expected_gap < 0 or cycle["gapBeforeSeconds"] != expected_gap:
                raise ValueError("gapBeforeSeconds must match consecutive cycle endpoints")
        _assert_unique_canonical_strings(cycle["assumptions"], "cycle assumptions")
        previous_id = cycle_id
        previous_cycle = cycle
    if cycle_keys != sorted(cycle_keys):
        raise ValueError("operating cycles must be ordered by startAt and ID")
    for candidate in candidates:
        if candidate["sourceKind"] != "historical_archive":
            continue
        cycle = cycle_by_id.get(candidate["operatingCycleId"])
        if cycle is None:
            raise ValueError("historical candidate references an unknown operating cycle")
        event_at = _timestamp(candidate["eventAt"])
        if not (_timestamp(cycle["startAt"]) <= event_at <= _timestamp(cycle["endAt"])):
            raise ValueError("historical candidate event does not belong to its cycle")

    series = value["series"]
    expected_series_keys: list[tuple[datetime, str, str, str, str]] = []
    combinations: dict[tuple[str, str], list[dict[str, object]]] = {}
    totals = [0, 0, 0]
    seen_point_ids: set[str] = set()
    seen_series_groups: set[tuple[str, str, str]] = set()
    resolved_metrics: set[str] = set()
    for row in series:
        segment = segment_by_id.get(row["segmentId"])
        if segment is None:
            raise ValueError("series references an unknown segment")
        if segment["sourceKind"] != row["sourceKind"]:
            raise ValueError("series crosses segment source")
        group = (row["segmentId"], row["sensorId"], row["sourceKind"])
        if group in seen_series_groups:
            raise ValueError("series group must be unique")
        seen_series_groups.add(group)
        resolved_metrics.add(row["metric"])
        aggregation = row["aggregation"]
        points = row["points"]
        original = aggregation["originalPointCount"]
        returned = aggregation["returnedPointCount"]
        omitted = aggregation["omittedPointCount"]
        if returned != len(points) or omitted != original - returned:
            raise ValueError("series aggregation counts are invalid")
        if original != segment["sensorCounts"][row["sensorId"]]:
            raise ValueError("series membership disagrees with segment sensor counts")
        point_keys: list[tuple[datetime, str]] = []
        for point in points:
            point_id = point["pointId"]
            if point_id in seen_point_ids:
                raise ValueError("series cannot duplicate original point IDs")
            seen_point_ids.add(point_id)
            event_at = _timestamp(point["eventAt"])
            if not (_timestamp(segment["startAt"]) <= event_at <= _timestamp(segment["endAt"])):
                raise ValueError("series point does not belong to its segment")
            point_keys.append((event_at, point_id))
        if point_keys != sorted(point_keys):
            raise ValueError("series points must retain total order")
        key = (row["sensorId"], row["sourceKind"])
        combinations.setdefault(key, []).append(row)
        expected_series_keys.append(
            (
                _timestamp(segment["startAt"]),
                row["segmentId"],
                row["sourceKind"],
                row["sensorId"],
                row["metric"],
            )
        )
        totals[0] += original
        totals[1] += returned
        totals[2] += omitted
    if expected_series_keys != sorted(expected_series_keys):
        raise ValueError("series must use deterministic segment order")
    if len(resolved_metrics) > 1:
        raise ValueError("one response must resolve exactly one metric")

    summary = value["aggregationSummary"]
    for rows in combinations.values():
        ceilings = {row["aggregation"]["requestedMaxPoints"] for row in rows}
        methods = {row["aggregation"]["method"] for row in rows}
        if ceilings != {summary["requestedMaxPoints"]} or len(methods) != 1:
            raise ValueError("series combination ceiling and method must agree")
        original_total = sum(row["aggregation"]["originalPointCount"] for row in rows)
        returned_total = sum(row["aggregation"]["returnedPointCount"] for row in rows)
        method = next(iter(methods))
        expected_method = (
            "none"
            if original_total <= summary["requestedMaxPoints"]
            else "time_bucket_envelope_v1"
        )
        if method != expected_method or returned_total > summary["requestedMaxPoints"]:
            raise ValueError("global sensor/source aggregation budget is invalid")
    if [
        summary["originalPointCount"],
        summary["returnedPointCount"],
        summary["omittedPointCount"],
    ] != totals:
        raise ValueError("aggregation summary does not equal series totals")
    reduced_count = sum(
        row["aggregation"]["method"] != "none" for row in series
    )
    if summary["reducedSeriesCount"] != reduced_count:
        raise ValueError("reducedSeriesCount must equal reduced segment series")

    effective = value["effectiveRange"]
    available = value["availableRange"]
    if available is not None and _timestamp(available["from"]) >= _timestamp(
        available["to"]
    ):
        raise ValueError("availableRange must be increasing")
    if not segments:
        if effective is not None or series:
            raise ValueError("an empty query result requires null effectiveRange and no series")
    else:
        if effective is None or available is None:
            raise ValueError("returned coverage requires effective and available ranges")
        earliest = min(_timestamp(segment["startAt"]) for segment in segments)
        latest = max(_timestamp(segment["endAt"]) for segment in segments)
        successor = public_millisecond_successor_v1(latest)
        if not (
            _timestamp(available["from"]) <= earliest
            and successor <= _timestamp(available["to"])
        ):
            raise ValueError("availableRange must cover returned source points")
        if _timestamp(effective["from"]) >= _timestamp(effective["to"]):
            raise ValueError("effectiveRange must be increasing")
        if not (
            _timestamp(effective["from"]) <= earliest
            and successor <= _timestamp(effective["to"])
        ):
            raise ValueError("effectiveRange must cover returned segments")
        expected_from = available["from"] if requested["from"] is None else requested["from"]
        expected_to = available["to"] if requested["to"] is None else requested["to"]
        if effective["from"] != expected_from or effective["to"] != expected_to:
            raise ValueError("effectiveRange must preserve explicit bounds and resolve unbounded bounds")
        if requested["from"] is None and requested["to"] is None and (
            available["from"] != serialize_public_utc_millis_v1(earliest)
            or available["to"] != serialize_public_utc_millis_v1(successor)
        ):
            raise ValueError("unbounded availableRange must minimally cover all source points")


def _assert_page(value: dict[str, object]) -> None:
    for item in value["items"]:
        _assert_point(item)
        if item["sourceKind"] == "historical_archive" and item["provenance"][
            "batchId"
        ] != value["activeHistoricalBatchId"]:
            raise ValueError("archive page item must use the active historical batch")
    keys = [(_timestamp(item["eventAt"]), item["pointId"]) for item in value["items"]]
    if keys != sorted(keys) or len({key[1] for key in keys}) != len(keys):
        raise ValueError("timeline page items must be unique and totally ordered")
    if value["hasMore"] != (value["nextCursor"] is not None):
        raise ValueError("nextCursor and hasMore must agree")


def _assert_context(value: dict[str, object]) -> None:
    _timestamp(value["selectedAt"])
    facts = value["decisionFacts"]
    provenance = value["provenance"]
    capabilities = value["capabilities"]
    _assert_decision_facts(facts)
    _assert_unique_canonical_strings(value["limitations"], "context limitations")

    channels = value["channels"]
    returned_channels: list[dict[str, object]] = []
    for sensor_id in ("s1", "s2"):
        point = channels[sensor_id]
        if point is None:
            continue
        _assert_point(point)
        if point["sensorId"] != sensor_id:
            raise ValueError("context channel sensorId must match its map key")
        returned_channels.append(point)
    anchor = value["anchor"]
    if anchor is not None:
        _assert_point(anchor)
        if anchor["pointId"] not in {point["pointId"] for point in returned_channels}:
            raise ValueError("context anchor must be one of the returned original channels")
    elif returned_channels:
        raise ValueError("returned context channels require an anchor")

    channel_count = len(returned_channels)
    expected_availability = "complete" if channel_count == 2 else "partial"
    if channel_count == 0:
        if facts["dataAvailability"] not in {"gap", "unavailable"}:
            raise ValueError("no channels require gap or unavailable availability")
    elif facts["dataAvailability"] != expected_availability:
        raise ValueError("dataAvailability must reflect returned channels")

    paired = channel_count == 2
    if capabilities["pairedChannels"] != paired:
        raise ValueError("pairedChannels must reflect returned channels")
    if capabilities["causalAssessment"] != (value["assessment"] is not None):
        raise ValueError("causalAssessment must reflect the returned assessment")

    if paired:
        left, right = returned_channels
        for key in ("samplePairId", "eventAt", "sourceKind", "operatingCycleId", "assetId"):
            if left[key] != right[key]:
                raise ValueError("paired context channels must share original pair facts")
        if left["provenance"]["sourceSystem"] != right["provenance"]["sourceSystem"]:
            raise ValueError("paired context channels cannot cross source systems")
        if left["sourceKind"] == "historical_archive" and left["provenance"][
            "batchId"
        ] != right["provenance"]["batchId"]:
            raise ValueError("paired historical channels cannot cross batches")
        if left["sourceKind"] == "live_collection" and left["provenance"][
            "collectionPolicyId"
        ] != right["provenance"]["collectionPolicyId"]:
            raise ValueError("paired live channels cannot cross collection policies")

    point_kind = provenance["pointSourceKind"]
    point_system = provenance["pointSourceSystem"]
    assessment_source = provenance["assessmentSource"]
    if point_kind is None:
        if point_system is not None or provenance["collectionPolicyId"] is not None:
            raise ValueError("no-point provenance cannot claim a source or policy")
    elif point_kind == "historical_archive":
        if not (
            point_system == "forzy-csv"
            and provenance["activeHistoricalBatchId"] is not None
            and provenance["collectionPolicyId"] is None
            and assessment_source in {"historical_walk_forward", "none"}
        ):
            raise ValueError("historical provenance facts are crossed")
    elif not (
        point_system == "forzy-api"
        and assessment_source in {"live_assessment", "none"}
    ):
        raise ValueError("live provenance facts are crossed")
    if returned_channels:
        if value["segmentId"] is None:
            raise ValueError("returned context points require segmentId")
        if any(point["sourceKind"] != point_kind for point in returned_channels):
            raise ValueError("context points and provenance source kind must agree")
        if anchor is not None and anchor["sourceKind"] != point_kind:
            raise ValueError("context anchor and provenance source kind must agree")
        if point_kind == "historical_archive":
            batches = {point["provenance"]["batchId"] for point in returned_channels}
            if batches != {provenance["activeHistoricalBatchId"]}:
                raise ValueError("historical context points must use the active batch")
        else:
            policies = {
                point["provenance"]["collectionPolicyId"]
                for point in returned_channels
            }
            if policies != {provenance["collectionPolicyId"]}:
                raise ValueError("live context points must use the claimed collection policy")
    if assessment_source != facts["conditionSource"]:
        raise ValueError("assessment source must agree across context facts")
    if provenance["collectionPolicyId"] is None and facts["collectionExpectation"] == "expected_now":
        raise ValueError("a missing policy cannot become expected_now")

    historical_state = facts["collectionState"] in {
        "historical_context",
        "historical_gap",
    }
    if capabilities["historicalNavigation"] != historical_state:
        raise ValueError("historicalNavigation must reflect collection state")
    if historical_state:
        if not (
            facts["dataFreshness"] == "historical"
            and facts["collectionState"] in {"historical_context", "historical_gap"}
            and facts["collectionExpectation"] == "not_applicable"
            and facts["conditionTemporalScope"] != "current"
        ):
            raise ValueError("historical navigation facts are crossed")

    if facts["collectionState"] == "historical_gap":
        if not (
            value["segmentId"] is None
            and value["anchor"] is None
            and channels["s1"] is None
            and channels["s2"] is None
            and value["assessment"] is None
        ):
            raise ValueError("historical gap context cannot carry point facts")

    assessment = value["assessment"]
    if assessment is None:
        if facts["conditionEpisodeStartedAt"] is not None or facts["conditionSource"] != "none":
            raise ValueError("condition evidence requires a returned matching assessment")
    elif assessment["schemaVersion"] == "1.0":
        _assert_historical_assessment(assessment)
        if not (
            facts["conditionSource"] == "historical_walk_forward"
            and facts["conditionState"] == assessment["status"]
            and facts["conditionAsOf"] == assessment["assessmentAt"]
            and facts["conditionEpisodeStartedAt"]
            == assessment["persistence"]["episodeStartedAt"]
        ):
            raise ValueError("historical condition facts do not match the assessment")
        anchor = value["anchor"]
        if anchor is not None and not (
            anchor["pointId"] == assessment["anchorPointId"]
            and anchor["sensorId"] == assessment["sensorId"]
            and anchor["operatingCycleId"] == assessment["operatingCycleId"]
            and _timestamp(assessment["assessmentAt"]) <= _timestamp(anchor["eventAt"])
        ):
            raise ValueError("historical assessment anchor facts are crossed")
    else:
        if not (
            facts["conditionSource"] == "live_assessment"
            and facts["conditionState"] == assessment["assessment"]["status"]
        ):
            raise ValueError("live condition facts do not match the assessment")


def assert_timeline_invariants_v1(
    value: dict[str, object], schema_name: str | None = None
) -> dict[str, object]:
    """Validate cross-field facts deliberately outside draft-07."""

    if not isinstance(value, dict):
        raise ValueError("timeline payload must be an object")
    _assert_finite_json_tree(value)
    name = schema_name
    if name is None:
        if "segments" in value:
            name = "timeline-overview"
        elif "collectionPolicyId" in value and "configurationHash" in value:
            name = "collection-policy"
        elif "candidateId" in value:
            name = "timeline-event-candidate"
        elif "decisionFacts" in value:
            name = "timeline-context"
        elif "conditionState" in value:
            name = "timeline-decision-facts"
        elif "items" in value and "hasMore" in value:
            name = "timeline-page"
        elif "assessmentId" in value and value.get("schemaVersion") == "1.0":
            name = "historical-assessment"
        elif "pointId" in value:
            name = "timeline-point"
        elif "readingId" in value and value.get("sourceKind") == "historical_archive":
            name = "historical-sensor-reading"

    if name == "historical-sensor-reading":
        _assert_historical_reading(value)
    elif name == "timeline-point":
        _assert_point(value)
    elif name == "historical-assessment":
        _assert_historical_assessment(value)
    elif name == "collection-policy":
        _assert_collection_policy(value)
    elif name == "timeline-event-candidate":
        _assert_candidate(value)
    elif name == "timeline-overview":
        _assert_overview(value)
    elif name == "timeline-page":
        _assert_page(value)
    elif name == "timeline-decision-facts":
        _assert_decision_facts(value)
    elif name == "timeline-context":
        _assert_context(value)
    else:
        raise ValueError(f"unknown timeline schema: {name}")
    return value


def _external_references(value: object) -> set[str]:
    references: set[str] = set()
    if isinstance(value, list):
        for child in value:
            references.update(_external_references(child))
    elif isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str) and not child.startswith("#"):
                references.add(urldefrag(child).url)
            else:
                references.update(_external_references(child))
    return references


def build_timeline_schema_registry_v1(
    documents: list[dict[str, object]],
) -> tuple[Registry, dict[str, Draft7Validator]]:
    """Check, register, resolve, and compile the complete timeline schema catalog."""

    ids: list[str] = []
    for document in documents:
        Draft7Validator.check_schema(document)
        schema_id = document.get("$id")
        if not isinstance(schema_id, str):
            raise ValueError("timeline schema requires an absolute $id")
        parsed = urlsplit(schema_id)
        if not parsed.scheme or parsed.fragment or not parsed.netloc:
            raise ValueError("timeline schema $id must be an absolute URI")
        ids.append(schema_id)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate timeline schema $id")

    known_ids = set(ids)
    unresolved = sorted(
        reference
        for document in documents
        for reference in _external_references(document)
        if reference not in known_ids
    )
    if unresolved:
        raise ValueError(f"unresolved timeline schema $ref: {unresolved[0]}")

    registry = Registry().with_resources(
        (
            schema_id,
            Resource.from_contents(document, default_specification=DRAFT7),
        )
        for schema_id, document in zip(ids, documents, strict=True)
    )
    validators: dict[str, Draft7Validator] = {}
    for schema_id, document in zip(ids, documents, strict=True):
        if schema_id.startswith(_TIMELINE_SCHEMA_PREFIX):
            name = schema_id.removeprefix(_TIMELINE_SCHEMA_PREFIX)
            validator = Draft7Validator(document, registry=registry)
            # Force root compilation/resolution now, not on the first request.
            list(validator.iter_errors({}))
            validators[name] = validator
    return registry, validators


def _load_schema_documents() -> list[dict[str, object]]:
    documents = [
        json.loads((_SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
        for name in _SCHEMA_NAMES
    ]
    documents.append(
        json.loads(
            (_ROOT / "contracts" / "v2" / "asset-condition-assessment.schema.json").read_text(
                encoding="utf-8"
            )
        )
    )
    return documents


TIMELINE_SCHEMA_DOCUMENTS_V1 = _load_schema_documents()
TIMELINE_SCHEMA_REGISTRY, _TIMELINE_VALIDATORS = build_timeline_schema_registry_v1(
    TIMELINE_SCHEMA_DOCUMENTS_V1
)


def validate_timeline_public_v1(schema_name: str, payload: dict[str, object]) -> None:
    normalized_name = schema_name.removeprefix(_TIMELINE_SCHEMA_PREFIX)
    validator = _TIMELINE_VALIDATORS.get(normalized_name)
    if validator is None:
        raise ValueError(f"unknown timeline schema: {schema_name}")
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path)
        prefix = f"{path}: " if path else ""
        raise ValueError(prefix + error.message)
    assert_timeline_invariants_v1(payload, normalized_name)
