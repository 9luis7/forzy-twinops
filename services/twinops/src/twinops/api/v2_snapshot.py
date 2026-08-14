"""Pure assembly of contract-valid TwinOps v2 snapshots."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from twinops.contracts.models import CanonicalSensorReading
from twinops.contracts.v2_models import (
    AssetConditionAssessmentV2,
    CanonicalSensorReadingV2,
    DigitalTwinSnapshotV2,
    SensorTelemetryFrameV2,
)
from twinops.contracts.v2_projections import to_sensor_telemetry_frame_v2
from twinops.ml.scorer import AssessmentScorer
from twinops.storage.v2_repository import (
    HistoryQueryV2,
    RepositorySensorHealthV2,
    TelemetryRepositoryV2,
)


_ASSET_ID = "forzy-motor-01"
_SENSOR_IDS = ("s1", "s2")


def build_snapshot_v2(
    *,
    repository: TelemetryRepositoryV2,
    scorer: AssessmentScorer,
    now: datetime,
    operational_state: Literal[
        "received_now", "last_known", "expected_idle", "unavailable"
    ],
    freshness_basis: Literal[
        "retrieval_time", "last_received", "schedule", "none"
    ],
    twin3d_enabled: bool,
) -> DigitalTwinSnapshotV2:
    """Read current telemetry and return a snapshot without mutating dependencies."""

    generated_at = _timestamp(now)
    readings_by_sensor = {
        sensor_id: repository.history(
            HistoryQueryV2(
                asset_id=_ASSET_ID,
                sensor_id=sensor_id,
                limit=1000,
            )
        )
        for sensor_id in _SENSOR_IDS
    }
    channels = [
        (
            to_sensor_telemetry_frame_v2(readings_by_sensor[sensor_id][0])
            if readings_by_sensor[sensor_id]
            else _unavailable_frame(sensor_id, generated_at)
        )
        for sensor_id in _SENSOR_IDS
    ]
    history = [
        to_sensor_telemetry_frame_v2(reading)
        for sensor_id in _SENSOR_IDS
        for reading in readings_by_sensor[sensor_id][1:]
    ]
    complete = all(readings_by_sensor[sensor_id] for sensor_id in _SENSOR_IDS)
    assessments = (
        [
            _score_sensor(
                scorer,
                readings_by_sensor[sensor_id],
                now=now,
            )
            for sensor_id in _SENSOR_IDS
        ]
        if complete
        else []
    )
    complete_assessments = [item for item in assessments if item is not None]
    selected_assessment = None
    if assessments and len(complete_assessments) == len(assessments):
        selected_assessment = max(
            complete_assessments,
            key=lambda item: _status_rank(item.assessment.status),
        )
    status = (
        selected_assessment.assessment.status
        if selected_assessment is not None
        else "insufficient_data"
    )

    return DigitalTwinSnapshotV2.model_validate(
        {
            "schemaVersion": "2.0",
            "asset": {
                "assetId": _ASSET_ID,
                "displayName": "Conjunto motor-bomba monitorado",
                "officialTag": None,
            },
            "generatedAt": generated_at,
            "status": status,
            "operationalState": operational_state,
            "freshnessBasis": freshness_basis,
            "channels": channels,
            "history": history,
            "assessment": selected_assessment,
            "integration": {
                "sensors": {
                    sensor_id: _sensor_health(repository.health(sensor_id))
                    for sensor_id in _SENSOR_IDS
                }
            },
            "capabilities": {
                "liveUpdates": True,
                "replayControls": False,
                "copilot": False,
                "twin3d": twin3d_enabled,
            },
        }
    )


def _score_sensor(
    scorer: AssessmentScorer,
    readings: list[CanonicalSensorReadingV2],
    *,
    now: datetime,
) -> AssetConditionAssessmentV2 | None:
    assessment = scorer.assess(
        [_to_scorer_reading(reading) for reading in readings],
        now=now,
    )
    if assessment is None:
        return None
    body = assessment.model_dump(mode="json", by_alias=True)
    body["schemaVersion"] = "2.0"
    body["assetId"] = _ASSET_ID
    body.pop("assetTag", None)
    return AssetConditionAssessmentV2.model_validate(body)


def _to_scorer_reading(reading: CanonicalSensorReadingV2) -> CanonicalSensorReading:
    return CanonicalSensorReading.model_validate(
        {
            "schemaVersion": "1.0",
            "readingId": reading.reading_id,
            "source": "forzy-live",
            "assetTag": reading.asset_id,
            "sensorId": reading.sensor_id,
            "scheduledAt": reading.scheduled_at,
            "observedAt": None,
            "receivedAt": reading.received_at,
            "measurements": reading.measurements.model_dump(mode="json", by_alias=True),
            "qualityFlags": list(reading.quality_flags),
            "payloadHash": reading.payload_hash,
            "raw": {},
            "provenance": {
                "sourceSystem": "forzy-api",
                "ingestedAt": reading.received_at,
            },
        }
    )


def _status_rank(status: str) -> int:
    return {
        "normal": 0,
        "watch": 1,
        "alert": 2,
        "insufficient_data": 3,
    }[status]


def _unavailable_frame(sensor_id: str, generated_at: str) -> SensorTelemetryFrameV2:
    frame_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"{_ASSET_ID}|{sensor_id}|{generated_at}|unavailable")
    )
    return SensorTelemetryFrameV2.model_validate(
        {
            "schemaVersion": "2.0",
            "frameId": frame_id,
            "assetId": _ASSET_ID,
            "sensorId": sensor_id,
            "observedAt": None,
            "receivedAt": None,
            "timestampQuality": "unavailable",
            "measurements": {
                "vibrationVelocityRms": None,
                "vibrationAcceleration": None,
                "temperature": None,
            },
            "qualityFlags": ["unavailable"],
        }
    )


def _sensor_health(
    health: RepositorySensorHealthV2 | None,
) -> dict[str, object]:
    if health is None:
        return {
            "lastAttemptAt": None,
            "lastSuccessAt": None,
            "latencyMs": None,
            "error": None,
            "sampleCount": 0,
        }
    return {
        "lastAttemptAt": _optional_timestamp(health.last_attempt_at),
        "lastSuccessAt": _optional_timestamp(health.last_success_at),
        "latencyMs": health.latency_ms,
        "error": health.error_code,
        "sampleCount": health.sample_count,
    }


def _optional_timestamp(value: datetime | None) -> str | None:
    return None if value is None else _timestamp(value)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("snapshot timestamps must be timezone-aware")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
