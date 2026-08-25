from datetime import datetime, timedelta, timezone
from importlib.util import find_spec

import pytest

from twinops.contracts.timeline_v1_models import TimelineOverviewV1, TimelinePointV1
from twinops.timeline.repository_v1 import timeline_order_key_v1

from overview_fixtures_v1 import (
    BATCH_A,
    FakeTimelineRepositoryV1,
    make_point,
    make_policy,
    uuid5_text,
)


_OVERVIEW_MODULES = (
    "twinops.timeline.ranges_v1",
    "twinops.timeline.segments_v1",
    "twinops.timeline.downsample_v1",
    "twinops.timeline.service_v1",
)


def test_timeline_overview_foundation_exists() -> None:
    assert all(find_spec(module) is not None for module in _OVERVIEW_MODULES), (
        "RED:VS2A:timeline-overview-missing"
    )


def _service(repository):
    from twinops.timeline.service_v1 import TimelineServiceV1

    return TimelineServiceV1(repository)


def _query(**changes):
    from twinops.timeline.service_v1 import TimelineOverviewQueryV1

    values = {
        "asset_id": "forzy-motor-01",
        "from_at": None,
        "to_at": None,
        "sensor_ids": ("s1", "s2"),
        "metric": "temperature",
        "max_points": 40,
    }
    return TimelineOverviewQueryV1(**(values | changes))


@pytest.mark.parametrize(
    "change",
    (
        {"asset_id": "other"},
        {"from_at": datetime(2026, 8, 22, 12)},
        {"to_at": datetime(2026, 8, 22, 12)},
        {
            "from_at": datetime(
                2026, 8, 22, 12, 0, 0, 1, tzinfo=timezone.utc
            )
        },
        {
            "from_at": datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
            "to_at": datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
        },
        {"sensor_ids": ()},
        {"sensor_ids": ("s2", "s1")},
        {"sensor_ids": ("s1", "s1")},
        {"sensor_ids": ["s1"]},
        {"metric": "rpm"},
        {"max_points": 39},
        {"max_points": 4001},
        {"max_points": True},
        {"max_points": 40.0},
    ),
)
def test_overview_query_is_strict_and_closed(change) -> None:
    with pytest.raises(ValueError):
        _query(**change)


def test_empty_and_bounded_no_result_overviews_are_honest_and_validated() -> None:
    empty_repository = FakeTimelineRepositoryV1(batch_id=None)
    empty = _service(empty_repository).overview(_query())

    assert isinstance(empty, TimelineOverviewV1)
    assert empty.effective_range is None
    assert empty.available_range is None
    assert empty.segments == []
    assert empty.gaps == []
    assert empty.operating_cycles == []
    assert empty.series == []
    assert empty.event_candidates == []
    assert empty.aggregation_summary.original_point_count == 0
    assert empty.capabilities.historical is False
    assert empty.capabilities.live is True

    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    point = make_point(1, event_at=start, source_kind="live_collection")
    policy = make_policy()
    repository = FakeTimelineRepositoryV1(
        live=(point,), policies=(policy,), batch_id=None
    )
    no_result = _service(repository).overview(
        _query(
            from_at=start + timedelta(hours=1),
            to_at=start + timedelta(hours=2),
        )
    )
    assert no_result.effective_range is None
    assert no_result.available_range.from_ == start
    assert no_result.available_range.to == start + timedelta(milliseconds=1)
    assert no_result.segments == []
    assert repository.policy_reads == [{policy.collection_policy_id}]


