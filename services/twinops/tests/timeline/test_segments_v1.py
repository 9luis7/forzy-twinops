from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import NAMESPACE_URL, uuid5

import pytest

from twinops.contracts.timeline_v1_models import CollectionPolicyV1
from twinops.timeline.repository_v1 import timeline_order_key_v1
from twinops.timeline.segments_v1 import (
    TimelinePolicyEvidenceInvalidV1,
    TimelineSourceOverlapV1,
    TimelineUnrepresentableLiveGapV1,
    build_operating_cycles_v1,
    build_timeline_coverage_v1,
)

from overview_fixtures_v1 import BATCH_A, make_point, make_policy, uuid5_text


def _ordered(*points):
    return tuple(sorted(points, key=timeline_order_key_v1))


def test_archive_gap_boundary_is_strictly_greater_than_fifteen_seconds() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    points = _ordered(
        make_point(0, event_at=start),
        make_point(1, event_at=start + timedelta(seconds=15)),
        make_point(2, event_at=start + timedelta(seconds=30, milliseconds=1)),
    )

    coverage = build_timeline_coverage_v1(
        points,
        active_batch_id=BATCH_A,
        policies={},
    )

    assert len(coverage.segments) == 2
    assert len(coverage.gaps) == 1
    gap = coverage.gaps[0]
    assert gap.gap_type == "archive_sampling_gap"
    assert gap.start_at == start + timedelta(seconds=15)
    assert gap.end_at == start + timedelta(seconds=30, milliseconds=1)
    assert gap.duration_seconds == 15.001
    expected_name = "|".join(
        (
            "timeline-gap-v1",
            "archive_sampling_gap",
            str(gap.left_segment_id),
            str(gap.right_segment_id),
            "2026-08-22T12:00:15.000Z",
            "2026-08-22T12:00:30.001Z",
            "timeline-gap-v1",
        )
    )
    assert str(gap.gap_id) == str(uuid5(NAMESPACE_URL, expected_name))


def test_nonoverlapping_sources_get_discontinuity_and_overlap_fails_closed() -> None:
    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    policy = make_policy()
    archive = make_point(0, event_at=start)
    live = make_point(
        1,
        event_at=start + timedelta(minutes=1),
        source_kind="live_collection",
    )

    coverage = build_timeline_coverage_v1(
        _ordered(archive, live),
        active_batch_id=BATCH_A,
        policies={policy.collection_policy_id: policy},
    )
    assert [gap.gap_type for gap in coverage.gaps] == ["source_discontinuity"]
    assert coverage.gaps[0].duration_seconds == 60

    overlapping = make_point(
        2,
        event_at=start,
        source_kind="live_collection",
    )
    with pytest.raises(TimelineSourceOverlapV1, match="timeline_source_overlap"):
        build_timeline_coverage_v1(
            _ordered(archive, overlapping),
            active_batch_id=BATCH_A,
            policies={policy.collection_policy_id: policy},
        )


def test_live_gaps_use_only_the_exact_persisted_policy_schedule() -> None:
    policy = make_policy()
    inside = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    outside = datetime(2026, 8, 12, 17, tzinfo=timezone.utc)

    expected_gap = build_timeline_coverage_v1(
        _ordered(
            make_point(10, event_at=inside, source_kind="live_collection"),
            make_point(
                11,
                event_at=inside + timedelta(seconds=15, milliseconds=1),
                source_kind="live_collection",
            ),
        ),
        active_batch_id=None,
        policies={policy.collection_policy_id: policy},
    )
    assert [gap.gap_type for gap in expected_gap.gaps] == [
        "live_expected_collection_gap"
    ]

    idle_gap = build_timeline_coverage_v1(
        _ordered(
            make_point(12, event_at=outside, source_kind="live_collection"),
            make_point(
                13,
                event_at=outside + timedelta(seconds=15, milliseconds=1),
                source_kind="live_collection",
            ),
        ),
        active_batch_id=None,
        policies={policy.collection_policy_id: policy},
    )
    assert [gap.gap_type for gap in idle_gap.gaps] == ["expected_idle"]

    exact_boundary = build_timeline_coverage_v1(
        _ordered(
            make_point(14, event_at=inside, source_kind="live_collection"),
            make_point(
                15,
                event_at=inside + timedelta(seconds=15),
                source_kind="live_collection",
            ),
        ),
        active_batch_id=None,
        policies={policy.collection_policy_id: policy},
    )
    assert len(exact_boundary.segments) == 1
    assert exact_boundary.gaps == ()


