"""Sanitized collector health exposed per sensor."""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from twinops.ingestion.schedule import CollectionWindow


router = APIRouter(prefix="/api/v1/system", tags=["system"])
PUBLIC_ERRORS = {"upstream_unavailable", "invalid_payload"}


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _public_error(value: str | None) -> str | None:
    if value is None or value in PUBLIC_ERRORS:
        return value
    return "upstream_unavailable"


@router.get("/health")
def health(request: Request):
    now = request.app.state.clock()
    open_now = CollectionWindow(
        request.app.state.settings.timezone_name
    ).is_open(now)
    sensors = {}
    for sensor_id in ("s1", "s2"):
        item = request.app.state.repository.health(sensor_id)
        sensors[sensor_id] = {
            "lastAttemptAt": _timestamp(item.last_attempt_at) if item else None,
            "lastSuccessAt": _timestamp(item.last_success_at) if item else None,
            "latencyMs": item.latency_ms if item else None,
            "error": _public_error(item.error_code) if item else None,
            "sampleCount": item.sample_count if item else 0,
        }
    return {
        "status": "ok",
        "collector": {
            "state": "active" if open_now else "expected_idle",
            "sensors": sensors,
        },
    }
