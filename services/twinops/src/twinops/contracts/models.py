"""Strict Pydantic representations of the version 1 TwinOps contracts."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


Timestamp = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
    ),
]
Uuid = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    ),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class ContractModel(BaseModel):
    """Shared validation and serialization settings for public contracts."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class EmptyObject(ContractModel):
    """A JSON object deliberately specified with no properties."""


class Measurement(ContractModel):
    value: float
    unit: str
    semantic_confidence: Literal[
        "confirmed", "inferred_from_datasheet", "unconfirmed"
    ] = Field(alias="semanticConfidence")


class VelocityMeasurement(Measurement):
    unit: Literal["mm/s"]


class AccelerationMeasurement(Measurement):
    unit: Literal["g"]
    statistic: Literal["unknown"]


class TemperatureMeasurement(Measurement):
    unit: Literal["degC"]


class Measurements(ContractModel):
    vibration_velocity_rms: VelocityMeasurement = Field(alias="vibrationVelocityRms")
    vibration_acceleration: AccelerationMeasurement = Field(alias="vibrationAcceleration")
    temperature: TemperatureMeasurement


class TelemetrySample(ContractModel):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    sample_id: Uuid = Field(alias="sampleId")
    source: Literal["forzy-live", "forzy-csv"]
    asset_tag: NonEmptyString = Field(alias="assetTag")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    scheduled_at: Timestamp | None = Field(alias="scheduledAt")
    received_at: Timestamp = Field(alias="receivedAt")
    observed_at: Timestamp | None = Field(alias="observedAt")
    measurements: Measurements
    quality_flags: list[str] = Field(alias="qualityFlags")
    payload_hash: Sha256 = Field(alias="payloadHash")
    raw: EmptyObject

    @model_validator(mode="after")
    def live_samples_have_no_observed_timestamp(self) -> Self:
        if self.source == "forzy-live" and self.observed_at is not None:
            raise ValueError("forzy-live samples must set observedAt to null")
        return self


class AssessmentWindow(ContractModel):
    start: Timestamp
    end: Timestamp
    received_at: Timestamp = Field(alias="receivedAt")
    freshness_ms: float = Field(alias="freshnessMs", ge=0)


class AssessmentQuality(ContractModel):
    status: Literal["ok", "degraded", "insufficient_data"]
    flags: list[str]


class OperatingContext(ContractModel):
    state: Literal["steady", "startup", "shutdown", "stopped", "unknown"]
    estimated: bool


class AssessmentDetail(ContractModel):
    status: Literal["normal", "watch", "alert", "insufficient_data"]
    anomaly_score: float = Field(alias="anomalyScore")
    deterioration_score: float = Field(alias="deteriorationScore")
    score_semantics: Literal[
        "relative_to_historical_baseline_not_failure_probability"
    ] = Field(alias="scoreSemantics")
    episode_id: str | None = Field(alias="episodeId")
    persistence_seconds: float = Field(alias="persistenceSeconds", ge=0)


class ModelMetadata(ContractModel):
    name: NonEmptyString
    version: NonEmptyString
    config_hash: Sha256 = Field(alias="configHash")
    trained_until: Timestamp = Field(alias="trainedUntil")


class DetectionAssessment(ContractModel):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    inference_id: Uuid = Field(alias="inferenceId")
    asset_tag: NonEmptyString = Field(alias="assetTag")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    window: AssessmentWindow
    quality: AssessmentQuality
    operating_context: OperatingContext = Field(alias="operatingContext")
    assessment: AssessmentDetail
    component_tag: str | None = Field(alias="componentTag")
    recommendation: str | None
    human_validation_required: bool = Field(alias="humanValidationRequired")
    evidence: list[EmptyObject]
    model: ModelMetadata
    limitations: list[str]


class Capabilities(ContractModel):
    replay_controls: bool = Field(alias="replayControls")
    live_updates: bool = Field(alias="liveUpdates")
    copilot: bool
    twin_3d: bool = Field(alias="twin3d")


class TwinSnapshot(ContractModel):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    asset_tag: NonEmptyString = Field(alias="assetTag")
    mode: Literal["replay", "live"]
    generated_at: Timestamp = Field(alias="generatedAt")
    status: Literal["normal", "watch", "alert", "unknown", "insufficient_data"]
    freshness: Literal["fresh", "delayed", "expected_idle", "unavailable", "unknown"]
    channels: list[TelemetrySample]
    history: list[TelemetrySample]
    assessment: DetectionAssessment | None
    capabilities: Capabilities

    @model_validator(mode="after")
    def live_snapshots_have_both_live_channels(self) -> Self:
        if self.mode == "live":
            sensor_ids = [channel.sensor_id for channel in self.channels]
            if len(sensor_ids) != 2 or set(sensor_ids) != {"s1", "s2"}:
                raise ValueError("live snapshots require exactly one s1 and one s2 channel")
        return self