def test_unified_overview_is_fully_validated_read_only_and_byte_deterministic() -> None:
    archive_start = datetime(2026, 8, 12, 14, 58, tzinfo=timezone.utc)
    live_start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    cycle_id = uuid5_text("unified-cycle")
    archive = tuple(
        sorted(
            (
                make_point(
                    10,
                    event_at=archive_start,
                    sensor_id="s1",
                    pair_key="archive-pair",
                    cycle_id=cycle_id,
                    temperature=-2,
                ),
                make_point(
                    11,
                    event_at=archive_start,
                    sensor_id="s2",
                    pair_key="archive-pair",
                    cycle_id=cycle_id,
                    temperature=0,
                ),
            ),
            key=timeline_order_key_v1,
        )
    )
    live = tuple(
        sorted(
            (
                make_point(
                    12,
                    event_at=live_start,
                    sensor_id="s1",
                    source_kind="live_collection",
                    pair_key="live-pair",
                    temperature=5,
                ),
                make_point(
                    13,
                    event_at=live_start,
                    sensor_id="s2",
                    source_kind="live_collection",
                    pair_key="live-pair",
                    temperature=6,
                ),
            ),
            key=timeline_order_key_v1,
        )
    )
    policy = make_policy()
    repository = FakeTimelineRepositoryV1(
        archive=archive,
        live=live,
        policies=(policy,),
    )
    service = _service(repository)

    first = service.overview(_query())
    second = service.overview(_query())
    payload = first.model_dump_public()

    assert TimelineOverviewV1.model_validate(payload) == first
    assert first.model_dump_public_json() == second.model_dump_public_json()
    assert first.event_candidates == []
    assert [gap.gap_type for gap in first.gaps] == ["source_discontinuity"]
    assert first.aggregation_summary.original_point_count == 4
    assert first.aggregation_summary.returned_point_count == 4
    assert first.aggregation_summary.omitted_point_count == 0
    assert len(first.operating_cycles) == 1
    assert first.operating_cycles[0].candidate_count == 0
    assert repository.policy_reads == [
        {policy.collection_policy_id},
        {policy.collection_policy_id},
    ]
    assert not hasattr(service, "_scorer")
    assert not hasattr(service, "_model")


def test_narrow_zoom_returns_the_exact_original_without_reduction() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    archive = tuple(
        make_point(index, event_at=start + timedelta(seconds=10 * index))
        for index in range(3)
    )
    repository = FakeTimelineRepositoryV1(archive=archive)
    service = _service(repository)

    full = service.overview(_query(sensor_ids=("s1",)))

    overview = service.overview(
        _query(
            sensor_ids=("s1",),
            from_at=start + timedelta(seconds=10),
            to_at=start + timedelta(seconds=10, milliseconds=1),
        )
    )

    assert overview.requested_range.from_ == start + timedelta(seconds=10)
    assert overview.effective_range.from_ == start + timedelta(seconds=10)
    assert overview.effective_range.to == start + timedelta(
        seconds=10, milliseconds=1
    )
    assert overview.aggregation_summary.original_point_count == 1
    assert overview.aggregation_summary.returned_point_count == 1
    assert overview.series[0].aggregation.method == "none"
    assert overview.series[0].points[0].point_id == archive[1].point_id
    assert overview.segments[0].segment_id == full.segments[0].segment_id

    from twinops.timeline.segments_v1 import build_timeline_coverage_v1

    recomputed = build_timeline_coverage_v1(
        archive,
        active_batch_id=BATCH_A,
        policies={},
    )
    assert str(overview.segments[0].segment_id) == recomputed.point_segment_ids[
        str(archive[1].point_id)
    ]


def test_sensor_filter_does_not_change_global_segment_identity() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    archive = tuple(
        sorted(
            (
                make_point(10, event_at=start, sensor_id="s1", pair_key="a"),
                make_point(
                    11,
                    event_at=start + timedelta(seconds=10),
                    sensor_id="s2",
                    pair_key="b",
                ),
            ),
            key=timeline_order_key_v1,
        )
    )
    service = _service(FakeTimelineRepositoryV1(archive=archive))

    unified = service.overview(_query(sensor_ids=("s1", "s2")))
    s1_only = service.overview(_query(sensor_ids=("s1",)))
    s2_only = service.overview(_query(sensor_ids=("s2",)))

    assert unified.segments[0].segment_id == s1_only.segments[0].segment_id
    assert unified.segments[0].segment_id == s2_only.segments[0].segment_id


