from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from twinops.contracts.timeline_v1_models import validate_timeline_public_v1
from twinops.timeline import service_v1
from twinops.timeline.repository_v1 import timeline_order_key_v1

from overview_fixtures_v1 import FakeTimelineRepositoryV1, make_point, uuid5_text


BASE = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)


def _context_api():
    required = (
        "TimelineContextQueryV1",
        "TimelineContextQueryInvalidV1",
        "TimelineContextRepositoryErrorV1",
        "TimelinePointNotFoundV1",
        "TimelineSegmentNotFoundV1",
        "TimelineSelectionOutsideSegment",
    )
    missing = [name for name in required if not hasattr(service_v1, name)]
    assert not missing, f"timeline context API missing: {missing}"
    return tuple(getattr(service_v1, name) for name in required)


def _archive_points(*, include_second_segment: bool = True):
    points = [
        make_point(0, event_at=BASE, sensor_id="s1", pair_key="a"),
        make_point(1, event_at=BASE, sensor_id="s2", pair_key="a"),
        make_point(
            2,
            event_at=BASE + timedelta(seconds=10),
            sensor_id="s1",
            pair_key="b",
        ),
        make_point(
            3,
            event_at=BASE + timedelta(seconds=10),
            sensor_id="s2",
            pair_key="b",
        ),
    ]
    if include_second_segment:
        points.extend(
            (
                make_point(
                    4,
                    event_at=BASE + timedelta(seconds=40),
                    sensor_id="s1",
                    pair_key="c",
                ),
                make_point(
                    5,
                    event_at=BASE + timedelta(seconds=40),
                    sensor_id="s2",
                    pair_key="c",
                ),
            )
        )
    return tuple(sorted(points, key=timeline_order_key_v1))


def _query_for_point(point_id: str):
    Query, *_ = _context_api()
    return Query(
        asset_id="forzy-motor-01",
        point_id=point_id,
        at=None,
        segment_id=None,
    )


def _query_for_at(at: datetime, segment_id: str):
    Query, *_ = _context_api()
    return Query(
        asset_id="forzy-motor-01",
        point_id=None,
        at=at,
        segment_id=segment_id,
    )


def test_context_query_requires_exactly_point_or_at_with_segment() -> None:
    Query, QueryInvalid, *_ = _context_api()
    valid_point = uuid5_text("context-query-point")
    valid_segment = uuid5_text("context-query-segment")

    Query(
        asset_id="forzy-motor-01",
        point_id=valid_point,
        at=None,
        segment_id=None,
    )
    Query(
        asset_id="forzy-motor-01",
        point_id=None,
        at=BASE,
        segment_id=valid_segment,
    )

    invalid = (
        (None, None, None),
        (valid_point, BASE, valid_segment),
        (None, BASE, None),
        (None, None, valid_segment),
        ("not-a-uuid", None, None),
        (None, BASE, "not-a-uuid"),
        (None, BASE.replace(microsecond=1), valid_segment),
    )
    for point_id, at, segment_id in invalid:
        with pytest.raises(QueryInvalid):
            Query(
                asset_id="forzy-motor-01",
                point_id=point_id,
                at=at,
                segment_id=segment_id,
            )


def test_point_context_returns_only_the_exact_pair_and_no_assessment_claim() -> None:
    points = _archive_points()
    repository = FakeTimelineRepositoryV1(archive=points)
    service = service_v1.TimelineServiceV1(repository)
    anchor = points[2]

    context = service.context(_query_for_point(str(anchor.point_id)))
    payload = context.model_dump_public()

    validate_timeline_public_v1("timeline-context", payload)
    assert payload["anchor"]["pointId"] == str(anchor.point_id)
    assert {
        payload["channels"][sensor]["samplePairId"]
        for sensor in ("s1", "s2")
    } == {str(anchor.sample_pair_id)}
    assert payload["assessment"] is None
    assert payload["decisionFacts"] == {
        "schemaVersion": "1.0",
        "conditionState": "unknown",
        "conditionTemporalScope": "none",
        "conditionAsOf": None,
        "conditionEpisodeStartedAt": None,
        "conditionSource": "none",
        "collectionState": "historical_context",
        "collectionExpectation": "not_applicable",
        "dataAvailability": "complete",
        "dataFreshness": "historical",
        "dataTrust": "sufficient",
    }
    assert payload["provenance"]["assessmentSource"] == "none"
    assert payload["capabilities"] == {
        "historicalNavigation": True,
        "pairedChannels": True,
        "causalAssessment": False,
        "baselineComparison": False,
        "previousCycleComparison": False,
    }
    assert payload["limitations"] == ["causal_assessment_not_available"]
    assert repository.pair_reads == [
        ("forzy-motor-01", str(anchor.sample_pair_id))
    ]
    assert repository.point_reads == [
        ("forzy-motor-01", str(anchor.point_id))
    ]


