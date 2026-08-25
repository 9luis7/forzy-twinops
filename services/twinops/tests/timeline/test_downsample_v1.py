from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from twinops.timeline.downsample_v1 import reduce_sensor_source_budget

from overview_fixtures_v1 import make_point


def _points(
    count: int,
    *,
    start: datetime,
    sensor_id: str = "s1",
    source_kind: str = "historical_archive",
):
    return tuple(
        make_point(
            index,
            event_at=start + timedelta(milliseconds=250 * index),
            sensor_id=sensor_id,
            source_kind=source_kind,
            velocity=float(index),
        )
        for index in range(count)
    )


def _reduce(points, *, start, sensor_id="s1", source="historical_archive"):
    return reduce_sensor_source_budget(
        points,
        sensor_id=sensor_id,
        source_kind=source,
        metric="vibrationVelocityRms",
        from_at=start,
        to_at=start + timedelta(seconds=10, milliseconds=1),
        max_points=40,
    )


def test_empty_one_and_exact_budget_return_originals_without_reduction() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    for points in ((), _points(1, start=start), _points(40, start=start)):
        result = _reduce(points, start=start)
        assert result.points == points
        assert result.method == "none"
        assert result.original_point_count == len(points)
        assert result.returned_point_count == len(points)
        assert result.omitted_point_count == 0


def test_envelope_keeps_first_min_max_last_with_total_order_ties() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    raw = list(_points(41, start=start))
    values = (0.0, -5.0, 9.0, 9.0, 1.0)
    for index, value in enumerate(values):
        payload = raw[index].model_dump_public()
        payload["measurements"]["vibrationVelocityRms"]["value"] = value
        raw[index] = type(raw[index]).model_validate(payload)

    first = _reduce(tuple(raw), start=start)
    second = _reduce(tuple(raw), start=start)
    selected_ids = {str(point.point_id) for point in first.points}

    assert str(raw[0].point_id) in selected_ids
    assert str(raw[1].point_id) in selected_ids
    assert str(raw[2].point_id) in selected_ids
    assert str(raw[3].point_id) not in selected_ids
    assert str(raw[4].point_id) in selected_ids
    assert first.method == "time_bucket_envelope_v1"
    assert first.returned_point_count <= 40
    assert first.omitted_point_count == 41 - first.returned_point_count
    assert [point.point_id for point in first.points] == [
        point.point_id for point in second.points
    ]


@pytest.mark.parametrize(
    "mutation",
    ("unordered", "duplicate", "mixed_sensor", "mixed_source", "outside"),
)
def test_reducer_rejects_nonoriginal_or_incomplete_group_inputs(mutation: str) -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    points = list(_points(3, start=start))
    if mutation == "unordered":
        points[0], points[1] = points[1], points[0]
    elif mutation == "duplicate":
        points[1] = points[0]
    elif mutation == "mixed_sensor":
        points[1] = make_point(
            99, event_at=points[1].event_at, sensor_id="s2"
        )
    elif mutation == "mixed_source":
        points[1] = make_point(
            99,
            event_at=points[1].event_at,
            source_kind="live_collection",
        )
    else:
        points[0] = make_point(
            99, event_at=start - timedelta(milliseconds=1)
        )

    with pytest.raises(ValueError):
        _reduce(tuple(points), start=start)


def test_sensor_source_budgets_are_independent_and_accept_negative_zero_extrema() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    groups = (
        (_points(41, start=start, sensor_id="s1"), "s1", "historical_archive"),
        (_points(41, start=start, sensor_id="s2"), "s2", "historical_archive"),
        (
            _points(41, start=start, sensor_id="s1", source_kind="live_collection"),
            "s1",
            "live_collection",
        ),
    )
    results = [
        _reduce(points, start=start, sensor_id=sensor, source=source)
        for points, sensor, source in groups
    ]

    assert all(result.returned_point_count <= 40 for result in results)
    assert all(result.original_point_count == 41 for result in results)
    assert {(result.sensor_id, result.source_kind) for result in results} == {
        ("s1", "historical_archive"),
        ("s2", "historical_archive"),
        ("s1", "live_collection"),
    }


@pytest.mark.parametrize("max_points", (39, 4001, True, 40.0))
def test_reducer_requires_the_strict_public_ceiling(max_points: object) -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        reduce_sensor_source_budget(
            (),
            sensor_id="s1",
            source_kind="historical_archive",
            metric="temperature",
            from_at=start,
            to_at=start + timedelta(seconds=1),
            max_points=max_points,
        )