def test_sensor_projection_uses_only_visible_originals_for_segment_facts() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    archive = tuple(
        sorted(
            (
                make_point(12, event_at=start, sensor_id="s2", pair_key="a"),
                make_point(
                    13,
                    event_at=start + timedelta(seconds=5),
                    sensor_id="s1",
                    pair_key="b",
                ),
                make_point(
                    14,
                    event_at=start + timedelta(seconds=10),
                    sensor_id="s2",
                    pair_key="c",
                ),
            ),
            key=timeline_order_key_v1,
        )
    )
    service = _service(FakeTimelineRepositoryV1(archive=archive))
    range_query = {
        "from_at": start,
        "to_at": start + timedelta(seconds=10, milliseconds=1),
    }

    unified = service.overview(
        _query(sensor_ids=("s1", "s2"), **range_query)
    )
    s1_only = service.overview(_query(sensor_ids=("s1",), **range_query))
    s2_only = service.overview(_query(sensor_ids=("s2",), **range_query))
    narrow = service.overview(
        _query(
            sensor_ids=("s1",),
            from_at=start + timedelta(seconds=5),
            to_at=start + timedelta(seconds=5, milliseconds=1),
        )
    )
    unified_again = service.overview(
        _query(sensor_ids=("s1", "s2"), **range_query)
    )
    s1_again = service.overview(_query(sensor_ids=("s1",), **range_query))
    s2_again = service.overview(_query(sensor_ids=("s2",), **range_query))

    assert s1_only.segments[0].segment_id == unified.segments[0].segment_id
    assert s2_only.segments[0].segment_id == unified.segments[0].segment_id
    assert narrow.segments[0].segment_id == unified.segments[0].segment_id
    assert s1_only.segments[0].start_at == start + timedelta(seconds=5)
    assert s1_only.segments[0].end_at == start + timedelta(seconds=5)
    assert s1_only.segments[0].total_points == 1
    assert s1_only.segments[0].sensor_counts.model_dump() == {"s1": 1, "s2": 0}
    assert len(s1_only.series) == 1
    assert s1_only.series[0].sensor_id == "s1"
    assert [point.point_id for point in s1_only.series[0].points] == [
        archive[1].point_id
    ]
    assert unified.model_dump_public_json() == unified_again.model_dump_public_json()
    assert s1_only.model_dump_public_json() == s1_again.model_dump_public_json()
    assert s2_only.model_dump_public_json() == s2_again.model_dump_public_json()


def test_sensor_projection_rebuilds_one_archive_gap_across_hidden_segments() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    archive = (
        make_point(15, event_at=start, sensor_id="s1", pair_key="a"),
        make_point(
            16,
            event_at=start + timedelta(seconds=30),
            sensor_id="s2",
            pair_key="b",
        ),
        make_point(
            17,
            event_at=start + timedelta(seconds=60),
            sensor_id="s1",
            pair_key="c",
        ),
    )
    service = _service(FakeTimelineRepositoryV1(archive=archive))

    unified = service.overview(_query(sensor_ids=("s1", "s2")))
    s1_only = service.overview(_query(sensor_ids=("s1",)))

    assert [segment.segment_id for segment in s1_only.segments] == [
        unified.segments[0].segment_id,
        unified.segments[2].segment_id,
    ]
    assert len(s1_only.gaps) == 1
    gap = s1_only.gaps[0]
    assert gap.gap_type == "archive_sampling_gap"
    assert gap.left_segment_id == s1_only.segments[0].segment_id
    assert gap.right_segment_id == s1_only.segments[1].segment_id
    assert gap.start_at == start
    assert gap.end_at == start + timedelta(seconds=60)
    assert [row.segment_id for row in s1_only.series] == [
        s1_only.segments[0].segment_id,
        s1_only.segments[1].segment_id,
    ]


