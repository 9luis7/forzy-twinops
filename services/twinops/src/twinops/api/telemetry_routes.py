"""Canonical snapshot and history routes without audit-only fields."""

from datetime import datetime, timezone
import logging
from typing import Literal
import uuid

from fastapi import APIRouter, Query, Request

from twinops.contracts.models import (
    AssetConditionAssessment,
    CanonicalSensorReading,
    DigitalTwinSnapshot,
    SensorTelemetryFrame,
)
from twinops.contracts.projections import to_sensor_telemetry_frame
from twinops.ingestion.schedule import CollectionWindow
from twinops.storage.repository import HistoryQuery


router = APIRouter(prefix="/api/v1/twin/assets", tags=["telemetry"])


def _unavailable_frame(
    asset_tag: str, sensor_id: Literal["s1", "s2"]
) -> SensorTelemetryFrame:
    return SensorTelemetryFrame.model_validate(
        {
            "schemaVersion": "1.0",
            "frameId": str(uuid.uuid4()),
            "assetTag": asset_tag,
            "sensorId": sensor_id,
            "sourceMode": "live",
            "observedAt": None,
            "receivedAt": None,
            "timestampQuality": "unknown",
            "measurements": {
                "vibrationVelocityRms": None,
                "vibrationAcceleration": None,
                "temperature": None,
            },
            "qualityFlags": ["unavailable"],
        }
    )


@router.get("/{asset_tag}/history")
def history(
    request: Request,
    asset_tag: str,
    sensorId: str | None = None,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(200, ge=1, le=1000),
):
    query = HistoryQuery(asset_tag, sensorId, None, from_, to, limit)
    items = [
        to_sensor_telemetry_frame(sample).model_dump(mode="json", by_alias=True)
        for sample in request.app.state.repository.history(query)
    ]
    return {"items": items, "limit": limit}


@router.get("/{asset_tag}/snapshot")
def snapshot(request: Request, asset_tag: str):
    now = request.app.state.clock()
    latest = request.app.state.repository.latest(asset_tag)
    by_sensor = {sample.sensor_id: sample for sample in latest}
    channels = []
    for sensor_id in ("s1", "s2"):
        reading = by_sensor.get(sensor_id)
        channels.append(
            to_sensor_telemetry_frame(reading)
            if reading is not None
            else _unavailable_frame(asset_tag, sensor_id)
        )
    assessment, assessed_sensor_count = _assessment(request, asset_tag, now)
    all_channels_available = set(by_sensor) == {"s1", "s2"}
    scorer_complete = (
        request.app.state.assessment_scorer is None or assessed_sensor_count == 2
    )
    if latest and (not all_channels_available or not scorer_complete):
        status = "insufficient_data"
    elif assessment is not None:
        status = assessment.assessment.status
    else:
        status = "insufficient_data" if latest else "unknown"
    body = {
        "schemaVersion": "1.0",
        "assetTag": asset_tag,
        "mode": "live",
        "generatedAt": now
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "status": status,
        "freshness": _snapshot_freshness(request, latest, now),
        "channels": [
            channel.model_dump(mode="json", by_alias=True) for channel in channels
        ],
        "history": [],
        "assessment": (
            assessment.model_dump(mode="json", by_alias=True)
            if assessment is not None
            else None
        ),
        "capabilities": {
            "replayControls": False,
            "liveUpdates": True,
            "copilot": assessment is not None,
            "twin3d": False,
        },
    }
    return DigitalTwinSnapshot.model_validate(body).model_dump(
        mode="json", by_alias=True
    )


def _assessment(
    request: Request, asset_tag: str, now: datetime
) -> tuple[AssetConditionAssessment | None, int]:
    scorer = request.app.state.assessment_scorer
    if scorer is None:
        return None, 0
    assessments = []
    for sensor_id in ("s1", "s2"):
        readings = request.app.state.repository.history(
            HistoryQuery(asset_tag, sensor_id, None, None, None, 1000)
        )
        if not readings:
            continue
        try:
            assessments.append(scorer.assess(readings, now=now))
        except (ValueError, RuntimeError) as exc:
            logging.getLogger("twinops.api").warning(
                "assessment_unavailable sensor_id=%s error_type=%s",
                sensor_id,
                type(exc).__name__,
            )
    rank = {"normal": 0, "insufficient_data": 1, "watch": 2, "alert": 3}
    return (
        max(
            assessments,
            key=lambda item: (
                rank[item.assessment.status],
                item.assessment.anomaly_score,
                item.assessment.deterioration_score,
            ),
            default=None,
        ),
        len(assessments),
    )


def _snapshot_freshness(
    request: Request,
    latest: list[CanonicalSensorReading],
    now: datetime,
) -> str:
    settings = request.app.state.settings
    if not CollectionWindow(settings.timezone_name).is_open(now):
        return "expected_idle"
    if not latest:
        return "unavailable"
    if any(sample.source != "forzy-live" for sample in latest):
        return "delayed"
    latest_received = max(
        datetime.fromisoformat(sample.received_at.replace("Z", "+00:00"))
        for sample in latest
    )
    age_seconds = max(0.0, (now - latest_received).total_seconds())
    return (
        "fresh"
        if age_seconds <= settings.poll_interval_seconds * 2
        else "delayed"
    )
