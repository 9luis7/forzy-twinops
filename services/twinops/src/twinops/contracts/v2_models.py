"""Strict Pydantic representations of the version 2 TwinOps contracts."""

import re
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


_RFC3339_UTC_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
)
_RFC3339_UTC = re.compile(_RFC3339_UTC_PATTERN)


def _validate_rfc3339_utc_timestamp(value: object) -> object:
    """Reject impossible UTC calendar values without normalizing the input string."""

    if isinstance(value, str):
        match = _RFC3339_UTC.fullmatch(value)
        if match is None:
            raise ValueError("must be a valid RFC 3339 UTC timestamp")

        date, time = value.split("T")
        year, month, day = (int(part) for part in date.split("-"))
        hour, minute, second_text = time[:-1].split(":")
        hour_value = int(hour)
        minute_value = int(minute)
        second = int(second_text.split(".", 1)[0])
        leap_year = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        month_days = [
            31,
            29 if leap_year else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ]

        valid_calendar = (
            1 <= month <= 12
            and 1 <= day <= month_days[month - 1]
            and hour_value <= 23
            and minute_value <= 59
            and second <= 60
            and (second < 60 or (hour_value == 23 and minute_value == 59))
        )
        if not valid_calendar:
            raise ValueError("must be a valid RFC 3339 UTC timestamp")
    return value


Timestamp = Annotated[
    str,
    BeforeValidator(_validate_rfc3339_utc_timestamp),
    StringConstraints(pattern=_RFC3339_UTC_PATTERN),
]
Uuid = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    ),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class ContractModelV2(BaseModel):
    """Shared validation and serialization settings for version 2 contracts."""

    model_config = ConfigDict(
        extra="forbid", strict=True, populate_by_name=True, allow_inf_nan=False
    )

    def to_public_dict(self) -> dict[str, object]:
        """Serialize aliases while preserving omitted fields versus explicit nulls."""

        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)


class EmptyObjectV2(ContractModelV2):
    """An object intentionally specified with no properties."""


class MeasurementV2(ContractModelV2):
    value: float
    unit: str
    semantic_confidence: Literal[
        "confirmed", "inferred_from_datasheet", "unconfirmed"
    ] = Field(alias="semanticConfidence")


class VelocityMeasurementV2(MeasurementV2):
    unit: Literal["mm/s"]


class AccelerationMeasurementV2(MeasurementV2):
    unit: Literal["g"]
    statistic: Literal["unknown"]


class TemperatureMeasurementV2(MeasurementV2):
    unit: Literal["degC"]


class MeasurementsV2(ContractModelV2):
    vibration_velocity_rms: VelocityMeasurementV2 = Field(alias="vibrationVelocityRms")
    vibration_acceleration: AccelerationMeasurementV2 = Field(
        alias="vibrationAcceleration"
    )
    temperature: TemperatureMeasurementV2


class CanonicalProvenanceV2(ContractModelV2):
    source_system: Literal["forzy-api"] = Field(alias="sourceSystem")
    ingested_at: Timestamp = Field(alias="ingestedAt")
    source_timestamp_provided: Literal[False] = Field(alias="sourceTimestampProvided")


class CanonicalSensorReadingV2(ContractModelV2):
    schema_version: Literal["2.0"] = Field(alias="schemaVersion")
    reading_id: Uuid = Field(alias="readingId")
    source: Literal["forzy-live"]
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    scheduled_at: Timestamp = Field(alias="scheduledAt")
    observed_at: Timestamp = Field(alias="observedAt")
    received_at: Timestamp = Field(alias="receivedAt")
    timestamp_quality: Literal["assumed_from_retrieval"] = Field(
        alias="timestampQuality"
    )
    measurements: MeasurementsV2
    quality_flags: list[str] = Field(alias="qualityFlags")
    payload_hash: Sha256 = Field(alias="payloadHash")
    raw: EmptyObjectV2
    provenance: CanonicalProvenanceV2

    @model_validator(mode="after")
    def live_time_is_explicitly_assumed(self) -> Self:
        if self.source == "forzy-live":
            if self.observed_at != self.received_at:
                raise ValueError("Forzy live observedAt must equal receivedAt")
            if self.timestamp_quality != "assumed_from_retrieval":
                raise ValueError(
                    "Forzy live timestampQuality must be assumed_from_retrieval"
                )
            if self.provenance.source_timestamp_provided:
                raise ValueError("Forzy live source timestamp was not provided")
        return self


class FrameMeasurementsV2(ContractModelV2):
    vibration_velocity_rms: VelocityMeasurementV2 | None = Field(
        alias="vibrationVelocityRms"
    )
    vibration_acceleration: AccelerationMeasurementV2 | None = Field(
        alias="vibrationAcceleration"
    )
    temperature: TemperatureMeasurementV2 | None


