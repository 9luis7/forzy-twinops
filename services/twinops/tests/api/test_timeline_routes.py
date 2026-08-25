from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from twinops.config_v2 import SettingsV2
from twinops.contracts.timeline_v1_models import (
    TimelineContextV1,
    TimelineOverviewV1,
    TimelinePageV1,
)
from twinops.main_v2 import create_app_v2
from twinops.timeline import service_v1
from twinops.timeline.cursor_v1 import TimelineCursorConflict
from twinops.timeline.repository_v1 import timeline_order_key_v1

from services.twinops.tests.timeline.overview_fixtures_v1 import (
    FakeTimelineRepositoryV1,
    make_policy,
    make_point,
)


BASE = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
TIME_A = "2026-08-25T15:00:00.000Z"
TIME_B = "2026-08-25T15:00:00.001Z"
POINT_A = "00000000-0000-5000-8000-000000000001"
POINT_B = "00000000-0000-5000-8000-000000000002"
SEGMENT_A = "00000000-0000-5000-8000-000000000003"
SEGMENT_B = "00000000-0000-5000-8000-000000000004"


def _service_and_points():
    points = tuple(
        sorted(
            (
                make_point(30, event_at=BASE, sensor_id="s1", pair_key="api"),
                make_point(31, event_at=BASE, sensor_id="s2", pair_key="api"),
            ),
            key=timeline_order_key_v1,
        )
    )
    repository = FakeTimelineRepositoryV1(archive=points)
    return service_v1.TimelineServiceV1(repository), repository, points


def _client(timeline_service, *, refresh_service=None):
    refresh = refresh_service or Mock(refresh=AsyncMock())
    app = create_app_v2(
        repository=object(),
        settings=SettingsV2(upstream_base_url="https://upstream.invalid"),
        refresh_service=refresh,
        assessment_scorer=None,
        clock=lambda: BASE,
        timeline_service=timeline_service,
    )
    return TestClient(app, raise_server_exceptions=False), refresh


def test_three_timeline_gets_honor_aliases_and_return_validated_public_models() -> None:
    service, repository, points = _service_and_points()
    client, refresh = _client(service)
    overview = client.get(
        "/api/v2/assets/forzy-motor-01/timeline",
        params={
            "from": "2026-08-25T15:00:00.000Z",
            "to": "2026-08-25T15:00:00.001Z",
            "sensorId": "s1",
            "metric": "temperature",
            "maxPoints": "40",
        },
    )
    samples = client.get(
        "/api/v2/assets/forzy-motor-01/timeline/samples",
        params={
            "from": "2026-08-25T15:00:00.000Z",
            "to": "2026-08-25T15:00:00.001Z",
            "sensorId": "s2",
            "metric": "vibrationAcceleration",
            "limit": "200",
        },
    )
    context = client.get(
        "/api/v2/assets/forzy-motor-01/timeline/context",
        params={"pointId": str(points[0].point_id)},
    )

    assert overview.status_code == samples.status_code == context.status_code == 200
    TimelineOverviewV1.model_validate(overview.json())
    TimelinePageV1.model_validate(samples.json())
    TimelineContextV1.model_validate(context.json())
    assert overview.json()["requestedRange"] == {
        "from": "2026-08-25T15:00:00.000Z",
        "to": "2026-08-25T15:00:00.001Z",
    }
    assert overview.json()["series"][0]["sensorId"] == "s1"
    assert overview.json()["series"][0]["metric"] == "temperature"
    assert samples.json()["items"][0]["sensorId"] == "s2"
    assert samples.json()["limit"] == 200
    assert context.json()["limitations"] == [
        "causal_assessment_not_available"
    ]
    assert all(point.source_kind == "historical_archive" for point in points)
    refresh.refresh.assert_not_called()
    assert repository.archive_reads and repository.live_reads


def test_samples_defaults_to_200_caps_at_500_and_returns_originals() -> None:
    service, _, points = _service_and_points()
    client, _ = _client(service)

    default = client.get("/api/v2/assets/forzy-motor-01/timeline/samples")
    maximum = client.get(
        "/api/v2/assets/forzy-motor-01/timeline/samples?limit=500"
    )

    assert default.status_code == maximum.status_code == 200
    assert default.json()["limit"] == 200
    assert maximum.json()["limit"] == 500
    assert [item["pointId"] for item in default.json()["items"]] == [
        str(point.point_id) for point in points
    ]


