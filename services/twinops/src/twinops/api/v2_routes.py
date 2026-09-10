"""HTTP routes for the single real TwinOps asset."""

import asyncio
from datetime import datetime, timezone
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from twinops.api.v2_snapshot import build_live_twin_context_v2, build_snapshot_v2
from twinops.contracts.v2_projections import to_sensor_telemetry_frame_v2
from twinops.ingestion.schedule import CollectionWindow
from twinops.rag.operational import TrustedOperationalContext
from twinops.rag.public_models import AssistantQueryRequest, AssistantQueryResponse
from twinops.rag.public_service import prohibited_intent_response
from twinops.rag.retrieval import CorpusUnavailableError
from twinops.storage.v2_repository import HistoryQueryV2


PUBLIC_ASSET_ID = "forzy-motor-01"


def create_v2_router() -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["real-twin"])

    @router.get("/assets/{asset_id}/twin-context")
    def twin_context(request: Request, asset_id: str):
        _require_asset(request, asset_id)
        now = request.app.state.clock()
        operational_state, freshness_basis = _persisted_state(request, now)
        return build_live_twin_context_v2(
            repository=request.app.state.repository,
            scorer=request.app.state.assessment_scorer,
            now=now,
            operational_state=operational_state,
            freshness_basis=freshness_basis,
            twin3d_enabled=True,
            copilot_enabled=_copilot_configured(request),
        )

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
        completion = result.completed_at or request.app.state.clock()
        return {
            "refreshAttempted": result.refresh_attempted,
            "outcomes": result.outcomes,
            "snapshot": _build_snapshot(
                request,
                now=max(now, completion),
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
        _validate_history_range(from_at, to_at)
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

    @router.post(
        "/assets/{asset_id}/assistant/query",
        response_model=AssistantQueryResponse,
        response_model_by_alias=True,
    )
    async def assistant_query(
        request: Request,
        asset_id: str,
        body: AssistantQueryRequest,
    ):
        started = perf_counter()
        _require_asset(request, asset_id)
        refusal = prohibited_intent_response(
            body,
            generation_model=request.app.state.settings.rag_generation_model,
            started_at=started,
        )
        if refusal is not None:
            return refusal
        service = request.app.state.rag_assistant_service
        if not _copilot_configured(request) or service is None:
            raise HTTPException(status_code=503, detail="rag_unavailable")

        async def load_operational():
            return await asyncio.to_thread(_trusted_operational_context, request)

        try:
            response = await service.query_with_operational_loader(
                asset_id,
                body,
                operational_loader=load_operational,
                started_at=started,
            )
            return response.model_copy(
                update={
                    "latency_ms": max(
                        0.0, (perf_counter() - started) * 1000.0
                    )
                }
            )
        except CorpusUnavailableError:
            raise HTTPException(status_code=503, detail="rag_unavailable") from None

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


def _validate_history_range(
    from_at: datetime | None, to_at: datetime | None
) -> None:
    for value in (from_at, to_at):
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise HTTPException(status_code=422, detail="timezone_required")
    if from_at is not None and to_at is not None and from_at > to_at:
        raise HTTPException(status_code=422, detail="invalid_time_range")


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
    snapshot = _snapshot_model(
        request,
        now=now,
        operational_state=operational_state,
        freshness_basis=freshness_basis,
    )
    return snapshot.model_dump(mode="json", by_alias=True)


def _snapshot_model(
    request: Request,
    *,
    now,
    operational_state,
    freshness_basis,
    copilot_enabled=None,
):
    return build_snapshot_v2(
        repository=request.app.state.repository,
        scorer=request.app.state.assessment_scorer,
        now=now,
        operational_state=operational_state,
        freshness_basis=freshness_basis,
        twin3d_enabled=True,
        copilot_enabled=(
            _copilot_available(request)
            if copilot_enabled is None
            else copilot_enabled
        ),
    )


def _trusted_operational_context(request: Request) -> TrustedOperationalContext:
    now = request.app.state.clock()
    operational_state, freshness_basis = _persisted_state(request, now)
    snapshot = _snapshot_model(
        request,
        now=now,
        operational_state=operational_state,
        freshness_basis=freshness_basis,
        copilot_enabled=True,
    )
    return TrustedOperationalContext.from_snapshot(snapshot)


def _copilot_configured(request: Request) -> bool:
    settings = request.app.state.settings
    return bool(
        settings.rag_enabled
        and settings.rag_api_key is not None
        and settings.rag_generation_model
        and request.app.state.rag_assistant_service is not None
    )


def _copilot_available(request: Request) -> bool:
    service = request.app.state.rag_assistant_service
    if not _copilot_configured(request) or service is None:
        return False
    try:
        return bool(service.is_healthy(PUBLIC_ASSET_ID))
    except Exception:
        return False


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
