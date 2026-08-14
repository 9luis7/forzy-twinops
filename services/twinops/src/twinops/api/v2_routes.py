"""HTTP routes for the single real TwinOps asset."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from twinops.api.v2_snapshot import build_snapshot_v2
from twinops.contracts.v2_projections import to_sensor_telemetry_frame_v2
from twinops.ingestion.schedule import CollectionWindow
from twinops.storage.v2_repository import HistoryQueryV2


PUBLIC_ASSET_ID = "forzy-motor-01"


def create_v2_router() -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["real-twin"])

    @router.get("/assets/{asset_id}/snapshot")
    def snapshot(request: Request, asset_id: str):
        _require_asset(request, asset_id)
        now = request.app.state.clock()
        operational_state, freshness_basis = _persisted_state(request, now)
        return _build_snapshot(
            request,
            now=now,
            operational_state=operational_state,
            freshness_basis=freshness_basis,
        )

    @router.post("/assets/{asset_id}/refresh")
    async def refresh(request: Request, asset_id: str):
        _require_asset(request, asset_id)
        now = request.app.state.clock()
        result = await request.app.state.refresh_service.refresh(now)
        operational_state, freshness_basis = _refresh_state(request, result)
        return {
            "refreshAttempted": result.refresh_attempted,
            "outcomes": result.outcomes,
            "snapshot": _build_snapshot(
                request,
                now=now,
                operational_state=operational_state,
                freshness_basis=freshness_basis,
            ),
        }

    @router.get("/assets/{asset_id}/history")
    def history(
        request: Request,
        asset_id: str,
        sensor_id: Literal["s1", "s2"] | None = Query(None, alias="sensorId"),
        from_at: datetime | None = Query(None, alias="from"),
        to_at: datetime | None = Query(None, alias="to"),
        limit: int = Query(200, ge=1, le=500),
    ):
        _require_asset(request, asset_id)
        items = request.app.state.repository.history(
            HistoryQueryV2(
                asset_id=asset_id,
                sensor_id=sensor_id,
                from_at=from_at,
                to_at=to_at,
                limit=limit,
            )
        )
        return {
            "items": [
                to_sensor_telemetry_frame_v2(item).model_dump(
                    mode="json", by_alias=True
                )
                for item in items
            ],
            "limit": limit,
        }

    @router.get("/integration/health")
    def integration_health(request: Request):
        now = request.app.state.clock()
        settings = request.app.state.settings
        return {
            "status": "ok",
            "integration": {
                "state": (
                    "active"
                    if CollectionWindow(settings.timezone_name).is_open(now)
                    else "expected_idle"
                ),
                "sensors": {
                    sensor_id: _health_item(
                        request.app.state.repository.health(sensor_id)
                    )
                    for sensor_id in ("s1", "s2")
                },
            },
        }

    return router


def _require_asset(request: Request, asset_id: str) -> None:
    if asset_id != PUBLIC_ASSET_ID:
        raise HTTPException(status_code=404, detail="asset_not_found")


def _persisted_state(request: Request, now):
    settings = request.app.state.settings
    if not CollectionWindow(settings.timezone_name).is_open(now):
        return "expected_idle", "schedule"
    if request.app.state.repository.latest(PUBLIC_ASSET_ID):
        return "last_known", "last_received"
    return "unavailable", "none"


def _refresh_state(request: Request, result):
    if not result.refresh_attempted:
        return "expected_idle", "schedule"
    if any(outcome != "failed" for outcome in result.outcomes.values()):
        return "received_now", "retrieval_time"
    if request.app.state.repository.latest(PUBLIC_ASSET_ID):
        return "last_known", "last_received"
    return "unavailable", "none"


def _build_snapshot(
    request: Request,
    *,
    now,
    operational_state,
    freshness_basis,
):
    snapshot = build_snapshot_v2(
        repository=request.app.state.repository,
        scorer=request.app.state.assessment_scorer,
        now=now,
        operational_state=operational_state,
        freshness_basis=freshness_basis,
        twin3d_enabled=True,
    )
    return snapshot.model_dump(mode="json", by_alias=True)


def _health_item(item):
    if item is None:
        return {
            "lastAttemptAt": None,
            "lastSuccessAt": None,
            "latencyMs": None,
            "error": None,
            "sampleCount": 0,
        }
    return {
        "lastAttemptAt": _timestamp(item.last_attempt_at),
        "lastSuccessAt": _timestamp(item.last_success_at),
        "latencyMs": item.latency_ms,
        "error": _public_error(item.error_code),
        "sampleCount": item.sample_count,
    }


def _public_error(value):
    if value is None or value in {"upstream_unavailable", "invalid_payload"}:
        return value
    return "upstream_unavailable"


def _timestamp(value):
    if value is None:
        return None
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
