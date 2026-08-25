"""Read-only HTTP boundary for the frozen Timeline v1 contracts."""

from __future__ import annotations

import re
from typing import TypeVar

from fastapi import APIRouter, HTTPException, Query, Request

from twinops.api.v2_routes import PUBLIC_ASSET_ID
from twinops.contracts.timeline_v1_models import (
    ContractModelTimelineV1,
    TimelineContextV1,
    TimelineOverviewV1,
    TimelinePageV1,
    parse_public_utc_millis_v1,
    validate_timeline_public_v1,
)
from twinops.timeline.cursor_v1 import TimelineCursorConflict
from twinops.timeline.repository_v1 import TimelineReadQueryV1
from twinops.timeline.service_v1 import (
    TimelineAssetNotFoundV1,
    TimelineContextQueryInvalidV1,
    TimelineContextQueryV1,
    TimelineOverviewQueryV1,
    TimelinePointNotFoundV1,
    TimelineSegmentNotFoundV1,
    TimelineSelectionOutsideSegment,
)


_INTEGER_RE = re.compile(r"^[0-9]+$")
_METRICS = frozenset(
    {
        "vibrationVelocityRms",
        "vibrationAcceleration",
        "temperature",
    }
)
_OVERVIEW_QUERY_ALIASES = frozenset(
    {"from", "to", "sensorId", "metric", "maxPoints"}
)
_SAMPLES_QUERY_ALIASES = frozenset(
    {"from", "to", "sensorId", "metric", "limit", "cursor"}
)
_CONTEXT_QUERY_ALIASES = frozenset({"pointId", "at", "segmentId"})
_ModelT = TypeVar("_ModelT", bound=ContractModelTimelineV1)


def _require_asset(asset_id: str) -> None:
    if asset_id != PUBLIC_ASSET_ID:
        raise HTTPException(status_code=404, detail="asset_not_found")


def _invalid_query() -> HTTPException:
    return HTTPException(status_code=422, detail="timeline_invalid_query")


def _reject_duplicate_query_aliases(
    request: Request,
    aliases: frozenset[str],
) -> None:
    if any(len(request.query_params.getlist(alias)) > 1 for alias in aliases):
        raise _invalid_query()


def _parse_timestamp(value: str | None):
    if value is None:
        return None
    try:
        return parse_public_utc_millis_v1(value)
    except (TypeError, ValueError) as exc:
        raise _invalid_query() from exc


def _parse_integer(value: str, *, minimum: int, maximum: int) -> int:
    if _INTEGER_RE.fullmatch(value) is None:
        raise _invalid_query()
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise _invalid_query()
    return parsed


def _parse_sensor(value: str | None):
    if value is None:
        return None
    if value not in {"s1", "s2"}:
        raise _invalid_query()
    return value


def _parse_metric(value: str):
    if value not in _METRICS:
        raise _invalid_query()
    return value


def _public_payload(
    value: object,
    *,
    model_type: type[_ModelT],
    schema_name: str,
) -> dict[str, object]:
    if not isinstance(value, model_type):
        raise RuntimeError("timeline service returned an invalid public model")
    payload = value.model_dump_public()
    model_type.model_validate(payload)
    validate_timeline_public_v1(schema_name, payload)
    return payload


def create_timeline_router() -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["timeline"])

    @router.get("/assets/{asset_id}/timeline")
    def overview(
        request: Request,
        asset_id: str,
        from_value: str | None = Query(None, alias="from"),
        to_value: str | None = Query(None, alias="to"),
        sensor_value: str | None = Query(None, alias="sensorId"),
        metric_value: str = Query("vibrationVelocityRms", alias="metric"),
        max_points_value: str = Query("1200", alias="maxPoints"),
    ):
        _require_asset(asset_id)
        _reject_duplicate_query_aliases(request, _OVERVIEW_QUERY_ALIASES)
        sensor_id = _parse_sensor(sensor_value)
        try:
            query = TimelineOverviewQueryV1(
                asset_id=asset_id,
                from_at=_parse_timestamp(from_value),
                to_at=_parse_timestamp(to_value),
                sensor_ids=("s1", "s2") if sensor_id is None else (sensor_id,),
                metric=_parse_metric(metric_value),
                max_points=_parse_integer(
                    max_points_value,
                    minimum=40,
                    maximum=4000,
                ),
            )
        except (TypeError, ValueError) as exc:
            raise _invalid_query() from exc
        result = request.app.state.timeline_service.overview(query)
        return _public_payload(
            result,
            model_type=TimelineOverviewV1,
            schema_name="timeline-overview",
        )

    @router.get("/assets/{asset_id}/timeline/samples")
    def samples(
        request: Request,
        asset_id: str,
        from_value: str | None = Query(None, alias="from"),
        to_value: str | None = Query(None, alias="to"),
        sensor_value: str | None = Query(None, alias="sensorId"),
        metric_value: str = Query("vibrationVelocityRms", alias="metric"),
        limit_value: str = Query("200", alias="limit"),
        cursor: str | None = Query(None, alias="cursor"),
    ):
        _require_asset(asset_id)
        _reject_duplicate_query_aliases(request, _SAMPLES_QUERY_ALIASES)
        try:
            query = TimelineReadQueryV1(
                asset_id=asset_id,
                from_at=_parse_timestamp(from_value),
                to_at=_parse_timestamp(to_value),
                sensor_id=_parse_sensor(sensor_value),
                metric=_parse_metric(metric_value),
                after=None,
                limit=_parse_integer(limit_value, minimum=1, maximum=500),
            )
        except (TypeError, ValueError) as exc:
            raise _invalid_query() from exc
        try:
            result = request.app.state.timeline_service.samples(
                query,
                cursor=cursor,
            )
        except TimelineCursorConflict as exc:
            raise HTTPException(
                status_code=409,
                detail="timeline_cursor_conflict",
            ) from exc
        return _public_payload(
            result,
            model_type=TimelinePageV1,
            schema_name="timeline-page",
        )

    @router.get("/assets/{asset_id}/timeline/context")
    def context(
        request: Request,
        asset_id: str,
        point_id: str | None = Query(None, alias="pointId"),
        at_value: str | None = Query(None, alias="at"),
        segment_id: str | None = Query(None, alias="segmentId"),
    ):
        _require_asset(asset_id)
        _reject_duplicate_query_aliases(request, _CONTEXT_QUERY_ALIASES)
        try:
            query = TimelineContextQueryV1(
                asset_id=asset_id,
                point_id=point_id,
                at=_parse_timestamp(at_value),
                segment_id=segment_id,
            )
        except TimelineAssetNotFoundV1 as exc:
            raise HTTPException(status_code=404, detail="asset_not_found") from exc
        except (TimelineContextQueryInvalidV1, TypeError, ValueError) as exc:
            raise _invalid_query() from exc
        try:
            result = request.app.state.timeline_service.context(query)
        except TimelinePointNotFoundV1 as exc:
            raise HTTPException(
                status_code=404,
                detail="timeline_point_not_found",
            ) from exc
        except TimelineSegmentNotFoundV1 as exc:
            raise HTTPException(
                status_code=404,
                detail="timeline_segment_not_found",
            ) from exc
        except TimelineSelectionOutsideSegment as exc:
            raise HTTPException(
                status_code=422,
                detail="timeline_selection_outside_segment",
            ) from exc
        return _public_payload(
            result,
            model_type=TimelineContextV1,
            schema_name="timeline-context",
        )

    return router


__all__ = ["create_timeline_router"]
