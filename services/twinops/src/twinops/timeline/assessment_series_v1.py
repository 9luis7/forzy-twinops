"""Read-only composition of comparable persisted historical assessment series."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import NAMESPACE_URL, uuid5

from twinops.contracts.timeline_v1_models import (
    HistoricalAssessmentV1,
    TimelineAssessmentOverviewV1,
    parse_public_utc_millis_v1,
    public_millisecond_successor_v1,
    serialize_public_utc_millis_v1,
    timeline_assessment_series_key_v1,
)

if TYPE_CHECKING:
    from twinops.storage.historical_repository_v1 import (
        HistoricalAssessmentSliceV1,
        HistoricalBatchSummaryV1,
    )


_BASE_LIMITATIONS = [
    "historical_source_participated_in_baseline_construction_and_evaluation",
    "no_confirmed_failure_labels_available",
    "relative_score_not_failure_probability_confidence_rul_or_diagnosis",
]


class TimelineAssessmentBudgetConflictV1(ValueError):
    """Raised when the request budget cannot represent every comparable series."""


class TimelineAssessmentRepositoryErrorV1(RuntimeError):
    """Raised when persisted assessment evidence crosses the active snapshot."""


@dataclass(frozen=True)
class TimelineAssessmentQueryV1:
    asset_id: str
    from_at: datetime | None
    to_at: datetime | None
    sensor_id: Literal["s1", "s2"] | None
    max_points: int = 4000

    def __post_init__(self) -> None:
        if self.asset_id != "forzy-motor-01":
            raise ValueError("unknown timeline asset")
        if self.from_at is not None:
            parse_public_utc_millis_v1(self.from_at)
        if self.to_at is not None:
            parse_public_utc_millis_v1(self.to_at)
        if (
            self.from_at is not None
            and self.to_at is not None
            and self.from_at >= self.to_at
        ):
            raise ValueError("assessment range must be non-empty and increasing")
        if self.sensor_id not in {None, "s1", "s2"}:
            raise ValueError("sensor ID must be s1 or s2")
        if type(self.max_points) is not int or not 40 <= self.max_points <= 4000:
            raise ValueError("assessment maxPoints must be between 40 and 4000")


def _requested_range(query: TimelineAssessmentQueryV1) -> dict[str, str | None]:
    return {
        "from": (
            None
            if query.from_at is None
            else serialize_public_utc_millis_v1(query.from_at)
        ),
        "to": (
            None
            if query.to_at is None
            else serialize_public_utc_millis_v1(query.to_at)
        ),
    }


def _empty_overview(
    query: TimelineAssessmentQueryV1,
    *,
    active_batch_id: str | None,
    state: str,
    assessment_count: int,
    assessment_manifest_sha256: str | None,
) -> TimelineAssessmentOverviewV1:
    return TimelineAssessmentOverviewV1.model_validate(
        {
            "schemaVersion": "1.0",
            "assetId": query.asset_id,
            "activeHistoricalBatchId": active_batch_id,
            "requestedRange": _requested_range(query),
            "effectiveRange": None,
            "materialization": {
                "state": state,
                "assessmentCount": assessment_count,
                "assessmentManifestSha256": assessment_manifest_sha256,
            },
            "aggregationSummary": {
                "requestedMaxPoints": query.max_points,
                "originalAssessmentCount": 0,
                "returnedAssessmentCount": 0,
                "omittedAssessmentCount": 0,
                "reducedSeriesCount": 0,
            },
            "series": [],
        }
    )


def _group_key(
    assessment: HistoricalAssessmentV1,
    segment_id: str,
) -> str:
    return timeline_assessment_series_key_v1(
        segment_id=segment_id,
        sensor_id=assessment.sensor_id,
        model_family=assessment.model_family,
        model_version=assessment.model_version,
        model_hash=assessment.model_hash,
        fold_id=assessment.fold_id,
        fold_hash=assessment.fold_hash,
        report_hash=assessment.report_hash,
        score_semantics=assessment.score_semantics,
        training_window=assessment.training_window.model_dump_public(),
    )


def _series_id(batch_id: str, key: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "|".join(("timeline-assessment-series-v1", batch_id, key)),
        )
    )


def _assessment_order(assessment: HistoricalAssessmentV1) -> tuple[object, ...]:
    return (
        assessment.assessment_at,
        str(assessment.anchor_point_id),
        str(assessment.assessment_id),
    )


def _is_evaluable(assessment: HistoricalAssessmentV1) -> bool:
    return assessment.anomaly_score is not None


def _score_extrema(
    assessments: tuple[HistoricalAssessmentV1, ...],
    indexes: range,
    field: Literal["anomaly_score", "deterioration_score"],
) -> tuple[int, int]:
    def score(index: int) -> float:
        value = getattr(assessments[index], field)
        assert value is not None
        return value

    minimum = min(
        indexes,
        key=lambda index: (score(index), _assessment_order(assessments[index])),
    )
    maximum = min(
        indexes,
        key=lambda index: (-score(index), _assessment_order(assessments[index])),
    )
    return minimum, maximum


def _required_envelope_indices(
    assessments: tuple[HistoricalAssessmentV1, ...],
) -> set[int]:
    required: set[int] = set()
    start = 0
    while start < len(assessments):
        evaluable = _is_evaluable(assessments[start])
        end = start + 1
        while end < len(assessments) and (
            _is_evaluable(assessments[end]) == evaluable
        ):
            end += 1
        indexes = range(start, end)
        required.update((start, end - 1))
        if evaluable:
            required.update(_score_extrema(assessments, indexes, "anomaly_score"))
            required.update(
                _score_extrema(assessments, indexes, "deterioration_score")
            )
        start = end
    return required


def _uniform_spread_positions(count: int, take: int) -> tuple[int, ...]:
    if take <= 0:
        return ()
    if take >= count:
        return tuple(range(count))
    return tuple(
        ((2 * index + 1) * count) // (2 * take)
        for index in range(take)
    )


def _time_bucket_ranges(
    assessments: tuple[HistoricalAssessmentV1, ...],
    bucket_count: int,
) -> tuple[range, ...]:
    if not assessments:
        return ()
    if bucket_count <= 1:
        return (range(0, len(assessments)),)
    first_at = assessments[0].assessment_at
    last_at = assessments[-1].assessment_at
    span_microseconds = int(
        (last_at - first_at).total_seconds() * 1_000_000
    ) + 1_000
    buckets: list[list[int]] = [[] for _ in range(bucket_count)]
    for index, assessment in enumerate(assessments):
        elapsed_microseconds = int(
            (assessment.assessment_at - first_at).total_seconds() * 1_000_000
        )
        bucket = min(
            bucket_count - 1,
            elapsed_microseconds * bucket_count // span_microseconds,
        )
        buckets[bucket].append(index)
    return tuple(
        range(indexes[0], indexes[-1] + 1)
        for indexes in buckets
        if indexes
    )


def _ordered_bucket_candidates(
    assessments: tuple[HistoricalAssessmentV1, ...],
    indexes: range,
    *,
    prefer_deterioration: bool,
) -> tuple[int, ...]:
    candidates: list[int] = []

    def append(index: int) -> None:
        if index not in candidates:
            candidates.append(index)

    start = indexes.start
    while start < indexes.stop:
        evaluable = _is_evaluable(assessments[start])
        end = start + 1
        while end < indexes.stop and (
            _is_evaluable(assessments[end]) == evaluable
        ):
            end += 1
        run = range(start, end)
        if evaluable:
            anomaly_min, anomaly_max = _score_extrema(
                assessments,
                run,
                "anomaly_score",
            )
            deterioration_min, deterioration_max = _score_extrema(
                assessments,
                run,
                "deterioration_score",
            )
            score_candidates = (
                (
                    deterioration_max,
                    anomaly_max,
                    deterioration_min,
                    anomaly_min,
                )
                if prefer_deterioration
                else (
                    anomaly_max,
                    deterioration_max,
                    anomaly_min,
                    deterioration_min,
                )
            )
            for index in (*score_candidates, start, end - 1):
                append(index)
        else:
            append(start)
            append(end - 1)
        start = end
    return tuple(candidates)


def _envelope(
    assessments: tuple[HistoricalAssessmentV1, ...],
    quota: int,
) -> tuple[HistoricalAssessmentV1, ...]:
    if quota >= len(assessments):
        return assessments
    required = _required_envelope_indices(assessments)
    if quota < len(required):
        raise TimelineAssessmentBudgetConflictV1(
            "requested maxPoints is below the complete assessment envelope"
        )
    selected = set(required)
    bucket_count = max(1, (quota + 1) // 2)
    bucket_candidates = [
        tuple(
            index
            for index in _ordered_bucket_candidates(
                assessments,
                indexes,
                prefer_deterioration=bucket_index % 2 == 1,
            )
            if index not in required
        )
        for bucket_index, indexes in enumerate(
            _time_bucket_ranges(assessments, bucket_count)
        )
    ]
    rank = 0
    while len(selected) < quota:
        available = [
            candidates[rank]
            for candidates in bucket_candidates
            if rank < len(candidates) and candidates[rank] not in selected
        ]
        if not available:
            if all(rank >= len(candidates) for candidates in bucket_candidates):
                break
            rank += 1
            continue
        remaining = quota - len(selected)
        for position in _uniform_spread_positions(len(available), remaining):
            selected.add(available[position])
        rank += 1
    if len(selected) < quota:
        available = [
            index
            for index in range(len(assessments))
            if index not in selected
        ]
        remaining = quota - len(selected)
        selected.update(
            available[position]
            for position in _uniform_spread_positions(
                len(available),
                remaining,
            )
        )
    if len(selected) > quota:
        removable = sorted(selected.difference(required), reverse=True)
        while len(selected) > quota:
            selected.remove(removable.pop(0))
    return tuple(assessments[index] for index in sorted(selected))


def _allocate_quotas(
    groups: list[tuple[str, tuple[HistoricalAssessmentV1, ...]]],
    max_points: int,
) -> dict[str, int]:
    quotas = {
        key: len(_required_envelope_indices(items))
        for key, items in groups
    }
    minimum = sum(quotas.values())
    if minimum > max_points:
        raise TimelineAssessmentBudgetConflictV1(
            "requested maxPoints is below the complete assessment envelope"
        )
    remaining = max_points - minimum
    while remaining:
        eligible = [
            key
            for key, items in groups
            if quotas[key] < len(items)
        ]
        if not eligible:
            break
        take = min(remaining, len(eligible))
        for position in _uniform_spread_positions(len(eligible), take):
            quotas[eligible[position]] += 1
        remaining -= take
    return quotas


def compose_assessment_overview_v1(
    *,
    query: TimelineAssessmentQueryV1,
    active_batch,
    assessment_slice: HistoricalAssessmentSliceV1,
    point_segment_ids: dict[str, str],
) -> TimelineAssessmentOverviewV1:
    """Compose persisted rows only; no scorer, interpolation, or nearest lookup."""

    if not isinstance(query, TimelineAssessmentQueryV1):
        raise ValueError("assessment overview requires TimelineAssessmentQueryV1")
    from twinops.storage.historical_repository_v1 import (
        HistoricalAssessmentSliceV1,
        HistoricalBatchSummaryV1,
    )

    if not isinstance(assessment_slice, HistoricalAssessmentSliceV1):
        raise TimelineAssessmentRepositoryErrorV1(
            "assessment repository returned an invalid slice"
        )
    if active_batch is not None and (
        not isinstance(active_batch, HistoricalBatchSummaryV1)
        or active_batch.asset_id != query.asset_id
        or active_batch.status != "active"
    ):
        raise TimelineAssessmentRepositoryErrorV1(
            "active historical batch summary is invalid"
        )
    if active_batch is None:
        if assessment_slice.assessments:
            raise TimelineAssessmentRepositoryErrorV1(
                "assessment rows exist without an active historical batch"
            )
        return _empty_overview(
            query,
            active_batch_id=None,
            state="no_active_historical_batch",
            assessment_count=0,
            assessment_manifest_sha256=None,
        )

    batch_id = active_batch.batch_id
    assessment_count = active_batch.assessment_count
    manifest = active_batch.assessment_manifest_sha256
    if (assessment_count == 0) != (manifest is None):
        raise TimelineAssessmentRepositoryErrorV1(
            "active assessment materialization metadata is inconsistent"
        )
    if assessment_count == 0:
        if assessment_slice.assessments:
            raise TimelineAssessmentRepositoryErrorV1(
                "unmaterialized active batch returned assessment rows"
            )
        return _empty_overview(
            query,
            active_batch_id=batch_id,
            state="not_materialized",
            assessment_count=0,
            assessment_manifest_sha256=None,
        )
    if len(assessment_slice.assessments) > assessment_count:
        raise TimelineAssessmentRepositoryErrorV1(
            "filtered assessment rows exceed the global materialization"
        )
    if not assessment_slice.assessments:
        return _empty_overview(
            query,
            active_batch_id=batch_id,
            state="materialized",
            assessment_count=assessment_count,
            assessment_manifest_sha256=manifest,
        )

    grouped: dict[str, list[HistoricalAssessmentV1]] = {}
    for assessment in assessment_slice.assessments:
        anchor_id = str(assessment.anchor_point_id)
        anchor = assessment_slice.anchors_by_id[anchor_id]
        segment_id = point_segment_ids.get(anchor_id)
        if (
            segment_id is None
            or anchor.provenance.batch_id != batch_id
            or (query.sensor_id is not None and assessment.sensor_id != query.sensor_id)
            or (query.from_at is not None and assessment.assessment_at < query.from_at)
            or (query.to_at is not None and assessment.assessment_at >= query.to_at)
        ):
            raise TimelineAssessmentRepositoryErrorV1(
                "assessment rows crossed the active filtered snapshot"
            )
        grouped.setdefault(_group_key(assessment, segment_id), []).append(assessment)
    groups = [
        (key, tuple(sorted(items, key=_assessment_order)))
        for key, items in sorted(grouped.items())
    ]
    quotas = _allocate_quotas(groups, query.max_points)
    series_payloads: list[dict[str, object]] = []
    returned_total = 0
    reduced_total = 0
    for key, originals in groups:
        selected = _envelope(originals, quotas[key])
        candidate = any(item.status in {"watch", "alert"} for item in selected)
        limitations = sorted(
            [*_BASE_LIMITATIONS]
            + (["candidate_not_ground_truth"] if candidate else [])
        )
        first = originals[0]
        segment_id = point_segment_ids[str(first.anchor_point_id)]
        omitted = len(originals) - len(selected)
        series_payloads.append(
            {
                "seriesId": _series_id(batch_id, key),
                "segmentId": segment_id,
                "sensorId": first.sensor_id,
                "modelFamily": first.model_family,
                "modelVersion": first.model_version,
                "modelHash": first.model_hash,
                "foldId": first.fold_id,
                "foldHash": first.fold_hash,
                "reportHash": first.report_hash,
                "scoreSemantics": first.score_semantics,
                "trainingWindow": first.training_window.model_dump_public(),
                "humanValidationRequired": True,
                "groundTruthLabelsAvailable": False,
                "limitations": limitations,
                "aggregation": {
                    "method": "none" if omitted == 0 else "time_bucket_envelope_v1",
                    "requestedMaxPoints": query.max_points,
                    "originalAssessmentCount": len(originals),
                    "returnedAssessmentCount": len(selected),
                    "omittedAssessmentCount": omitted,
                },
                "points": [
                    {
                        "assessmentId": str(item.assessment_id),
                        "anchorPointId": str(item.anchor_point_id),
                        "eventAt": serialize_public_utc_millis_v1(item.assessment_at),
                        "anomalyScore": item.anomaly_score,
                        "deteriorationScore": item.deterioration_score,
                        "status": item.status,
                        "qualityStatus": item.quality.status,
                        "candidateState": (
                            "candidate_not_ground_truth"
                            if item.status in {"watch", "alert"}
                            else None
                        ),
                    }
                    for item in selected
                ],
            }
        )
        returned_total += len(selected)
        reduced_total += int(omitted > 0)
    first_at = min(item.assessment_at for item in assessment_slice.assessments)
    last_at = max(item.assessment_at for item in assessment_slice.assessments)
    return TimelineAssessmentOverviewV1.model_validate(
        {
            "schemaVersion": "1.0",
            "assetId": query.asset_id,
            "activeHistoricalBatchId": batch_id,
            "requestedRange": _requested_range(query),
            "effectiveRange": {
                "from": serialize_public_utc_millis_v1(first_at),
                "to": serialize_public_utc_millis_v1(
                    public_millisecond_successor_v1(last_at)
                ),
            },
            "materialization": {
                "state": "materialized",
                "assessmentCount": assessment_count,
                "assessmentManifestSha256": manifest,
            },
            "aggregationSummary": {
                "requestedMaxPoints": query.max_points,
                "originalAssessmentCount": len(assessment_slice.assessments),
                "returnedAssessmentCount": returned_total,
                "omittedAssessmentCount": (
                    len(assessment_slice.assessments) - returned_total
                ),
                "reducedSeriesCount": reduced_total,
            },
            "series": series_payloads,
        }
    )


__all__ = [
    "TimelineAssessmentBudgetConflictV1",
    "TimelineAssessmentQueryV1",
    "TimelineAssessmentRepositoryErrorV1",
    "compose_assessment_overview_v1",
]
