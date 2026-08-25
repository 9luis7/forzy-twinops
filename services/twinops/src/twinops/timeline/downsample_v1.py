"""Peak-preserving Timeline v1 overview reduction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Literal, Sequence

from twinops.contracts.timeline_v1_models import (
    TimelinePointV1,
    TimelineSourceKindV1,
    parse_public_utc_millis_v1,
)
from twinops.timeline.repository_v1 import (
    TimelineMetricV1,
    TimelineSensorIdV1,
    timeline_order_key_v1,
)


TimelineAggregationMethodV1 = Literal["none", "time_bucket_envelope_v1"]


def timeline_metric_value_v1(
    point: TimelinePointV1,
    metric: TimelineMetricV1,
) -> float:
    if metric not in {
        "vibrationVelocityRms",
        "vibrationAcceleration",
        "temperature",
    }:
        raise ValueError("unknown timeline metric")
    field_name = {
        "vibrationVelocityRms": "vibration_velocity_rms",
        "vibrationAcceleration": "vibration_acceleration",
        "temperature": "temperature",
    }[metric]
    value = float(getattr(point.measurements, field_name).value)
    if not math.isfinite(value):
        raise ValueError("timeline metric values must be finite")
    return value


@dataclass(frozen=True)
class ReducedSensorSourceBudgetV1:
    sensor_id: TimelineSensorIdV1
    source_kind: TimelineSourceKindV1
    metric: TimelineMetricV1
    points: tuple[TimelinePointV1, ...]
    method: TimelineAggregationMethodV1
    requested_max_points: int
    original_point_count: int
    returned_point_count: int
    omitted_point_count: int

    def __post_init__(self) -> None:
        if self.sensor_id not in {"s1", "s2"}:
            raise ValueError("sensor ID must be s1 or s2")
        if self.source_kind not in {"historical_archive", "live_collection"}:
            raise ValueError("unknown timeline source")
        if self.metric not in {
            "vibrationVelocityRms",
            "vibrationAcceleration",
            "temperature",
        }:
            raise ValueError("unknown timeline metric")
        if type(self.requested_max_points) is not int or not (
            40 <= self.requested_max_points <= 4000
        ):
            raise ValueError("maxPoints must be an integer between 40 and 4000")
        if self.returned_point_count != len(self.points):
            raise ValueError("returned timeline count must match points")
        if (
            self.original_point_count < 0
            or self.returned_point_count < 0
            or self.omitted_point_count
            != self.original_point_count - self.returned_point_count
        ):
            raise ValueError("timeline aggregation counts are inconsistent")
        expected_method: TimelineAggregationMethodV1 = (
            "none"
            if self.original_point_count <= self.requested_max_points
            else "time_bucket_envelope_v1"
        )
        if self.method != expected_method:
            raise ValueError("timeline aggregation method disagrees with its budget")
        if self.returned_point_count > self.requested_max_points:
            raise ValueError("timeline aggregation exceeds its global ceiling")
        keys = tuple(timeline_order_key_v1(point) for point in self.points)
        if keys != tuple(sorted(keys)) or len(
            {str(point.point_id) for point in self.points}
        ) != len(self.points):
            raise ValueError("reduced timeline points must be uniquely ordered")
        if any(
            point.sensor_id != self.sensor_id
            or point.source_kind != self.source_kind
            for point in self.points
        ):
            raise ValueError("reduced timeline points must be sensor/source homogeneous")


def _microseconds(value: timedelta) -> int:
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )


def reduce_sensor_source_budget(
    points: Sequence[TimelinePointV1],
    *,
    sensor_id: TimelineSensorIdV1,
    source_kind: TimelineSourceKindV1,
    metric: TimelineMetricV1,
    from_at: datetime,
    to_at: datetime,
    max_points: int,
) -> ReducedSensorSourceBudgetV1:
    """Apply the frozen global envelope once to one sensor/source combination."""

    if sensor_id not in {"s1", "s2"}:
        raise ValueError("sensor ID must be s1 or s2")
    if source_kind not in {"historical_archive", "live_collection"}:
        raise ValueError("unknown timeline source")
    if metric not in {
        "vibrationVelocityRms",
        "vibrationAcceleration",
        "temperature",
    }:
        raise ValueError("unknown timeline metric")
    if type(max_points) is not int or not 40 <= max_points <= 4000:
        raise ValueError("maxPoints must be an integer between 40 and 4000")
    if type(from_at) is not datetime or type(to_at) is not datetime:
        raise ValueError("timeline bounds must be canonical UTC milliseconds")
    start = parse_public_utc_millis_v1(from_at)
    end = parse_public_utc_millis_v1(to_at)
    if start >= end:
        raise ValueError("timeline range must be non-empty and increasing")

    originals = tuple(points)
    if any(not isinstance(point, TimelinePointV1) for point in originals):
        raise ValueError("timeline reducer accepts original TimelinePointV1 values")
    keys = tuple(timeline_order_key_v1(point) for point in originals)
    if keys != tuple(sorted(keys)) or len(
        {str(point.point_id) for point in originals}
    ) != len(originals):
        raise ValueError("timeline reducer input must be uniquely total-ordered")
    if any(
        point.sensor_id != sensor_id
        or point.source_kind != source_kind
        or not start <= point.event_at < end
        for point in originals
    ):
        raise ValueError("timeline reducer input is not the complete requested group")
    for point in originals:
        timeline_metric_value_v1(point, metric)

    if len(originals) <= max_points:
        selected = originals
        method: TimelineAggregationMethodV1 = "none"
    else:
        bucket_count = max_points // 4
        duration_us = _microseconds(end - start)
        buckets: list[list[TimelinePointV1]] = [
            [] for _ in range(bucket_count)
        ]
        for point in originals:
            elapsed_us = _microseconds(point.event_at - start)
            bucket_index = min(
                bucket_count - 1,
                (elapsed_us * bucket_count) // duration_us,
            )
            buckets[bucket_index].append(point)

        selected_ids: set[str] = set()
        for bucket in buckets:
            if not bucket:
                continue
            first = bucket[0]
            last = bucket[-1]
            minimum = min(
                bucket,
                key=lambda point: (
                    timeline_metric_value_v1(point, metric),
                    timeline_order_key_v1(point),
                ),
            )
            maximum_value = max(
                timeline_metric_value_v1(point, metric) for point in bucket
            )
            maximum = min(
                (
                    point
                    for point in bucket
                    if timeline_metric_value_v1(point, metric) == maximum_value
                ),
                key=timeline_order_key_v1,
            )
            selected_ids.update(
                str(point.point_id)
                for point in (first, minimum, maximum, last)
            )
        selected = tuple(
            point for point in originals if str(point.point_id) in selected_ids
        )
        method = "time_bucket_envelope_v1"

    return ReducedSensorSourceBudgetV1(
        sensor_id=sensor_id,
        source_kind=source_kind,
        metric=metric,
        points=selected,
        method=method,
        requested_max_points=max_points,
        original_point_count=len(originals),
        returned_point_count=len(selected),
        omitted_point_count=len(originals) - len(selected),
    )


__all__ = [
    "ReducedSensorSourceBudgetV1",
    "reduce_sensor_source_budget",
    "timeline_metric_value_v1",
]