def test_sensor_projection_keeps_source_boundary_with_hidden_points() -> None:
    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    policy = make_policy()
    repository = FakeTimelineRepositoryV1(
        archive=(
            make_point(18, event_at=start, sensor_id="s1", pair_key="a"),
            make_point(
                19,
                event_at=start + timedelta(seconds=10),
                sensor_id="s2",
                pair_key="b",
            ),
        ),
        live=(
            make_point(
                20,
                event_at=start + timedelta(seconds=30),
                sensor_id="s2",
                source_kind="live_collection",
                pair_key="c",
            ),
            make_point(
                21,
                event_at=start + timedelta(seconds=40),
                sensor_id="s1",
                source_kind="live_collection",
                pair_key="d",
            ),
        ),
        policies=(policy,),
    )
    service = _service(repository)

    unified = service.overview(_query(sensor_ids=("s1", "s2")))
    s1_only = service.overview(_query(sensor_ids=("s1",)))

    assert [segment.segment_id for segment in s1_only.segments] == [
        segment.segment_id for segment in unified.segments
    ]
    assert len(s1_only.gaps) == 1
    gap = s1_only.gaps[0]
    assert gap.gap_type == "source_discontinuity"
    assert gap.left_segment_id == s1_only.segments[0].segment_id
    assert gap.right_segment_id == s1_only.segments[1].segment_id
    assert gap.start_at == start
    assert gap.end_at == start + timedelta(seconds=40)
    assert [row.source_kind for row in s1_only.series] == [
        "historical_archive",
        "live_collection",
    ]
    assert [row.segment_id for row in s1_only.series] == [
        s1_only.segments[0].segment_id,
        s1_only.segments[1].segment_id,
    ]


@pytest.mark.parametrize(
    ("start", "policy_id", "gap_type"),
    (
        (
            datetime(2026, 8, 12, 15, tzinfo=timezone.utc),
            "forzy-live-window-v1",
            "live_expected_collection_gap",
        ),
        (
            datetime(2026, 8, 12, 17, tzinfo=timezone.utc),
            "forzy-live-window-v1",
            "expected_idle",
        ),
        (
            datetime(2026, 8, 12, 15, tzinfo=timezone.utc),
            None,
            "unclassified_coverage_gap",
        ),
    ),
)
def test_sensor_projection_classifies_live_gap_with_hidden_boundary_points(
    start, policy_id, gap_type
) -> None:
    policy = make_policy()
    live = tuple(
        sorted(
            (
                make_point(
                    22,
                    event_at=start,
                    sensor_id="s1",
                    source_kind="live_collection",
                    policy_id=policy_id,
                    pair_key="a",
                ),
                make_point(
                    23,
                    event_at=start + timedelta(seconds=5),
                    sensor_id="s2",
                    source_kind="live_collection",
                    policy_id=policy_id,
                    pair_key="b",
                ),
                make_point(
                    24,
                    event_at=start + timedelta(seconds=25),
                    sensor_id="s2",
                    source_kind="live_collection",
                    policy_id=policy_id,
                    pair_key="c",
                ),
                make_point(
                    25,
                    event_at=start + timedelta(seconds=30),
                    sensor_id="s1",
                    source_kind="live_collection",
                    policy_id=policy_id,
                    pair_key="d",
                ),
            ),
            key=timeline_order_key_v1,
        )
    )
    repository = FakeTimelineRepositoryV1(
        live=live,
        policies=() if policy_id is None else (policy,),
        batch_id=None,
    )
    service = _service(repository)

    unified = service.overview(_query(sensor_ids=("s1", "s2")))
    s1_only = service.overview(_query(sensor_ids=("s1",)))

    expected_ids = [
        segment.segment_id
        for segment in unified.segments
        if segment.sensor_counts.s1 > 0
    ]
    assert [segment.segment_id for segment in s1_only.segments] == expected_ids
    assert len(s1_only.gaps) == 1
    gap = s1_only.gaps[0]
    assert gap.gap_type == gap_type
    assert gap.left_segment_id == s1_only.segments[0].segment_id
    assert gap.right_segment_id == s1_only.segments[1].segment_id
    assert gap.start_at == start
    assert gap.end_at == start + timedelta(seconds=30)
    gap_payload = gap.model_dump_public()
    identity = "|".join(
        (
            "timeline-gap-v1",
            gap_payload["gapType"],
            gap_payload["leftSegmentId"],
            gap_payload["rightSegmentId"],
            gap_payload["startAt"],
            gap_payload["endAt"],
            gap_payload["ruleVersion"],
        )
    )
    assert str(gap.gap_id) == uuid5_text(identity)


