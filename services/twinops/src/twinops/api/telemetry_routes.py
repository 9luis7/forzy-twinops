"""Canonical snapshot and history routes without audit-only fields."""

from datetime import datetime, timezone
from typing import Literal
import uuid

from fastapi import APIRouter, Query, Request

from twinops.contracts.models import (
    DigitalTwinSnapshot,
    SensorTelemetryFrame,
)
from twinops.contracts.projections import to_sensor_telemetry_frame
from twinops.storage.repository import HistoryQuery


router = APIRouter(prefix="/api/v1/twin/assets", tags=["telemetry"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    body = {
        "schemaVersion": "1.0",
        "assetTag": asset_tag,
        "mode": "live",
        "generatedAt": _utc_now(),
        "status": "insufficient_data" if latest else "unknown",
        "freshness": "fresh" if latest else "unavailable",
        "channels": [
            channel.model_dump(mode="json", by_alias=True) for channel in channels
        ],
        "history": [],
        "assessment": None,
        "capabilities": {
            "replayControls": False,
            "liveUpdates": True,
            "copilot": False,
            "twin3d": True,
        },
    }
    return DigitalTwinSnapshot.model_validate(body).model_dump(
        mode="json", by_alias=True
    )
