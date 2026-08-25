"""Coverage segments, explicit gaps, and active archive cycles."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    TimelineGapV1,
    TimelineOperatingCycleV1,
    TimelinePointV1,
    TimelineSegmentV1,
    parse_public_utc_millis_v1,
    serialize_public_utc_millis_v1,
)
from twinops.timeline.repository_v1 import timeline_order_key_v1


_ARCHIVE_GAP_THRESHOLD = timedelta(seconds=15)
_WEEKDAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


class TimelineCoverageErrorV1(ValueError):
    """Base error for coverage that cannot be represented truthfully."""


class TimelineSourceOverlapV1(TimelineCoverageErrorV1):
    """Archive/live overlap cannot satisfy the frozen segment invariant."""


class TimelineUnrepresentableLiveGapV1(TimelineCoverageErrorV1):
    """One frozen public gap cannot express mixed schedule classifications."""


class TimelinePolicyEvidenceInvalidV1(TimelineCoverageErrorV1):
    """Persisted policy evidence is internally inconsistent."""


@dataclass(frozen=True)
class TimelineCoverageV1:
    segments: tuple[TimelineSegmentV1, ...]
    gaps: tuple[TimelineGapV1, ...]
    point_segment_ids: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "point_segment_ids",
            MappingProxyType(dict(self.point_segment_ids)),
        )
        if len(self.point_segment_ids) != sum(
            segment.total_points for segment in self.segments
        ):
            raise ValueError("segment point membership is incomplete")


@dataclass(frozen=True)
class _LivePolicyEvidenceV1:
    policy_id: str | None
    policy: CollectionPolicyV1 | None
    assumption: str | None

    @property
    def key(self) -> tuple[str | None, str | None]:
        return self.policy_id, self.assumption


def _validated_originals(
    points: Sequence[TimelinePointV1],
) -> tuple[TimelinePointV1, ...]:
    originals = tuple(points)
    if any(not isinstance(point, TimelinePointV1) for point in originals):
        raise ValueError("coverage requires original TimelinePointV1 values")
    keys = tuple(timeline_order_key_v1(point) for point in originals)
    if keys != tuple(sorted(keys)) or len(
        {str(point.point_id) for point in originals}
    ) != len(originals):
        raise ValueError("coverage originals must be uniquely total-ordered")
    if any(point.asset_id != "forzy-motor-01" for point in originals):
        raise ValueError("coverage originals must use the one timeline asset")
    return originals


def _validated_policies(
    policies: Mapping[str, CollectionPolicyV1],
) -> dict[str, CollectionPolicyV1]:
    result: dict[str, CollectionPolicyV1] = {}
    for policy_id, policy in policies.items():
        if not isinstance(policy_id, str) or not policy_id:
            raise TimelinePolicyEvidenceInvalidV1(
                "timeline_policy_mapping_invalid"
            )
        if not isinstance(policy, CollectionPolicyV1):
            raise TimelinePolicyEvidenceInvalidV1(
                "timeline_policy_payload_invalid"
            )
        try:
            validated = CollectionPolicyV1.model_validate(policy.model_dump_public())
        except ValueError as exc:
            raise TimelinePolicyEvidenceInvalidV1(
                "timeline_policy_payload_invalid"
            ) from exc
        if validated.collection_policy_id != policy_id:
            raise TimelinePolicyEvidenceInvalidV1(
                "timeline_policy_mapping_invalid"
            )
        result[policy_id] = validated
    return result


def _live_evidence(
    point: TimelinePointV1,
    policies: Mapping[str, CollectionPolicyV1],
) -> _LivePolicyEvidenceV1:
    policy_id = point.provenance.collection_policy_id
    if policy_id is None:
        return _LivePolicyEvidenceV1(
            policy_id=None,
            policy=None,
            assumption="live_collection_policy_missing",
        )
    policy = policies.get(policy_id)
    if policy is None:
        raise TimelinePolicyEvidenceInvalidV1(
            "timeline_collection_policy_unavailable"
        )
    scheduled_at = point.provenance.scheduled_at
    if (
        policy.asset_id != point.asset_id
        or scheduled_at < policy.effective_from
        or (
            policy.effective_to is not None
            and scheduled_at >= policy.effective_to
        )
    ):
        raise TimelinePolicyEvidenceInvalidV1(
            "timeline_collection_policy_invalid_association"
        )
    return _LivePolicyEvidenceV1(
        policy_id=policy_id,
        policy=policy,
        assumption=None,
    )


def _segment_id(
    points: tuple[TimelinePointV1, ...],
    *,
    batch_id: str | None,
    collection_policy_id: str | None,
) -> str:
    digest = sha256(
        "|".join(str(point.point_id) for point in points).encode("ascii")
    ).hexdigest()
    name = "|".join(
        (
            "timeline-segment-v1",
            points[0].asset_id,
            points[0].source_kind,
            batch_id or "none",
            collection_policy_id or "none",
            serialize_public_utc_millis_v1(points[0].event_at),
            serialize_public_utc_millis_v1(points[-1].event_at),
            digest,
        )
    )
    return str(uuid5(NAMESPACE_URL, name))


def _build_segment(
    points: tuple[TimelinePointV1, ...],
    *,
    active_batch_id: str | None,
    evidence: _LivePolicyEvidenceV1 | None,
) -> TimelineSegmentV1:
    source = points[0].source_kind
    if any(point.source_kind != source for point in points):
        raise ValueError("a segment cannot mix timeline sources")
    counts = {
        "s1": sum(point.sensor_id == "s1" for point in points),
        "s2": sum(point.sensor_id == "s2" for point in points),
    }
    if source == "historical_archive":
        if active_batch_id is None or any(
            point.provenance.batch_id != active_batch_id for point in points
        ):
            raise TimelineCoverageErrorV1(
                "timeline_archive_active_batch_mismatch"
            )
        batch_id = active_batch_id
        collection_policy_id = None
        assumptions: list[str] = []
    else:
        if evidence is None:
            raise ValueError("live segment requires exact policy evidence")
        batch_id = None
        collection_policy_id = evidence.policy_id
        assumptions = (
            [] if evidence.assumption is None else [evidence.assumption]
        )
    return TimelineSegmentV1.model_validate(
        {
            "segmentId": _segment_id(
                points,
                batch_id=batch_id,
                collection_policy_id=collection_policy_id,
            ),
            "sourceKind": source,
            "startAt": serialize_public_utc_millis_v1(points[0].event_at),
            "endAt": serialize_public_utc_millis_v1(points[-1].event_at),
            "totalPoints": len(points),
            "sensorCounts": counts,
            "timestampQuality": points[0].timestamp_quality,
            "batchId": batch_id,
            "collectionPolicyId": collection_policy_id,
            "assumptions": sorted(set(assumptions)),
        }
    )


def _gap(
    *,
    left: TimelineSegmentV1,
    right: TimelineSegmentV1,
    gap_type: str,
) -> TimelineGapV1:
    return _bounded_gap(
        left=left,
        right=right,
        start=left.end_at,
        end=right.start_at,
        gap_type=gap_type,
    )


def _bounded_gap(
    *,
    left: TimelineSegmentV1 | None,
    right: TimelineSegmentV1 | None,
    start: datetime,
    end: datetime,
    gap_type: str,
) -> TimelineGapV1:
    if left is None and right is None:
        raise ValueError("a projected gap must border a returned segment")
    start = parse_public_utc_millis_v1(start)
    end = parse_public_utc_millis_v1(end)
    if start >= end:
        raise ValueError("a projected gap must retain a positive open interval")
    message_code = {
        "source_discontinuity": "timeline_gap_source_discontinuity",
        "archive_sampling_gap": "timeline_gap_archive_sampling",
        "live_expected_collection_gap": "timeline_gap_live_expected_collection",
        "expected_idle": "timeline_gap_expected_idle",
        "unclassified_coverage_gap": "timeline_gap_unclassified_coverage",
    }[gap_type]
    start_text = serialize_public_utc_millis_v1(start)
    end_text = serialize_public_utc_millis_v1(end)
    left_id = None if left is None else str(left.segment_id)
    right_id = None if right is None else str(right.segment_id)
    name = "|".join(
        (
            "timeline-gap-v1",
            gap_type,
            left_id or "none",
            right_id or "none",
            start_text,
            end_text,
            "timeline-gap-v1",
        )
    )
    return TimelineGapV1.model_validate(
        {
            "gapId": str(uuid5(NAMESPACE_URL, name)),
            "leftSegmentId": left_id,
            "rightSegmentId": right_id,
            "startAt": start_text,
            "endAt": end_text,
            "gapType": gap_type,
            "durationSeconds": (end - start).total_seconds(),
            "ruleVersion": "timeline-gap-v1",
            "messageCode": message_code,
        }
    )


def _archive_groups(
    points: tuple[TimelinePointV1, ...],
) -> tuple[tuple[TimelinePointV1, ...], ...]:
    if not points:
        return ()
    groups: list[list[TimelinePointV1]] = [[points[0]]]
    for point in points[1:]:
        if point.event_at - groups[-1][-1].event_at > _ARCHIVE_GAP_THRESHOLD:
            groups.append([])
        groups[-1].append(point)
    return tuple(tuple(group) for group in groups)


def _live_groups(
    points: tuple[TimelinePointV1, ...],
    policies: Mapping[str, CollectionPolicyV1],
) -> tuple[
    tuple[tuple[TimelinePointV1, ...], _LivePolicyEvidenceV1], ...
]:
    if not points:
        return ()
    evidence_by_id = {
        str(point.point_id): _live_evidence(point, policies) for point in points
    }
    groups: list[list[TimelinePointV1]] = [[points[0]]]
    group_evidence: list[_LivePolicyEvidenceV1] = [
        evidence_by_id[str(points[0].point_id)]
    ]
    for point in points[1:]:
        previous = groups[-1][-1]
        previous_evidence = evidence_by_id[str(previous.point_id)]
        evidence = evidence_by_id[str(point.point_id)]
        elapsed = point.event_at - previous.event_at
        if elapsed < timedelta(0):
            raise ValueError("live points must retain total order")
        if elapsed == timedelta(0):
            if evidence.key != previous_evidence.key:
                raise TimelineUnrepresentableLiveGapV1(
                    "timeline_tied_live_policy_overlap"
                )
            groups[-1].append(point)
            continue
        continuous = bool(
            evidence.policy is not None
            and previous_evidence.policy is not None
            and evidence.policy_id == previous_evidence.policy_id
            and elapsed
            <= timedelta(seconds=evidence.policy.gap_threshold_seconds)
        )
        if not continuous:
            groups.append([])
            group_evidence.append(evidence)
        groups[-1].append(point)
    return tuple(
        (tuple(group), evidence)
        for group, evidence in zip(groups, group_evidence, strict=True)
    )


def _expected_window_duration(
    start: datetime,
    end: datetime,
    policy: CollectionPolicyV1,
) -> timedelta:
    zone = ZoneInfo(policy.timezone)
    first_date = start.astimezone(zone).date()
    last_date = end.astimezone(zone).date()
    active_weekdays = set(policy.active_weekdays)
    start_local = time.fromisoformat(policy.window_start_local)
    end_local = time.fromisoformat(policy.window_end_local)
    total = timedelta(0)
    cursor: date = first_date
    while cursor <= last_date:
        if _WEEKDAY_NAMES[cursor.weekday()] in active_weekdays:
            window_start = datetime.combine(cursor, start_local, zone).astimezone(
                timezone.utc
            )
            window_end = datetime.combine(cursor, end_local, zone).astimezone(
                timezone.utc
            )
            window_start = max(window_start, policy.effective_from)
            if policy.effective_to is not None:
                window_end = min(window_end, policy.effective_to)
            overlap_start = max(start, window_start)
            overlap_end = min(end, window_end)
            if overlap_start < overlap_end:
                total += overlap_end - overlap_start
        cursor += timedelta(days=1)
    return total


def _classify_live_gap(
    left_points: tuple[TimelinePointV1, ...],
    right_points: tuple[TimelinePointV1, ...],
    left_evidence: _LivePolicyEvidenceV1,
    right_evidence: _LivePolicyEvidenceV1,
) -> str:
    if (
        left_evidence.policy_id is not None
        and right_evidence.policy_id is not None
        and left_evidence.policy_id != right_evidence.policy_id
    ):
        raise TimelineUnrepresentableLiveGapV1(
            "timeline_live_policy_transition_unrepresentable"
        )
    if (
        left_evidence.policy is None
        or right_evidence.policy is None
    ):
        return "unclassified_coverage_gap"
    start = left_points[-1].event_at
    end = right_points[0].event_at
    expected = _expected_window_duration(start, end, left_evidence.policy)
    duration = end - start
    if expected == timedelta(0):
        return "expected_idle"
    if expected == duration:
        return "live_expected_collection_gap"
    raise TimelineUnrepresentableLiveGapV1(
        "timeline_live_gap_crosses_policy_windows"
    )


def build_timeline_coverage_v1(
    points: Sequence[TimelinePointV1],
    *,
    active_batch_id: str | None,
    policies: Mapping[str, CollectionPolicyV1],
) -> TimelineCoverageV1:
    """Build validated inclusive segments and explicit open coverage gaps."""

    originals = _validated_originals(points)
    validated_policies = _validated_policies(policies)
    archive_points = tuple(
        point for point in originals if point.source_kind == "historical_archive"
    )
    live_points = tuple(
        point for point in originals if point.source_kind == "live_collection"
    )
    if archive_points and live_points and archive_points[-1].event_at >= live_points[0].event_at:
        raise TimelineSourceOverlapV1("timeline_source_overlap")

    archive_groups = _archive_groups(archive_points)
    live_groups = _live_groups(live_points, validated_policies)
    segments: list[TimelineSegmentV1] = []
    gaps: list[TimelineGapV1] = []
    membership: dict[str, str] = {}

    archive_segments = [
        _build_segment(
            group,
            active_batch_id=active_batch_id,
            evidence=None,
        )
        for group in archive_groups
    ]
    for left, right in zip(archive_segments, archive_segments[1:], strict=False):
        gaps.append(_gap(left=left, right=right, gap_type="archive_sampling_gap"))

    live_segments = [
        _build_segment(
            group,
            active_batch_id=active_batch_id,
            evidence=evidence,
        )
        for group, evidence in live_groups
    ]
    for index, (left, right) in enumerate(
        zip(live_segments, live_segments[1:], strict=False)
    ):
        left_points, left_evidence = live_groups[index]
        right_points, right_evidence = live_groups[index + 1]
        gaps.append(
            _gap(
                left=left,
                right=right,
                gap_type=_classify_live_gap(
                    left_points,
                    right_points,
                    left_evidence,
                    right_evidence,
                ),
            )
        )

    if archive_segments and live_segments:
        gaps.append(
            _gap(
                left=archive_segments[-1],
                right=live_segments[0],
                gap_type="source_discontinuity",
            )
        )
    segments.extend(archive_segments)
    segments.extend(live_segments)
    segments.sort(key=lambda segment: (segment.start_at, str(segment.segment_id)))
    gaps.sort(key=lambda gap: (gap.start_at, gap.end_at, str(gap.gap_id)))

    segment_groups = [*archive_groups, *(group for group, _ in live_groups)]
    segment_by_bounds = {
        (
            segment.source_kind,
            segment.start_at,
            segment.end_at,
        ): segment
        for segment in segments
    }
    for group in segment_groups:
        segment = segment_by_bounds[
            (group[0].source_kind, group[0].event_at, group[-1].event_at)
        ]
        for point in group:
            membership[str(point.point_id)] = str(segment.segment_id)
    return TimelineCoverageV1(
        segments=tuple(segments),
        gaps=tuple(gaps),
        point_segment_ids=membership,
    )


def project_timeline_coverage_v1(
    topology: TimelineCoverageV1,
    topology_points: Sequence[TimelinePointV1],
    points: Sequence[TimelinePointV1],
    *,
    effective_from: datetime,
    effective_to: datetime,
) -> TimelineCoverageV1:
    """Project query counts/range while retaining global segment identities."""

    range_start = parse_public_utc_millis_v1(effective_from)
    range_end = parse_public_utc_millis_v1(effective_to)
    if range_start >= range_end:
        raise ValueError("timeline range must be non-empty and increasing")
    range_originals = _validated_originals(topology_points)
    selected = _validated_originals(points)
    if any(
        not range_start <= point.event_at < range_end
        for point in range_originals
    ):
        raise ValueError(
            "topology projection points must be inside the effective range"
        )
    range_ids = {str(point.point_id) for point in range_originals}
    if any(str(point.point_id) not in range_ids for point in selected):
        raise ValueError("timeline projection points must be original topology points")
    if any(
        str(point.point_id) not in topology.point_segment_ids
        for point in range_originals
    ):
        raise ValueError("timeline topology membership is incomplete")

    range_by_segment: dict[str, list[TimelinePointV1]] = defaultdict(list)
    selected_by_segment: dict[str, list[TimelinePointV1]] = defaultdict(list)
    for point in range_originals:
        range_by_segment[topology.point_segment_ids[str(point.point_id)]].append(
            point
        )
    for point in selected:
        selected_by_segment[topology.point_segment_ids[str(point.point_id)]].append(
            point
        )

    segments: list[TimelineSegmentV1] = []
    membership: dict[str, str] = {}
    for segment in topology.segments:
        segment_id = str(segment.segment_id)
        segment_points = selected_by_segment.get(segment_id, [])
        if not segment_points:
            continue
        segment_topology_points = range_by_segment[segment_id]
        payload = segment.model_dump_public()
        payload.update(
            {
                "startAt": serialize_public_utc_millis_v1(
                    segment_topology_points[0].event_at
                ),
                "endAt": serialize_public_utc_millis_v1(
                    segment_topology_points[-1].event_at
                ),
                "totalPoints": len(segment_points),
                "sensorCounts": {
                    "s1": sum(point.sensor_id == "s1" for point in segment_points),
                    "s2": sum(point.sensor_id == "s2" for point in segment_points),
                },
            }
        )
        projected = TimelineSegmentV1.model_validate(payload)
        segments.append(projected)
        for point in segment_points:
            membership[str(point.point_id)] = segment_id

    segment_by_id = {str(segment.segment_id): segment for segment in segments}
    gaps: list[TimelineGapV1] = []
    for gap in topology.gaps:
        start = max(gap.start_at, range_start)
        end = min(gap.end_at, range_end)
        if start >= end:
            continue
        left = (
            None
            if gap.left_segment_id is None
            else segment_by_id.get(str(gap.left_segment_id))
        )
        right = (
            None
            if gap.right_segment_id is None
            else segment_by_id.get(str(gap.right_segment_id))
        )
        if left is not None and left.end_at != start:
            left = None
        if right is not None and right.start_at != end:
            right = None
        if left is None and right is None:
            continue
        gaps.append(
            _bounded_gap(
                left=left,
                right=right,
                start=start,
                end=end,
                gap_type=gap.gap_type,
            )
        )
    return TimelineCoverageV1(
        segments=tuple(segments),
        gaps=tuple(gaps),
        point_segment_ids=membership,
    )


def build_operating_cycles_v1(
    archive_points: Sequence[TimelinePointV1],
    *,
    active_batch_id: str,
    effective_from: datetime,
    effective_to: datetime,
) -> tuple[TimelineOperatingCycleV1, ...]:
    """Build complete active-batch cycle facts intersecting the response range."""

    originals = _validated_originals(archive_points)
    if type(effective_from) is not datetime or type(effective_to) is not datetime:
        raise ValueError("cycle range must use canonical UTC milliseconds")
    range_start = parse_public_utc_millis_v1(effective_from)
    range_end = parse_public_utc_millis_v1(effective_to)
    if range_start >= range_end:
        raise ValueError("cycle range must be non-empty and increasing")
    if any(
        point.source_kind != "historical_archive"
        or point.provenance.batch_id != active_batch_id
        or point.operating_cycle_id is None
        for point in originals
    ):
        raise TimelineCoverageErrorV1("timeline_archive_active_batch_mismatch")

    grouped: dict[str, list[TimelinePointV1]] = defaultdict(list)
    for point in originals:
        grouped[str(point.operating_cycle_id)].append(point)
    facts: list[tuple[datetime, str, tuple[TimelinePointV1, ...]]] = []
    for cycle_id, cycle_points in grouped.items():
        points_tuple = tuple(cycle_points)
        facts.append((points_tuple[0].event_at, cycle_id, points_tuple))
    facts.sort(key=lambda item: (item[0], item[1]))
    intersecting = [
        item
        for item in facts
        if item[2][-1].event_at >= range_start
        and item[2][0].event_at < range_end
    ]

    cycles: list[TimelineOperatingCycleV1] = []
    previous: TimelineOperatingCycleV1 | None = None
    for _, cycle_id, cycle_points in intersecting:
        start = cycle_points[0].event_at
        end = cycle_points[-1].event_at
        if previous is not None and start < previous.end_at:
            raise TimelineCoverageErrorV1("timeline_operating_cycles_overlap")
        cycle = TimelineOperatingCycleV1.model_validate(
            {
                "operatingCycleId": cycle_id,
                "sourceKind": "historical_archive",
                "batchId": active_batch_id,
                "startAt": serialize_public_utc_millis_v1(start),
                "endAt": serialize_public_utc_millis_v1(end),
                "durationSeconds": (end - start).total_seconds(),
                "totalPoints": len(cycle_points),
                "sensorCounts": {
                    "s1": sum(point.sensor_id == "s1" for point in cycle_points),
                    "s2": sum(point.sensor_id == "s2" for point in cycle_points),
                },
                "candidateCount": 0,
                "gapBeforeSeconds": (
                    None
                    if previous is None
                    else (start - previous.end_at).total_seconds()
                ),
                "previousOperatingCycleId": (
                    None if previous is None else str(previous.operating_cycle_id)
                ),
                "assumptions": [],
            }
        )
        cycles.append(cycle)
        previous = cycle
    return tuple(cycles)


__all__ = [
    "TimelineCoverageErrorV1",
    "TimelineCoverageV1",
    "TimelinePolicyEvidenceInvalidV1",
    "TimelineSourceOverlapV1",
    "TimelineUnrepresentableLiveGapV1",
    "build_operating_cycles_v1",
    "build_timeline_coverage_v1",
    "project_timeline_coverage_v1",
]