def test_sensor_projection_fails_before_validation_for_mixed_live_schedule() -> None:
    from twinops.timeline.segments_v1 import (
        TimelineProjectedGapUnrepresentableV1,
    )

    start = datetime(2026, 8, 12, 16, 59, 50, tzinfo=timezone.utc)
    policy = make_policy()
    live = tuple(
        sorted(
            (
                make_point(
                    26,
                    event_at=start,
                    sensor_id="s1",
                    source_kind="live_collection",
                    pair_key="a",
                ),
                make_point(
                    27,
                    event_at=start + timedelta(seconds=10),
                    sensor_id="s2",
                    source_kind="live_collection",
                    pair_key="b",
                ),
                make_point(
                    28,
                    event_at=start + timedelta(seconds=30),
                    sensor_id="s2",
                    source_kind="live_collection",
                    pair_key="c",
                ),
                make_point(
                    29,
                    event_at=start + timedelta(seconds=40),
                    sensor_id="s1",
                    source_kind="live_collection",
                    pair_key="d",
                ),
            ),
            key=timeline_order_key_v1,
        )
    )
    service = _service(
        FakeTimelineRepositoryV1(
            live=live,
            policies=(policy,),
            batch_id=None,
        )
    )

    with pytest.raises(
        TimelineProjectedGapUnrepresentableV1,
        match="timeline_projected_live_gap_crosses_policy_windows",
    ):
        service.overview(_query(sensor_ids=("s1",)))


def test_sensor_projection_fails_closed_for_mixed_hidden_gap_evidence() -> None:
    from twinops.timeline.segments_v1 import (
        TimelineProjectedGapUnrepresentableV1,
    )

    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    policy = make_policy()
    live = (
        make_point(
            30,
            event_at=start,
            sensor_id="s1",
            source_kind="live_collection",
            pair_key="a",
        ),
        make_point(
            31,
            event_at=start + timedelta(seconds=20),
            sensor_id="s2",
            source_kind="live_collection",
            policy_id=None,
            pair_key="b",
        ),
        make_point(
            32,
            event_at=start + timedelta(seconds=40),
            sensor_id="s1",
            source_kind="live_collection",
            pair_key="c",
        ),
    )
    policy_service = _service(
        FakeTimelineRepositoryV1(
            live=live,
            policies=(policy,),
            batch_id=None,
        )
    )
    policy_service.overview(_query(sensor_ids=("s1", "s2")))
    with pytest.raises(
        TimelineProjectedGapUnrepresentableV1,
        match="timeline_projected_live_policy_evidence_unrepresentable",
    ):
        policy_service.overview(_query(sensor_ids=("s1",)))

    source_service = _service(
        FakeTimelineRepositoryV1(
            archive=(
                make_point(33, event_at=start, sensor_id="s1", pair_key="d"),
                make_point(
                    34,
                    event_at=start + timedelta(seconds=30),
                    sensor_id="s2",
                    pair_key="e",
                ),
            ),
            live=(
                make_point(
                    35,
                    event_at=start + timedelta(seconds=60),
                    sensor_id="s1",
                    source_kind="live_collection",
                    pair_key="f",
                ),
            ),
            policies=(policy,),
        )
    )
    source_service.overview(_query(sensor_ids=("s1", "s2")))
    with pytest.raises(
        TimelineProjectedGapUnrepresentableV1,
        match="timeline_projected_gap_mixed_classification",
    ):
        source_service.overview(_query(sensor_ids=("s1",)))


