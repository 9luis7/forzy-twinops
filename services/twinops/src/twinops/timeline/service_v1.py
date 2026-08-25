"""Read-only orchestration for honest Timeline v1 overviews."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from heapq import merge
import json
from typing import Mapping

from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    TimelineAggregationSummaryV1,
    TimelineOverviewV1,
    TimelinePointV1,
    TimelineSeriesV1,
    parse_public_utc_millis_v1,
    serialize_public_utc_millis_v1,
)
from twinops.timeline.downsample_v1 import (
    ReducedSensorSourceBudgetV1,
    reduce_sensor_source_budget,
    timeline_metric_value_v1,
)
from twinops.timeline.ranges_v1 import (
    ResolvedTimelineRangesV1,
    resolve_timeline_ranges_v1,
)
from twinops.timeline.repository_v1 import (
    TimelineMetricV1,
    TimelineReadQueryV1,
    TimelineReadRepositoryV1,
    TimelineSensorIdV1,
    TimelineSliceV1,
    timeline_order_key_v1,
)
from twinops.timeline.segments_v1 import (
    TimelineCoverageV1,
    build_operating_cycles_v1,
    build_timeline_coverage_v1,
    project_timeline_coverage_v1,
)


_SENSORS: tuple[TimelineSensorIdV1, ...] = ("s1", "s2")
_SOURCES = ("historical_archive", "live_collection")


class TimelineOverviewSnapshotConflictV1(RuntimeError):
    """The active archive changed while an overview snapshot was read."""


class TimelineOverviewRepositoryErrorV1(RuntimeError):
    """A read repository violated its bounded original-point contract."""


@dataclass(frozen=True)
class TimelineOverviewQueryV1:
    asset_id: str
    from_at: datetime | None
    to_at: datetime | None
    sensor_ids: tuple[TimelineSensorIdV1, ...]
    metric: TimelineMetricV1 = "vibrationVelocityRms"
    max_points: int = 1200

    def __post_init__(self) -> None:
        if self.asset_id != "forzy-motor-01":
            raise ValueError("unknown timeline asset")
        for value, label in (
            (self.from_at, "timeline from"),
            (self.to_at, "timeline to"),
        ):
            if value is not None:
                if type(value) is not datetime:
                    raise ValueError(f"{label} must be a canonical UTC millisecond")
                parse_public_utc_millis_v1(value)
        if (
            self.from_at is not None
            and self.to_at is not None
            and self.from_at >= self.to_at
        ):
            raise ValueError("timeline range must be non-empty and increasing")
        if type(self.sensor_ids) is not tuple or not self.sensor_ids:
            raise ValueError("overview requires a canonical sensor tuple")
        if any(sensor not in _SENSORS for sensor in self.sensor_ids):
            raise ValueError("sensor ID must be s1 or s2")
        canonical = tuple(sensor for sensor in _SENSORS if sensor in self.sensor_ids)
        if self.sensor_ids != canonical or len(set(self.sensor_ids)) != len(
            self.sensor_ids
        ):
            raise ValueError("overview sensor IDs must be unique and canonical")
        if self.metric not in {
            "vibrationVelocityRms",
            "vibrationAcceleration",
            "temperature",
        }:
            raise ValueError("unknown timeline metric")
        if type(self.max_points) is not int or not 40 <= self.max_points <= 4000:
            raise ValueError("maxPoints must be an integer between 40 and 4000")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def timeline_overview_query_fingerprint_v1(
    query: TimelineOverviewQueryV1,
) -> str:
    payload = {
        "aggregation": "time_bucket_envelope_v1",
        "assetId": query.asset_id,
        "from": (
            None
            if query.from_at is None
            else serialize_public_utc_millis_v1(query.from_at)
        ),
        "maxPoints": query.max_points,
        "metric": query.metric,
        "order": ["eventAt", "samplePairId", "sensorId", "pointId"],
        "sensorIds": list(query.sensor_ids),
        "to": (
            None
            if query.to_at is None
            else serialize_public_utc_millis_v1(query.to_at)
        ),
    }
    return "sha256:" + sha256(_canonical_json_bytes(payload)).hexdigest()


def _active_batch_id(summary: object | None) -> str | None:
    if summary is None:
        return None
    batch_id = getattr(summary, "batch_id", None)
    if not isinstance(batch_id, str):
        raise TimelineOverviewRepositoryErrorV1(
            "active batch summary has no canonical batch ID"
        )
    return batch_id


def _read_all_source_points(
    repository: TimelineReadRepositoryV1,
    query: TimelineOverviewQueryV1,
    *,
    source_kind: str,
) -> tuple[TimelinePointV1, ...]:
    reader = (
        repository.read_archive_points
        if source_kind == "historical_archive"
        else repository.read_live_points
    )
    after = None
    result: list[TimelinePointV1] = []
    seen_boundaries = set()
    while True:
        read_query = TimelineReadQueryV1(
            asset_id=query.asset_id,
            from_at=None,
            to_at=None,
            sensor_id=None,
            metric=query.metric,
            after=after,
            limit=500,
        )
        page = reader(read_query)
        if not isinstance(page, TimelineSliceV1):
            raise TimelineOverviewRepositoryErrorV1(
                "timeline repository returned an invalid source slice"
            )
        if len(page.points) > read_query.limit + 1:
            raise TimelineOverviewRepositoryErrorV1(
                "timeline repository exceeded its bounded source read"
            )
        if any(point.source_kind != source_kind for point in page.points):
            raise TimelineOverviewRepositoryErrorV1(
                "timeline repository crossed source projections"
            )
        if page.has_more:
            selected = page.points[: read_query.limit]
            if not selected:
                raise TimelineOverviewRepositoryErrorV1(
                    "timeline repository made no pagination progress"
                )
        else:
            if len(page.points) > read_query.limit:
                raise TimelineOverviewRepositoryErrorV1(
                    "timeline repository returned lookahead without hasMore"
                )
            selected = page.points
        if after is not None and any(
            timeline_order_key_v1(point) <= after for point in selected
        ):
            raise TimelineOverviewRepositoryErrorV1(
                "timeline repository violated its exclusive boundary"
            )
        result.extend(selected)
        if not page.has_more:
            break
        after = timeline_order_key_v1(selected[-1])
        if after in seen_boundaries:
            raise TimelineOverviewRepositoryErrorV1(
                "timeline repository repeated a pagination boundary"
            )
        seen_boundaries.add(after)

    points = tuple(result)
    keys = tuple(timeline_order_key_v1(point) for point in points)
    if keys != tuple(sorted(keys)) or len(
        {str(point.point_id) for point in points}
    ) != len(points):
        raise TimelineOverviewRepositoryErrorV1(
            "timeline repository originals are not uniquely ordered"
        )
    return points


def _range_payload(
    start: datetime | None,
    end: datetime | None,
) -> dict[str, str] | None:
    if start is None or end is None:
        return None
    return {
        "from": serialize_public_utc_millis_v1(start),
        "to": serialize_public_utc_millis_v1(end),
    }


def _policies_for_effective_points(
    repository: TimelineReadRepositoryV1,
    points: tuple[TimelinePointV1, ...],
) -> Mapping[str, CollectionPolicyV1]:
    policy_ids = {
        point.provenance.collection_policy_id
        for point in points
        if point.source_kind == "live_collection"
        and point.provenance.collection_policy_id is not None
    }
    if not policy_ids:
        return {}
    policies = repository.collection_policies(set(policy_ids))
    if not isinstance(policies, dict) or not set(policies).issubset(policy_ids):
        raise TimelineOverviewRepositoryErrorV1(
            "timeline repository returned unrelated collection policies"
        )
    return policies


def _budgets(
    points: tuple[TimelinePointV1, ...],
    *,
    query: TimelineOverviewQueryV1,
    ranges: ResolvedTimelineRangesV1,
) -> dict[tuple[str, str], ReducedSensorSourceBudgetV1]:
    if ranges.effective_from is None or ranges.effective_to is None:
        return {}
    result: dict[tuple[str, str], ReducedSensorSourceBudgetV1] = {}
    for sensor_id in query.sensor_ids:
        for source_kind in _SOURCES:
            group = tuple(
                point
                for point in points
                if point.sensor_id == sensor_id
                and point.source_kind == source_kind
            )
            if not group:
                continue
            result[(sensor_id, source_kind)] = reduce_sensor_source_budget(
                group,
                sensor_id=sensor_id,
                source_kind=source_kind,
                metric=query.metric,
                from_at=ranges.effective_from,
                to_at=ranges.effective_to,
                max_points=query.max_points,
            )
    return result


def _series(
    points: tuple[TimelinePointV1, ...],
    coverage: TimelineCoverageV1,
    budgets: Mapping[tuple[str, str], ReducedSensorSourceBudgetV1],
    *,
    query: TimelineOverviewQueryV1,
) -> tuple[TimelineSeriesV1, ...]:
    rows: list[TimelineSeriesV1] = []
    for segment in coverage.segments:
        segment_id = str(segment.segment_id)
        for sensor_id in _SENSORS:
            if getattr(segment.sensor_counts, sensor_id) == 0:
                continue
            originals = tuple(
                point
                for point in points
                if point.sensor_id == sensor_id
                and coverage.point_segment_ids[str(point.point_id)] == segment_id
            )
            budget = budgets[(sensor_id, segment.source_kind)]
            selected_ids = {str(point.point_id) for point in budget.points}
            selected = tuple(
                point
                for point in originals
                if str(point.point_id) in selected_ids
            )
            rows.append(
                TimelineSeriesV1.model_validate(
                    {
                        "segmentId": segment_id,
                        "sensorId": sensor_id,
                        "sourceKind": segment.source_kind,
                        "metric": query.metric,
                        "points": [
                            {
                                "pointId": str(point.point_id),
                                "eventAt": serialize_public_utc_millis_v1(
                                    point.event_at
                                ),
                                "value": timeline_metric_value_v1(
                                    point, query.metric
                                ),
                            }
                            for point in selected
                        ],
                        "aggregation": {
                            "method": budget.method,
                            "requestedMaxPoints": query.max_points,
                            "originalPointCount": len(originals),
                            "returnedPointCount": len(selected),
                            "omittedPointCount": len(originals) - len(selected),
                        },
                    }
                )
            )
    return tuple(rows)


class TimelineServiceV1:
    """Compose public overviews without models, scorers, writes, or upstream I/O."""

    def __init__(self, repository: TimelineReadRepositoryV1) -> None:
        self._repository = repository

    def overview(self, query: TimelineOverviewQueryV1) -> TimelineOverviewV1:
        if not isinstance(query, TimelineOverviewQueryV1):
            raise ValueError("overview requires TimelineOverviewQueryV1")
        active_before = self._repository.active_batch(query.asset_id)
        active_batch_id = _active_batch_id(active_before)
        archive_all = _read_all_source_points(
            self._repository,
            query,
            source_kind="historical_archive",
        )
        live_all = _read_all_source_points(
            self._repository,
            query,
            source_kind="live_collection",
        )
        active_after = self._repository.active_batch(query.asset_id)
        if _active_batch_id(active_after) != active_batch_id:
            raise TimelineOverviewSnapshotConflictV1(
                "active historical batch changed"
            )
        if (
            active_batch_id is None
            and archive_all
            or any(
                point.provenance.batch_id != active_batch_id
                for point in archive_all
            )
        ):
            raise TimelineOverviewSnapshotConflictV1(
                "active historical batch changed"
            )

        all_originals = tuple(
            merge(
                archive_all,
                live_all,
                key=timeline_order_key_v1,
            )
        )
        topology_policies = _policies_for_effective_points(
            self._repository, all_originals
        )
        topology = build_timeline_coverage_v1(
            all_originals,
            active_batch_id=active_batch_id,
            policies=topology_policies,
        )
        available_points = tuple(
            point
            for point in all_originals
            if point.sensor_id in query.sensor_ids
        )
        ranges = resolve_timeline_ranges_v1(
            available_points,
            from_at=query.from_at,
            to_at=query.to_at,
        )
        if ranges.effective_from is None or ranges.effective_to is None:
            effective_points: tuple[TimelinePointV1, ...] = ()
        else:
            effective_points = tuple(
                point
                for point in available_points
                if ranges.effective_from <= point.event_at < ranges.effective_to
            )
        coverage = (
            TimelineCoverageV1(segments=(), gaps=(), point_segment_ids={})
            if ranges.effective_from is None or ranges.effective_to is None
            else project_timeline_coverage_v1(
                topology,
                tuple(
                    point
                    for point in all_originals
                    if ranges.effective_from <= point.event_at < ranges.effective_to
                ),
                effective_points,
                effective_from=ranges.effective_from,
                effective_to=ranges.effective_to,
                policies=topology_policies,
            )
        )
        budgets = _budgets(
            effective_points,
            query=query,
            ranges=ranges,
        )
        series = _series(
            effective_points,
            coverage,
            budgets,
            query=query,
        )
        original_count = sum(
            row.aggregation.original_point_count for row in series
        )
        returned_count = sum(
            row.aggregation.returned_point_count for row in series
        )
        omitted_count = sum(
            row.aggregation.omitted_point_count for row in series
        )
        summary = TimelineAggregationSummaryV1.model_validate(
            {
                "requestedMaxPoints": query.max_points,
                "originalPointCount": original_count,
                "returnedPointCount": returned_count,
                "omittedPointCount": omitted_count,
                "reducedSeriesCount": sum(
                    row.aggregation.method == "time_bucket_envelope_v1"
                    for row in series
                ),
            }
        )
        cycles = (
            ()
            if active_batch_id is None
            or ranges.effective_from is None
            or ranges.effective_to is None
            else build_operating_cycles_v1(
                archive_all,
                active_batch_id=active_batch_id,
                effective_from=ranges.effective_from,
                effective_to=ranges.effective_to,
            )
        )
        return TimelineOverviewV1.model_validate(
            {
                "schemaVersion": "1.0",
                "assetId": query.asset_id,
                "queryFingerprint": timeline_overview_query_fingerprint_v1(query),
                "activeHistoricalBatchId": active_batch_id,
                "requestedRange": {
                    "from": (
                        None
                        if ranges.requested_from is None
                        else serialize_public_utc_millis_v1(
                            ranges.requested_from
                        )
                    ),
                    "to": (
                        None
                        if ranges.requested_to is None
                        else serialize_public_utc_millis_v1(ranges.requested_to)
                    ),
                },
                "effectiveRange": _range_payload(
                    ranges.effective_from, ranges.effective_to
                ),
                "availableRange": _range_payload(
                    ranges.available_from, ranges.available_to
                ),
                "aggregationSummary": summary.model_dump_public(),
                "segments": [
                    segment.model_dump_public() for segment in coverage.segments
                ],
                "gaps": [gap.model_dump_public() for gap in coverage.gaps],
                "operatingCycles": [
                    cycle.model_dump_public() for cycle in cycles
                ],
                "series": [row.model_dump_public() for row in series],
                "eventCandidates": [],
                "capabilities": {
                    "historical": active_batch_id is not None,
                    "live": True,
                },
            }
        )


__all__ = [
    "TimelineOverviewQueryV1",
    "TimelineOverviewRepositoryErrorV1",
    "TimelineOverviewSnapshotConflictV1",
    "TimelineServiceV1",
    "timeline_overview_query_fingerprint_v1",
]