def test_null_policy_never_inherits_a_runtime_gap_default() -> None:
    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    points = _ordered(
        make_point(
            20,
            event_at=start,
            source_kind="live_collection",
            policy_id=None,
        ),
        make_point(
            21,
            event_at=start + timedelta(seconds=5),
            source_kind="live_collection",
            policy_id=None,
        ),
    )

    coverage = build_timeline_coverage_v1(
        points,
        active_batch_id=None,
        policies={},
    )

    assert len(coverage.segments) == 2
    assert [gap.gap_type for gap in coverage.gaps] == [
        "unclassified_coverage_gap"
    ]
    assert all(
        segment.assumptions == ["live_collection_policy_missing"]
        for segment in coverage.segments
    )


def test_nonnull_association_without_its_policy_fails_closed() -> None:
    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    points = _ordered(
        make_point(22, event_at=start, source_kind="live_collection"),
        make_point(
            23,
            event_at=start + timedelta(seconds=5),
            source_kind="live_collection",
        ),
    )

    with pytest.raises(
        TimelinePolicyEvidenceInvalidV1,
        match="timeline_collection_policy_unavailable",
    ):
        build_timeline_coverage_v1(
            points,
            active_batch_id=None,
            policies={},
        )


def test_invalid_hash_or_out_of_effect_association_fails_closed() -> None:
    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    point = make_point(24, event_at=start, source_kind="live_collection")
    corrupted = make_policy()
    corrupted.configuration_hash = "sha256:" + "0" * 64
    with pytest.raises(
        TimelinePolicyEvidenceInvalidV1,
        match="timeline_policy_payload_invalid",
    ):
        build_timeline_coverage_v1(
            (point,),
            active_batch_id=None,
            policies={corrupted.collection_policy_id: corrupted},
        )

    future_policy = make_policy(start + timedelta(days=1))
    with pytest.raises(
        TimelinePolicyEvidenceInvalidV1,
        match="timeline_collection_policy_invalid_association",
    ):
        build_timeline_coverage_v1(
            (point,),
            active_batch_id=None,
            policies={future_policy.collection_policy_id: future_policy},
        )