def test_archive_gap_remains_explicit_at_leading_and_trailing_range_edges() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    midpoint = start + timedelta(seconds=30)
    right_at = start + timedelta(seconds=60)
    archive = (
        make_point(30, event_at=start, sensor_id="s1", cycle_id=uuid5_text("a")),
        make_point(
            31,
            event_at=right_at,
            sensor_id="s1",
            cycle_id=uuid5_text("b"),
        ),
    )
    service = _service(FakeTimelineRepositoryV1(archive=archive))

    full = service.overview(_query(sensor_ids=("s1",)))
    leading = service.overview(
        _query(
            sensor_ids=("s1",),
            from_at=midpoint,
            to_at=right_at + timedelta(milliseconds=1),
        )
    )
    trailing = service.overview(
        _query(sensor_ids=("s1",), from_at=start, to_at=midpoint)
    )

    assert [gap.gap_type for gap in full.gaps] == ["archive_sampling_gap"]
    assert leading.segments[0].segment_id == full.segments[1].segment_id
    assert leading.gaps[0].left_segment_id is None
    assert leading.gaps[0].right_segment_id == full.segments[1].segment_id
    assert leading.gaps[0].start_at == midpoint
    assert leading.gaps[0].end_at == right_at
    assert trailing.segments[0].segment_id == full.segments[0].segment_id
    assert trailing.gaps[0].left_segment_id == full.segments[0].segment_id
    assert trailing.gaps[0].right_segment_id is None
    assert trailing.gaps[0].start_at == start
    assert trailing.gaps[0].end_at == midpoint


def test_source_and_live_gaps_remain_explicit_at_both_range_edges() -> None:
    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    policy = make_policy()
    cases = (
        (
            "source_discontinuity",
            start + timedelta(seconds=60),
            FakeTimelineRepositoryV1(
                archive=(make_point(40, event_at=start),),
                live=(
                    make_point(
                        41,
                        event_at=start + timedelta(seconds=60),
                        source_kind="live_collection",
                    ),
                ),
                policies=(policy,),
            ),
        ),
        (
            "live_expected_collection_gap",
            start + timedelta(seconds=20),
            FakeTimelineRepositoryV1(
                live=(
                    make_point(42, event_at=start, source_kind="live_collection"),
                    make_point(
                        43,
                        event_at=start + timedelta(seconds=20),
                        source_kind="live_collection",
                    ),
                ),
                policies=(policy,),
                batch_id=None,
            ),
        ),
    )

    for gap_type, right_at, repository in cases:
        midpoint = start + (right_at - start) / 2
        service = _service(repository)
        full = service.overview(_query(sensor_ids=("s1",)))
        leading = service.overview(
            _query(
                sensor_ids=("s1",),
                from_at=midpoint,
                to_at=right_at + timedelta(milliseconds=1),
            )
        )
        trailing = service.overview(
            _query(sensor_ids=("s1",), from_at=start, to_at=midpoint)
        )

        assert [gap.gap_type for gap in full.gaps] == [gap_type]
        assert leading.segments[0].segment_id == full.segments[1].segment_id
        assert leading.gaps[0].gap_type == gap_type
        assert leading.gaps[0].left_segment_id is None
        assert leading.gaps[0].right_segment_id == full.segments[1].segment_id
        assert leading.gaps[0].start_at == midpoint
        assert leading.gaps[0].end_at == right_at
        assert trailing.segments[0].segment_id == full.segments[0].segment_id
        assert trailing.gaps[0].gap_type == gap_type
        assert trailing.gaps[0].left_segment_id == full.segments[0].segment_id
        assert trailing.gaps[0].right_segment_id is None
        assert trailing.gaps[0].start_at == start
        assert trailing.gaps[0].end_at == midpoint


