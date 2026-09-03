"""Pure assembly of contract-valid TwinOps v2 snapshots."""

import logging
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
_LOGGER = logging.getLogger("twinops.api")


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
    copilot_enabled: bool = False,
) -> DigitalTwinSnapshotV2:
    """Read current telemetry and return a snapshot without mutating dependencies."""

    latest_by_sensor = {
        reading.sensor_id: reading for reading in repository.latest(_ASSET_ID)
    }
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
    time_candidates = [_as_datetime(now)]
    time_candidates.extend(
        _as_datetime(reading.received_at)
        for reading in (
            list(latest_by_sensor.values())
            + [
                item
                for sensor_readings in readings_by_sensor.values()
                for item in sensor_readings
            ]
        )
    )
    effective_now = max(time_candidates)
    generated_at = _timestamp(effective_now)
    channels = [
        (
            to_sensor_telemetry_frame_v2(latest_by_sensor[sensor_id])
            if sensor_id in latest_by_sensor
            else _unavailable_frame(sensor_id, generated_at)
        )
        for sensor_id in _SENSOR_IDS
    ]
    history = [
        to_sensor_telemetry_frame_v2(reading)
        for reading in sorted(
            (
                reading
                for sensor_id in _SENSOR_IDS
                for reading in readings_by_sensor[sensor_id]
            ),
            key=lambda item: (
                _as_datetime(item.observed_at),
                _as_datetime(item.received_at),
                item.reading_id,
            ),
            reverse=True,
        )
    ]
    complete = all(sensor_id in latest_by_sensor for sensor_id in _SENSOR_IDS)
    assessments = (
        [
            _score_sensor(
                scorer,
                readings_by_sensor[sensor_id],
                sensor_id=sensor_id,
                now=effective_now,
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
                "copilot": copilot_enabled,
                "twin3d": twin3d_enabled,
            },
        }
    )


def _score_sensor(
    scorer: AssessmentScorer,
    readings: list[CanonicalSensorReadingV2],
    *,
    sensor_id: str,
    now: datetime,
) -> AssetConditionAssessmentV2 | None:
    try:
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
    except Exception as exc:
        _LOGGER.warning(
            "assessment_unavailable error_type=%s sensor=%s",
            type(exc).__name__,
            sensor_id,
        )
        return None


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
        "insufficient_data": 1,
        "watch": 2,
        "alert": 3,
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


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("snapshot timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)