def test_context_keeps_an_exact_missing_channel_null_without_carry_forward() -> None:
    anchor = make_point(10, event_at=BASE, sensor_id="s1", pair_key="partial")
    unrelated = make_point(
        11,
        event_at=BASE - timedelta(seconds=1),
        sensor_id="s2",
        pair_key="previous",
    )
    points = tuple(sorted((unrelated, anchor), key=timeline_order_key_v1))
    context = service_v1.TimelineServiceV1(
        FakeTimelineRepositoryV1(archive=points)
    ).context(_query_for_point(str(anchor.point_id)))
    payload = context.model_dump_public()

    assert payload["channels"]["s1"]["pointId"] == str(anchor.point_id)
    assert payload["channels"]["s2"] is None
    assert payload["decisionFacts"]["dataAvailability"] == "partial"
    assert payload["decisionFacts"]["dataTrust"] == "degraded"
    assert payload["capabilities"]["pairedChannels"] is False


def test_at_selection_uses_the_greatest_full_original_order_key() -> None:
    points = _archive_points()
    repository = FakeTimelineRepositoryV1(archive=points)
    service = service_v1.TimelineServiceV1(repository)
    overview = service.overview(
        service_v1.TimelineOverviewQueryV1(
            asset_id="forzy-motor-01",
            from_at=None,
            to_at=None,
            sensor_ids=("s1", "s2"),
        )
    )
    first_segment = overview.segments[0]
    expected = max(
        (
            point
            for point in points
            if point.event_at <= BASE + timedelta(seconds=10)
            and first_segment.start_at <= point.event_at <= first_segment.end_at
        ),
        key=timeline_order_key_v1,
    )

    context = service.context(
        _query_for_at(
            BASE + timedelta(seconds=10), str(first_segment.segment_id)
        )
    )

    assert context.anchor is not None
    assert context.anchor.point_id == expected.point_id
    assert context.selected_at == BASE + timedelta(seconds=10)


def test_open_gap_is_empty_from_either_adjacent_segment_and_endpoints_are_owned() -> None:
    points = _archive_points()
    service = service_v1.TimelineServiceV1(
        FakeTimelineRepositoryV1(archive=points)
    )
    overview = service.overview(
        service_v1.TimelineOverviewQueryV1(
            asset_id="forzy-motor-01",
            from_at=None,
            to_at=None,
            sensor_ids=("s1", "s2"),
        )
    )
    left, right = overview.segments

    for adjacent_id in (str(left.segment_id), str(right.segment_id)):
        payload = service.context(
            _query_for_at(BASE + timedelta(seconds=20), adjacent_id)
        ).model_dump_public()
        validate_timeline_public_v1("timeline-context", payload)
        assert payload["selectedAt"] == "2026-08-25T15:00:20.000Z"
        assert payload["segmentId"] is None
        assert payload["anchor"] is None
        assert payload["channels"] == {"s1": None, "s2": None}
        assert payload["assessment"] is None
        assert payload["limitations"] == ["timeline_coverage_gap"]
        assert payload["capabilities"] == {
            "historicalNavigation": True,
            "pairedChannels": False,
            "causalAssessment": False,
            "baselineComparison": False,
            "previousCycleComparison": False,
        }

    at_left = service.context(_query_for_at(left.end_at, str(left.segment_id)))
    at_right = service.context(_query_for_at(right.start_at, str(right.segment_id)))
    assert at_left.anchor is not None and at_left.anchor.event_at == left.end_at
    assert at_right.anchor is not None and at_right.anchor.event_at == right.start_at


def test_unknown_point_segment_and_outside_selection_raise_named_errors() -> None:
    (
        _,
        _,
        _,
        PointNotFound,
        SegmentNotFound,
        SelectionOutside,
    ) = _context_api()
    points = _archive_points()
    service = service_v1.TimelineServiceV1(
        FakeTimelineRepositoryV1(archive=points)
    )

    with pytest.raises(PointNotFound):
        service.context(_query_for_point(uuid5_text("unknown-point")))
    with pytest.raises(SegmentNotFound):
        service.context(
            _query_for_at(BASE, uuid5_text("unknown-segment"))
        )

    overview = service.overview(
        service_v1.TimelineOverviewQueryV1(
            asset_id="forzy-motor-01",
            from_at=None,
            to_at=None,
            sensor_ids=("s1", "s2"),
        )
    )
    with pytest.raises(SelectionOutside):
        service.context(
            _query_for_at(
                BASE - timedelta(milliseconds=1),
                str(overview.segments[0].segment_id),
            )
        )


def test_crossed_exact_pair_evidence_fails_closed() -> None:
    *_, RepositoryError, _, _, _ = _context_api()
    s1 = make_point(20, event_at=BASE, sensor_id="s1", pair_key="crossed")
    s2 = make_point(
        21,
        event_at=BASE + timedelta(seconds=1),
        sensor_id="s2",
        pair_key="crossed",
    )
    points = tuple(sorted((s1, s2), key=timeline_order_key_v1))

    with pytest.raises(RepositoryError):
        service_v1.TimelineServiceV1(
            FakeTimelineRepositoryV1(archive=points)
        ).context(_query_for_point(str(s1.point_id)))