def test_tied_series_points_preserve_original_full_total_order() -> None:
    event_at = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    first_payload = make_point(20, event_at=event_at).model_dump_public()
    second_payload = make_point(21, event_at=event_at).model_dump_public()
    first_payload["samplePairId"] = "00000000-0000-5000-8000-000000000001"
    first_payload["pointId"] = "00000000-0000-5000-8000-000000000009"
    second_payload["samplePairId"] = "00000000-0000-5000-8000-000000000002"
    second_payload["pointId"] = "00000000-0000-5000-8000-000000000008"
    first = TimelinePointV1.model_validate(first_payload)
    second = TimelinePointV1.model_validate(second_payload)
    assert timeline_order_key_v1(first) < timeline_order_key_v1(second)
    repository = FakeTimelineRepositoryV1(archive=(first, second))

    overview = _service(repository).overview(
        _query(sensor_ids=("s1",), metric="temperature")
    )

    assert [str(point.point_id) for point in overview.series[0].points] == [
        "00000000-0000-5000-8000-000000000009",
        "00000000-0000-5000-8000-000000000008",
    ]


def test_global_budget_is_independent_per_sensor_source_and_never_crosses_gaps() -> None:
    archive_start = datetime(2026, 8, 12, 14, tzinfo=timezone.utc)
    archive_points = []
    point_index = 100
    for segment_index in range(4):
        cycle_id = uuid5_text(f"budget-cycle|{segment_index}")
        segment_start = archive_start + timedelta(minutes=segment_index)
        for sample_index in range(11):
            event_at = segment_start + timedelta(milliseconds=500 * sample_index)
            pair_key = f"budget-pair|{segment_index}|{sample_index}"
            for sensor_id in ("s1", "s2"):
                archive_points.append(
                    make_point(
                        point_index,
                        event_at=event_at,
                        sensor_id=sensor_id,
                        pair_key=pair_key,
                        cycle_id=cycle_id,
                        temperature=float(point_index - 120),
                    )
                )
                point_index += 1
    archive = tuple(sorted(archive_points, key=timeline_order_key_v1))

    live_start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    live = tuple(
        sorted(
            (
                make_point(
                    1000 + index,
                    event_at=live_start + timedelta(milliseconds=250 * index),
                    sensor_id="s1",
                    source_kind="live_collection",
                    temperature=float(index % 5 - 2),
                )
                for index in range(41)
            ),
            key=timeline_order_key_v1,
        )
    )
    policy = make_policy()
    repository = FakeTimelineRepositoryV1(
        archive=archive,
        live=live,
        policies=(policy,),
    )

    overview = _service(repository).overview(_query(max_points=40))
    payload = overview.model_dump_public()
    original_values = {
        str(point.point_id): point.measurements.temperature.value
        for point in (*archive, *live)
    }
    segment_by_id = {
        segment["segmentId"]: segment for segment in payload["segments"]
    }
    combinations = {}
    for series in payload["series"]:
        key = (series["sensorId"], series["sourceKind"])
        combinations.setdefault(key, []).append(series)
        segment = segment_by_id[series["segmentId"]]
        assert all(
            segment["startAt"] <= point["eventAt"] <= segment["endAt"]
            for point in series["points"]
        )
        assert all(
            point["pointId"] in original_values
            and point["value"] == original_values[point["pointId"]]
            for point in series["points"]
        )
        assert (
            series["aggregation"]["originalPointCount"]
            == series["aggregation"]["returnedPointCount"]
            + series["aggregation"]["omittedPointCount"]
        )

    assert set(combinations) == {
        ("s1", "historical_archive"),
        ("s2", "historical_archive"),
        ("s1", "live_collection"),
    }
    for rows in combinations.values():
        assert sum(
            row["aggregation"]["returnedPointCount"] for row in rows
        ) <= 40
        assert {row["aggregation"]["method"] for row in rows} == {
            "time_bucket_envelope_v1"
        }
    assert any(
        row["aggregation"]["originalPointCount"] > 0 and not row["points"]
        for row in payload["series"]
    )
    assert overview.aggregation_summary.original_point_count == len(archive) + len(live)
    assert overview.event_candidates == []