def test_missing_active_archive_returns_live_only_without_side_effects() -> None:
    points = tuple(
        sorted(
            (
                make_point(
                    32,
                    event_at=BASE,
                    sensor_id="s1",
                    source_kind="live_collection",
                    pair_key="live-api",
                ),
                make_point(
                    33,
                    event_at=BASE,
                    sensor_id="s2",
                    source_kind="live_collection",
                    pair_key="live-api",
                ),
            ),
            key=timeline_order_key_v1,
        )
    )
    repository = FakeTimelineRepositoryV1(
        live=points,
        policies=(make_policy(),),
        batch_id=None,
    )
    client, refresh = _client(service_v1.TimelineServiceV1(repository))

    overview = client.get("/api/v2/assets/forzy-motor-01/timeline")
    samples = client.get("/api/v2/assets/forzy-motor-01/timeline/samples")
    context = client.get(
        "/api/v2/assets/forzy-motor-01/timeline/context",
        params={"pointId": str(points[0].point_id)},
    )

    assert overview.status_code == samples.status_code == context.status_code == 200
    assert overview.json()["activeHistoricalBatchId"] is None
    assert overview.json()["capabilities"] == {"historical": False, "live": True}
    assert samples.json()["activeHistoricalBatchId"] is None
    assert {item["sourceKind"] for item in samples.json()["items"]} == {
        "live_collection"
    }
    assert context.json()["provenance"] == {
        "pointSourceKind": "live_collection",
        "pointSourceSystem": "forzy-api",
        "activeHistoricalBatchId": None,
        "collectionPolicyId": "forzy-live-window-v1",
        "assessmentSource": "none",
    }
    assert context.json()["assessment"] is None
    refresh.refresh.assert_not_called()


@pytest.mark.parametrize(
    ("path", "service_method", "alias", "supporting", "first", "second"),
    (
        pytest.param(
            "timeline", "overview", "from", (), TIME_A, TIME_B, id="overview-from"
        ),
        pytest.param(
            "timeline", "overview", "to", (), TIME_A, TIME_B, id="overview-to"
        ),
        pytest.param(
            "timeline",
            "overview",
            "sensorId",
            (),
            "s1",
            "s2",
            id="overview-sensor",
        ),
        pytest.param(
            "timeline",
            "overview",
            "metric",
            (),
            "temperature",
            "vibrationAcceleration",
            id="overview-metric",
        ),
        pytest.param(
            "timeline",
            "overview",
            "maxPoints",
            (),
            "40",
            "41",
            id="overview-max-points",
        ),
        pytest.param(
            "timeline/samples",
            "samples",
            "from",
            (),
            TIME_A,
            TIME_B,
            id="samples-from",
        ),
        pytest.param(
            "timeline/samples",
            "samples",
            "to",
            (),
            TIME_A,
            TIME_B,
            id="samples-to",
        ),
        pytest.param(
            "timeline/samples",
            "samples",
            "sensorId",
            (),
            "s1",
            "s2",
            id="samples-sensor",
        ),
        pytest.param(
            "timeline/samples",
            "samples",
            "metric",
            (),
            "temperature",
            "vibrationAcceleration",
            id="samples-metric",
        ),
        pytest.param(
            "timeline/samples",
            "samples",
            "limit",
            (),
            "1",
            "2",
            id="samples-limit",
        ),
        pytest.param(
            "timeline/samples",
            "samples",
            "cursor",
            (),
            "opaque-a",
            "opaque-b",
            id="samples-cursor",
        ),
        pytest.param(
            "timeline/context",
            "context",
            "pointId",
            (),
            POINT_A,
            POINT_B,
            id="context-point",
        ),
        pytest.param(
            "timeline/context",
            "context",
            "at",
            (("segmentId", SEGMENT_A),),
            TIME_A,
            TIME_B,
            id="context-at",
        ),
        pytest.param(
            "timeline/context",
            "context",
            "segmentId",
            (("at", TIME_A),),
            SEGMENT_A,
            SEGMENT_B,
            id="context-segment",
        ),
    ),
)
@pytest.mark.parametrize("duplicate_kind", ("equal", "distinct"))
def test_recognized_duplicate_query_aliases_are_rejected_before_service(
    path: str,
    service_method: str,
    alias: str,
    supporting: tuple[tuple[str, str], ...],
    first: str,
    second: str,
    duplicate_kind: str,
) -> None:
    timeline_service = Mock()
    client, refresh = _client(timeline_service)
    duplicate = first if duplicate_kind == "equal" else second

    response = client.get(
        f"/api/v2/assets/forzy-motor-01/{path}",
        params=[*supporting, (alias, first), (alias, duplicate)],
    )

    assert timeline_service.method_calls == []
    getattr(timeline_service, service_method).assert_not_called()
    assert response.status_code == 422
    assert response.json() == {"detail": "timeline_invalid_query"}
    refresh.refresh.assert_not_called()


