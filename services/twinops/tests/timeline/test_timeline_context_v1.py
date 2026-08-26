from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from twinops.contracts.timeline_v1_models import (
    TimelinePointV1,
    validate_timeline_public_v1,
)
from twinops.timeline import service_v1
from twinops.timeline.repository_v1 import timeline_order_key_v1

from overview_fixtures_v1 import (
    FakeTimelineRepositoryV1,
    make_point,
    make_policy,
    uuid5_text,
)


BASE = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
LOW_PAIR_ID = "00000000-0000-5000-8000-000000000010"
HIGH_PAIR_ID = "00000000-0000-5000-8000-000000000020"
FUTURE_PAIR_ID = "00000000-0000-5000-8000-000000000030"
EXPECTED_TIED_ANCHOR_ID = "00000000-0000-5000-8000-000000000002"


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


class _BatchChangingPairRepositoryV1(FakeTimelineRepositoryV1):
    def __init__(self, *, archive: tuple[TimelinePointV1, ...]) -> None:
        super().__init__(archive=archive)
        self.active_batch_id_calls_before_pair: int | None = None

    def points_for_pair(self, asset_id: str, sample_pair_id: str):
        self.active_batch_id_calls_before_pair = self.active_batch_id_calls
        pair = super().points_for_pair(asset_id, sample_pair_id)
        self.batch_id = "sha256:" + "c" * 64
        return pair


def test_point_context_uses_only_metadata_active_batch_guards() -> None:
    points = _archive_points(include_second_segment=False)
    repository = FakeTimelineRepositoryV1(archive=points)
    service = service_v1.TimelineServiceV1(repository)

    context = service.context(_query_for_point(str(points[0].point_id)))

    assert context.provenance.active_historical_batch_id == repository.batch_id
    assert repository.active_batch_id_calls == 4
    assert repository.assessment_anchor_reads == [
        (repository.batch_id, str(points[0].point_id))
    ]


def test_point_context_reuses_the_archive_warmed_by_overview() -> None:
    points = _archive_points(include_second_segment=False)
    repository = FakeTimelineRepositoryV1(archive=points)
    service = service_v1.TimelineServiceV1(repository)
    service.overview(
        service_v1.TimelineOverviewQueryV1(
            asset_id="forzy-motor-01",
            from_at=None,
            to_at=None,
            sensor_ids=("s1", "s2"),
            metric="temperature",
            max_points=40,
        )
    )
    archive_reads_after_warm = len(repository.archive_reads)

    context = service.context(_query_for_point(str(points[0].point_id)))

    assert str(context.anchor.point_id) == str(points[0].point_id)
    assert len(repository.archive_reads) == archive_reads_after_warm


def test_point_context_detects_active_batch_change_during_pair_read() -> None:
    points = _archive_points(include_second_segment=False)
    repository = _BatchChangingPairRepositoryV1(archive=points)
    service = service_v1.TimelineServiceV1(repository)

    with pytest.raises(service_v1.TimelineOverviewSnapshotConflictV1):
        service.context(_query_for_point(str(points[0].point_id)))

    assert repository.active_batch_id_calls_before_pair == 2
    assert repository.active_batch_id_calls == 3
    assert repository.pair_reads == [
        ("forzy-motor-01", str(points[0].sample_pair_id))
    ]


def test_warm_archive_cache_preserves_the_pair_activation_race_guard() -> None:
    points = _archive_points(include_second_segment=False)
    repository = _BatchChangingPairRepositoryV1(archive=points)
    service = service_v1.TimelineServiceV1(repository)
    service.overview(
        service_v1.TimelineOverviewQueryV1(
            asset_id="forzy-motor-01",
            from_at=None,
            to_at=None,
            sensor_ids=("s1", "s2"),
            metric="temperature",
            max_points=40,
        )
    )
    archive_reads_after_warm = len(repository.archive_reads)

    with pytest.raises(service_v1.TimelineOverviewSnapshotConflictV1):
        service.context(_query_for_point(str(points[0].point_id)))

    assert len(repository.archive_reads) == archive_reads_after_warm
    assert repository.active_batch_id_calls_before_pair == 4
    assert repository.active_batch_id_calls == 5


def _point_with_adversarial_identity(
    index: int,
    *,
    event_at: datetime,
    sensor_id: str,
    sample_pair_id: str,
    point_id: str,
) -> TimelinePointV1:
    payload = make_point(
        index,
        event_at=event_at,
        sensor_id=sensor_id,
        pair_key=f"adversarial-{index}",
    ).model_dump_public()
    payload["samplePairId"] = sample_pair_id
    payload["pointId"] = point_id
    return TimelinePointV1.model_validate(payload)