def test_null_policy_produces_unclassified_coverage_without_defaults() -> None:
    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    live = tuple(
        sorted(
            (
                make_point(
                    2000,
                    event_at=start,
                    source_kind="live_collection",
                    policy_id=None,
                ),
                make_point(
                    2001,
                    event_at=start + timedelta(seconds=5),
                    source_kind="live_collection",
                    policy_id=None,
                ),
            ),
            key=timeline_order_key_v1,
        )
    )
    repository = FakeTimelineRepositoryV1(live=live, batch_id=None)

    overview = _service(repository).overview(_query(sensor_ids=("s1",)))

    assert [gap.gap_type for gap in overview.gaps] == [
        "unclassified_coverage_gap"
    ]
    assert all(
        segment.assumptions == ["live_collection_policy_missing"]
        for segment in overview.segments
    )
    assert repository.policy_reads == []


def test_nonnull_policy_association_without_policy_record_fails_closed() -> None:
    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    live = (
        make_point(2100, event_at=start, source_kind="live_collection"),
    )
    repository = FakeTimelineRepositoryV1(live=live, batch_id=None)
    from twinops.timeline.segments_v1 import TimelinePolicyEvidenceInvalidV1

    with pytest.raises(
        TimelinePolicyEvidenceInvalidV1,
        match="timeline_collection_policy_unavailable",
    ):
        _service(repository).overview(_query(sensor_ids=("s1",)))


def test_service_fails_closed_for_overlapping_archive_and_live_sources() -> None:
    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    archive = (make_point(3000, event_at=start),)
    live = (
        make_point(
            3001,
            event_at=start,
            source_kind="live_collection",
        ),
    )
    repository = FakeTimelineRepositoryV1(
        archive=archive,
        live=live,
        policies=(make_policy(),),
    )
    from twinops.timeline.segments_v1 import TimelineSourceOverlapV1

    with pytest.raises(TimelineSourceOverlapV1, match="timeline_source_overlap"):
        _service(repository).overview(_query(sensor_ids=("s1",)))


def test_active_batch_change_during_overview_fails_closed() -> None:
    class SwitchingRepository(FakeTimelineRepositoryV1):
        def read_live_points(self, query):
            result = super().read_live_points(query)
            self.batch_id = "sha256:" + "d" * 64
            return result

    repository = SwitchingRepository()
    from twinops.timeline.service_v1 import TimelineOverviewSnapshotConflictV1

    with pytest.raises(
        TimelineOverviewSnapshotConflictV1,
        match="active historical batch changed",
    ):
        _service(repository).overview(_query())


def test_real_scale_shape_keeps_all_originals_and_builds_204_cycles() -> None:
    start = datetime(2026, 5, 19, 14, tzinfo=timezone.utc)
    points = []
    for cycle_index in range(204):
        cycle_id = uuid5_text(f"overview-cycle|{cycle_index}")
        cycle_start = start + timedelta(minutes=cycle_index)
        points.extend(
            (
                make_point(
                    4000 + 3 * cycle_index,
                    event_at=cycle_start,
                    sensor_id="s1",
                    pair_key=f"scale|{cycle_index}|a",
                    cycle_id=cycle_id,
                ),
                make_point(
                    4001 + 3 * cycle_index,
                    event_at=cycle_start,
                    sensor_id="s2",
                    pair_key=f"scale|{cycle_index}|a",
                    cycle_id=cycle_id,
                ),
                make_point(
                    4002 + 3 * cycle_index,
                    event_at=cycle_start + timedelta(seconds=1),
                    sensor_id="s1",
                    pair_key=f"scale|{cycle_index}|b",
                    cycle_id=cycle_id,
                ),
            )
        )
    archive = tuple(sorted(points, key=timeline_order_key_v1))
    repository = FakeTimelineRepositoryV1(archive=archive)

    overview = _service(repository).overview(_query(max_points=4000))

    assert len(archive) == 612
    assert len(overview.operating_cycles) == 204
    assert overview.aggregation_summary.original_point_count == 612
    assert overview.aggregation_summary.returned_point_count == 612
    assert overview.aggregation_summary.omitted_point_count == 0
    assert len(repository.archive_reads) == 2
    assert repository.live_reads
    assert repository.archive == archive