def test_duplicate_unknown_query_parameters_remain_ignored() -> None:
    service, _, points = _service_and_points()
    client, refresh = _client(service)
    cases = (
        ("timeline", []),
        ("timeline/samples", []),
        ("timeline/context", [("pointId", str(points[0].point_id))]),
    )

    for path, supporting in cases:
        response = client.get(
            f"/api/v2/assets/forzy-motor-01/{path}",
            params=[*supporting, ("futureAlias", "one"), ("futureAlias", "two")],
        )
        assert response.status_code == 200
    refresh.refresh.assert_not_called()


@pytest.mark.parametrize(
    ("path", "query"),
    (
        ("timeline", "from=2026-08-25T15:00:00Z"),
        ("timeline", "from=2026-08-25T15:00:01.000Z&to=2026-08-25T15:00:00.000Z"),
        ("timeline", "sensorId=s3"),
        ("timeline", "metric=velocity"),
        ("timeline", "maxPoints=39"),
        ("timeline", "maxPoints=40.0"),
        ("timeline/samples", "limit=0"),
        ("timeline/samples", "limit=501"),
        ("timeline/context", ""),
        ("timeline/context", "at=2026-08-25T15:00:00.000Z"),
        ("timeline/context", "pointId=bad"),
    ),
)
def test_invalid_timeline_filters_are_422(path: str, query: str) -> None:
    service, _, _ = _service_and_points()
    client, _ = _client(service)
    suffix = f"?{query}" if query else ""

    response = client.get(
        f"/api/v2/assets/forzy-motor-01/{path}{suffix}"
    )

    assert response.status_code == 422


def test_unknown_asset_is_404_before_timeline_service_calls() -> None:
    timeline_service = Mock()
    client, refresh = _client(timeline_service)

    for suffix in ("timeline", "timeline/samples", "timeline/context?pointId=bad"):
        response = client.get(f"/api/v2/assets/not-real/{suffix}")
        assert response.status_code == 404
        assert response.json() == {"detail": "asset_not_found"}
    timeline_service.assert_not_called()
    timeline_service.overview.assert_not_called()
    timeline_service.samples.assert_not_called()
    timeline_service.context.assert_not_called()
    refresh.refresh.assert_not_called()


def test_named_context_and_cursor_errors_map_to_404_409_and_422() -> None:
    required = (
        "TimelinePointNotFoundV1",
        "TimelineSegmentNotFoundV1",
        "TimelineSelectionOutsideSegment",
    )
    assert all(hasattr(service_v1, name) for name in required)
    PointNotFound, SegmentNotFound, SelectionOutside = (
        getattr(service_v1, name) for name in required
    )
    cases = (
        (PointNotFound("missing"), 404),
        (SegmentNotFound("missing"), 404),
        (TimelineCursorConflict("conflict"), 409),
        (SelectionOutside("outside"), 422),
    )
    for error, expected in cases:
        timeline_service = Mock()
        if isinstance(error, TimelineCursorConflict):
            timeline_service.samples.side_effect = error
            path = "timeline/samples?cursor=opaque"
        else:
            timeline_service.context.side_effect = error
            path = (
                "timeline/context?pointId="
                "00000000-0000-5000-8000-000000000001"
            )
        client, _ = _client(timeline_service)

        response = client.get(f"/api/v2/assets/forzy-motor-01/{path}")

        assert response.status_code == expected


def test_unexpected_timeline_failure_uses_sanitized_500_boundary() -> None:
    timeline_service = Mock()
    timeline_service.overview.side_effect = RuntimeError(
        "postgresql://secret@db.internal/twinops\nTraceback: secret"
    )
    client, _ = _client(timeline_service)

    response = client.get("/api/v2/assets/forzy-motor-01/timeline")

    assert response.status_code == 500
    assert response.json() == {"detail": "internal_error"}
    assert "secret" not in response.text
    assert "db.internal" not in response.text


def test_context_at_and_segment_aliases_select_the_original_anchor() -> None:
    service, _, _ = _service_and_points()
    client, _ = _client(service)
    overview = client.get("/api/v2/assets/forzy-motor-01/timeline").json()

    response = client.get(
        "/api/v2/assets/forzy-motor-01/timeline/context",
        params={
            "at": "2026-08-25T15:00:00.000Z",
            "segmentId": overview["segments"][0]["segmentId"],
        },
    )

    assert response.status_code == 200
    assert response.json()["anchor"] is not None
    assert response.json()["selectedAt"] == "2026-08-25T15:00:00.000Z"