def _adversarial_order_points() -> tuple[TimelinePointV1, ...]:
    tied = (
        _point_with_adversarial_identity(
            40,
            event_at=BASE,
            sensor_id="s1",
            sample_pair_id=LOW_PAIR_ID,
            point_id="00000000-0000-5000-8000-000000000090",
        ),
        _point_with_adversarial_identity(
            41,
            event_at=BASE,
            sensor_id="s2",
            sample_pair_id=LOW_PAIR_ID,
            point_id="00000000-0000-5000-8000-000000000099",
        ),
        _point_with_adversarial_identity(
            42,
            event_at=BASE,
            sensor_id="s1",
            sample_pair_id=HIGH_PAIR_ID,
            point_id="00000000-0000-5000-8000-000000000001",
        ),
        _point_with_adversarial_identity(
            43,
            event_at=BASE,
            sensor_id="s2",
            sample_pair_id=HIGH_PAIR_ID,
            point_id=EXPECTED_TIED_ANCHOR_ID,
        ),
    )
    future = (
        _point_with_adversarial_identity(
            44,
            event_at=BASE + timedelta(milliseconds=2),
            sensor_id="s1",
            sample_pair_id=FUTURE_PAIR_ID,
            point_id="00000000-0000-5000-8000-000000000003",
        ),
        _point_with_adversarial_identity(
            45,
            event_at=BASE + timedelta(milliseconds=2),
            sensor_id="s2",
            sample_pair_id=FUTURE_PAIR_ID,
            point_id="00000000-0000-5000-8000-000000000004",
        ),
    )
    return tuple(sorted((*tied, *future), key=timeline_order_key_v1))


def _adversarial_service_and_segment():
    service = service_v1.TimelineServiceV1(
        FakeTimelineRepositoryV1(archive=_adversarial_order_points())
    )
    overview = service.overview(
        service_v1.TimelineOverviewQueryV1(
            asset_id="forzy-motor-01",
            from_at=None,
            to_at=None,
            sensor_ids=("s1", "s2"),
        )
    )
    assert len(overview.segments) == 1
    return service, str(overview.segments[0].segment_id)


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


def test_at_selection_uses_sample_pair_and_sensor_before_opposed_point_id() -> None:
    service, segment_id = _adversarial_service_and_segment()

    context = service.context(_query_for_at(BASE, segment_id))

    assert context.anchor is not None
    assert str(context.anchor.point_id) == EXPECTED_TIED_ANCHOR_ID
    assert str(context.anchor.sample_pair_id) == HIGH_PAIR_ID
    assert context.anchor.sensor_id == "s2"


def test_at_selection_between_instants_never_uses_the_nearest_future_pair() -> None:
    service, segment_id = _adversarial_service_and_segment()
    selected_at = BASE + timedelta(milliseconds=1)

    context = service.context(_query_for_at(selected_at, segment_id))

    assert context.anchor is not None
    assert str(context.anchor.point_id) == EXPECTED_TIED_ANCHOR_ID
    assert context.anchor.event_at == BASE
    assert context.selected_at == selected_at


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


def test_live_pair_allows_distinct_receipt_instants_for_one_scheduled_sample() -> None:
    scheduled_at = BASE
    s1_payload = make_point(
        30,
        event_at=BASE + timedelta(seconds=5, milliseconds=201),
        sensor_id="s1",
        source_kind="live_collection",
        pair_key="live-receipt-skew",
    ).model_dump_public()
    s2_payload = make_point(
        31,
        event_at=BASE + timedelta(seconds=5, milliseconds=278),
        sensor_id="s2",
        source_kind="live_collection",
        pair_key="live-receipt-skew",
    ).model_dump_public()
    scheduled_text = service_v1.serialize_public_utc_millis_v1(scheduled_at)
    s1_payload["provenance"]["scheduledAt"] = scheduled_text
    s2_payload["provenance"]["scheduledAt"] = scheduled_text
    points = tuple(
        sorted(
            (
                TimelinePointV1.model_validate(s1_payload),
                TimelinePointV1.model_validate(s2_payload),
            ),
            key=timeline_order_key_v1,
        )
    )

    context = service_v1.TimelineServiceV1(
        FakeTimelineRepositoryV1(
            live=points,
            policies=(make_policy(),),
            batch_id=None,
        )
    ).context(_query_for_point(str(points[0].point_id)))

    assert context.channels.s1 is not None
    assert context.channels.s2 is not None
    assert context.channels.s1.event_at != context.channels.s2.event_at
    assert context.selected_at == points[0].event_at