def test_mixed_schedule_interval_and_nonnull_policy_transition_fail_closed() -> None:
    policy = make_policy()
    crossing = datetime(2026, 8, 12, 16, 59, 50, tzinfo=timezone.utc)
    with pytest.raises(
        TimelineUnrepresentableLiveGapV1,
        match="timeline_live_gap_crosses_policy_windows",
    ):
        build_timeline_coverage_v1(
            _ordered(
                make_point(25, event_at=crossing, source_kind="live_collection"),
                make_point(
                    26,
                    event_at=crossing + timedelta(seconds=20),
                    source_kind="live_collection",
                ),
            ),
            active_batch_id=None,
            policies={policy.collection_policy_id: policy},
        )

    payload = policy.model_dump_public()
    payload["collectionPolicyId"] = "forzy-live-window-v2"
    selected_keys = (
        "schemaVersion",
        "collectionPolicyId",
        "assetId",
        "timezone",
        "activeWeekdays",
        "windowStartLocal",
        "windowEndLocal",
        "pollIntervalSeconds",
        "gapThresholdSeconds",
    )
    canonical = json.dumps(
        {key: payload[key] for key in selected_keys},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload["configurationHash"] = "sha256:" + sha256(canonical).hexdigest()
    policy_v2 = CollectionPolicyV1.model_validate(payload)
    transition_start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    with pytest.raises(
        TimelineUnrepresentableLiveGapV1,
        match="timeline_live_policy_transition_unrepresentable",
    ):
        build_timeline_coverage_v1(
            _ordered(
                make_point(
                    27,
                    event_at=transition_start,
                    source_kind="live_collection",
                    policy_id=policy.collection_policy_id,
                ),
                make_point(
                    28,
                    event_at=transition_start + timedelta(seconds=5),
                    source_kind="live_collection",
                    policy_id=policy_v2.collection_policy_id,
                ),
            ),
            active_batch_id=None,
            policies={
                policy.collection_policy_id: policy,
                policy_v2.collection_policy_id: policy_v2,
            },
        )


def test_segments_have_exact_counts_sources_policies_and_point_membership() -> None:
    start = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    policy = make_policy()
    points = _ordered(
        make_point(30, event_at=start, sensor_id="s1", pair_key="a"),
        make_point(31, event_at=start, sensor_id="s2", pair_key="a"),
        make_point(
            32,
            event_at=start + timedelta(minutes=1),
            sensor_id="s1",
            source_kind="live_collection",
        ),
    )
    coverage = build_timeline_coverage_v1(
        points,
        active_batch_id=BATCH_A,
        policies={policy.collection_policy_id: policy},
    )

    archive, live = coverage.segments
    assert archive.total_points == 2
    assert archive.sensor_counts.s1 == 1
    assert archive.sensor_counts.s2 == 1
    assert archive.batch_id == BATCH_A
    assert archive.collection_policy_id is None
    assert live.collection_policy_id == policy.collection_policy_id
    assert live.batch_id is None
    assert set(coverage.point_segment_ids) == {
        str(point.point_id) for point in points
    }


def test_active_cycle_facts_are_exact_ordered_and_scale_to_204_cycles() -> None:
    start = datetime(2026, 5, 19, 14, tzinfo=timezone.utc)
    points = []
    for index in range(204):
        cycle_id = uuid5_text(f"registered-cycle|{index}")
        cycle_start = start + timedelta(minutes=index)
        points.extend(
            (
                make_point(
                    1000 + 2 * index,
                    event_at=cycle_start,
                    sensor_id="s1",
                    cycle_id=cycle_id,
                ),
                make_point(
                    1001 + 2 * index,
                    event_at=cycle_start + timedelta(seconds=1),
                    sensor_id="s2",
                    cycle_id=cycle_id,
                ),
            )
        )
    ordered = tuple(sorted(points, key=timeline_order_key_v1))

    cycles = build_operating_cycles_v1(
        ordered,
        active_batch_id=BATCH_A,
        effective_from=start,
        effective_to=start + timedelta(minutes=204),
    )

    assert len(cycles) == 204
    assert cycles[0].previous_operating_cycle_id is None
    assert cycles[0].gap_before_seconds is None
    assert all(cycle.duration_seconds == 1 for cycle in cycles)
    assert all(cycle.total_points == 2 for cycle in cycles)
    assert all(cycle.sensor_counts.s1 == cycle.sensor_counts.s2 == 1 for cycle in cycles)
    assert all(cycle.candidate_count == 0 for cycle in cycles)
    assert cycles[1].previous_operating_cycle_id == cycles[0].operating_cycle_id
    assert cycles[1].gap_before_seconds == 59

    narrowed = build_operating_cycles_v1(
        ordered,
        active_batch_id=BATCH_A,
        effective_from=start + timedelta(minutes=100),
        effective_to=start + timedelta(minutes=102),
    )
    assert len(narrowed) == 2
    assert narrowed[0].previous_operating_cycle_id is None
    assert narrowed[0].gap_before_seconds is None