class SensorTelemetryFrameV2(ContractModelV2):
    schema_version: Literal["2.0"] = Field(alias="schemaVersion")
    frame_id: Uuid = Field(alias="frameId")
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    observed_at: Timestamp | None = Field(alias="observedAt")
    received_at: Timestamp | None = Field(alias="receivedAt")
    timestamp_quality: Literal["assumed_from_retrieval", "unavailable"] = Field(
        alias="timestampQuality"
    )
    measurements: FrameMeasurementsV2
    quality_flags: list[str] = Field(alias="qualityFlags")

    @model_validator(mode="after")
    def timestamps_match_quality(self) -> Self:
        if self.timestamp_quality == "assumed_from_retrieval":
            if self.observed_at is None or self.received_at is None:
                raise ValueError(
                    "assumed_from_retrieval requires observedAt and receivedAt"
                )
            if self.observed_at != self.received_at:
                raise ValueError(
                    "assumed_from_retrieval requires observedAt equal receivedAt"
                )
        elif self.observed_at is not None or self.received_at is not None:
            raise ValueError("unavailable requires null observedAt and receivedAt")
        return self


class AssessmentWindowV2(ContractModelV2):
    start: Timestamp
    end: Timestamp
    received_at: Timestamp = Field(alias="receivedAt")
    freshness_ms: float = Field(alias="freshnessMs", ge=0)


class AssessmentQualityV2(ContractModelV2):
    status: Literal["ok", "degraded", "insufficient_data"]
    flags: list[str]


class OperatingContextV2(ContractModelV2):
    state: Literal["steady", "startup", "shutdown", "stopped", "unknown"]
    estimated: bool


class AssessmentDetailV2(ContractModelV2):
    status: Literal["normal", "watch", "alert", "insufficient_data"]
    anomaly_score: float = Field(alias="anomalyScore")
    deterioration_score: float = Field(alias="deteriorationScore")
    score_semantics: Literal[
        "relative_to_historical_baseline_not_failure_probability"
    ] = Field(alias="scoreSemantics")
    episode_id: str | None = Field(alias="episodeId")
    persistence_seconds: float = Field(alias="persistenceSeconds", ge=0)


class AssessmentEvidenceV2(ContractModelV2):
    id: NonEmptyString
    feature: NonEmptyString
    value: float
    unit: NonEmptyString
    baseline: float | None = None
    deviation: float | None = None
    direction: Literal["up", "down", "stable", "unknown"] | None = None
    window_seconds: float | None = Field(default=None, alias="windowSeconds", ge=0)


class ModelMetadataV2(ContractModelV2):
    name: NonEmptyString
    version: NonEmptyString
    config_hash: Sha256 = Field(alias="configHash")
    trained_until: Timestamp = Field(alias="trainedUntil")


class AssetConditionAssessmentV2(ContractModelV2):
    schema_version: Literal["2.0"] = Field(alias="schemaVersion")
    assessment_id: Uuid = Field(alias="assessmentId")
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    window: AssessmentWindowV2
    quality: AssessmentQualityV2
    operating_context: OperatingContextV2 = Field(alias="operatingContext")
    assessment: AssessmentDetailV2
    component_tag: None = Field(alias="componentTag")
    recommendation: str | None
    human_validation_required: bool = Field(alias="humanValidationRequired")
    evidence: list[AssessmentEvidenceV2]
    model: ModelMetadataV2
    limitations: list[str]


class AssetIdentityV2(ContractModelV2):
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    display_name: Literal["Conjunto motor-bomba monitorado"] = Field(alias="displayName")
    official_tag: None = Field(alias="officialTag")


class SensorHealthV2(ContractModelV2):
    last_attempt_at: Timestamp | None = Field(alias="lastAttemptAt")
    last_success_at: Timestamp | None = Field(alias="lastSuccessAt")
    latency_ms: float | None = Field(alias="latencyMs", ge=0)
    error: Literal["upstream_unavailable", "invalid_payload"] | None
    sample_count: int = Field(alias="sampleCount", ge=0)


class IntegrationSensorsV2(ContractModelV2):
    s1: SensorHealthV2
    s2: SensorHealthV2


class IntegrationV2(ContractModelV2):
    sensors: IntegrationSensorsV2


class CapabilitiesV2(ContractModelV2):
    live_updates: Literal[True] = Field(alias="liveUpdates")
    replay_controls: Literal[False] = Field(alias="replayControls")
    copilot: Literal[False]
    twin_3d: bool = Field(alias="twin3d")


class DigitalTwinSnapshotV2(ContractModelV2):
    schema_version: Literal["2.0"] = Field(alias="schemaVersion")
    asset: AssetIdentityV2
    generated_at: Timestamp = Field(alias="generatedAt")
    status: Literal["normal", "watch", "alert", "unknown", "insufficient_data"]
    operational_state: Literal[
        "received_now", "last_known", "expected_idle", "unavailable"
    ] = Field(alias="operationalState")
    freshness_basis: Literal["retrieval_time", "last_received", "schedule", "none"] = Field(
        alias="freshnessBasis"
    )
    channels: list[SensorTelemetryFrameV2]
    history: list[SensorTelemetryFrameV2]
    assessment: AssetConditionAssessmentV2 | None
    integration: IntegrationV2
    capabilities: CapabilitiesV2

    @model_validator(mode="after")
    def has_exactly_one_channel_per_live_sensor(self) -> Self:
        sensor_ids = [channel.sensor_id for channel in self.channels]
        if len(sensor_ids) != 2 or set(sensor_ids) != {"s1", "s2"}:
            raise ValueError("snapshots require exactly one s1 and one s2 channel")
        return self
