"""Contract-first coverage for persisted historical assessment series."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import pytest

from twinops.contracts import timeline_v1_models as timeline_models
from twinops.contracts.timeline_v1_models import (
    HistoricalAssessmentV1,
    TimelineAssessmentOverviewV1,
    serialize_public_utc_millis_v1,
)
from twinops.storage.historical_repository_v1 import (
    HistoricalAssessmentRangeQueryV1,
    HistoricalAssessmentSliceV1,
    HistoricalBatchSummaryV1,
    historical_assessment_id_v1,
)
from twinops.timeline import service_v1
from twinops.timeline.assessment_series_v1 import (
    TimelineAssessmentBudgetConflictV1,
    TimelineAssessmentQueryV1,
    TimelineAssessmentRepositoryErrorV1,
    _allocate_quotas,
    _envelope,
    _series_id,
    compose_assessment_overview_v1,
)

from services.twinops.tests.timeline.overview_fixtures_v1 import (
    BATCH_A,
    FakeTimelineRepositoryV1,
    make_point,
    uuid5_text,
)


BASE = datetime(2026, 8, 25, 15, tzinfo=timezone.utc)
SEGMENT = uuid5_text("vs6c-assessment-segment")
BASE_LIMITATIONS = [
    "historical_source_participated_in_baseline_construction_and_evaluation",
    "no_confirmed_failure_labels_available",
    "relative_score_not_failure_probability_confidence_rul_or_diagnosis",
]
_DERIVED = object()


def _assessment(
    index: int,
    *,
    fold_id: str = "walk-forward-fold-1",
    sensor_id: str = "s1",
    score: float | None = 25.0,
    deterioration_score: float | None | object = _DERIVED,
    status: str = "normal",
    training_start: str = "2026-08-25T12:00:00.000Z",
    training_end: str = "2026-08-25T13:00:00.000Z",
):
    event_at = BASE + timedelta(milliseconds=index)
    anchor = make_point(index, event_at=event_at, sensor_id=sensor_id)
    anchor_id = str(anchor.point_id)
    candidate = status in {"watch", "alert"}
    deterioration = (
        None if score is None else score / 2
    ) if deterioration_score is _DERIVED else deterioration_score
    episode_started_at = event_at - timedelta(seconds=1) if candidate else None
    assessment = HistoricalAssessmentV1.model_validate(
        {
            "schemaVersion": "1.0",
            "assessmentId": historical_assessment_id_v1(
                BATCH_A,
                fold_id,
                anchor_id,
            ),
            "foldId": fold_id,
            "sensorId": sensor_id,
            "operatingCycleId": str(anchor.operating_cycle_id),
            "trainingWindow": {
                "start": training_start,
                "end": training_end,
            },
            "assessmentWindow": {
                "start": "2026-08-25T14:00:00.000Z",
                "end": serialize_public_utc_millis_v1(event_at),
            },
            "assessmentAt": serialize_public_utc_millis_v1(event_at),
            "anchorPointId": anchor_id,
            "status": status,
            "anomalyScore": score,
            "deteriorationScore": deterioration,
            "scoreSemantics": (
                "relative_to_walk_forward_historical_baseline_not_failure_probability"
            ),
            "persistence": {
                "episodeId": (
                    str(uuid5(NAMESPACE_URL, f"vs6c-episode|{fold_id}|{index}"))
                    if candidate
                    else None
                ),
                "episodeStartedAt": (
                    serialize_public_utc_millis_v1(episode_started_at)
                    if episode_started_at is not None
                    else None
                ),
                "persistenceSeconds": 1.0 if candidate else 0.0,
                "persistenceCount": 1 if candidate else 0,
            },
            "quality": {
                "status": (
                    "insufficient_data"
                    if status == "insufficient_data"
                    else "ok"
                ),
                "flags": [],
            },
            "evidence": [],
            "modelFamily": "robust-baseline",
            "modelVersion": "1.0.1",
            "modelHash": "sha256:" + "d" * 64,
            "foldHash": "sha256:" + "e" * 64,
            "reportHash": "sha256:" + "f" * 64,
            "componentTag": None,
            "humanValidationRequired": True,
            "limitations": sorted(
                [*BASE_LIMITATIONS]
                + (["candidate_not_ground_truth"] if candidate else [])
            ),
        }
    )
    return assessment, anchor


def _slice(rows):
    assessments = tuple(row[0] for row in rows)
    return HistoricalAssessmentSliceV1(
        assessments=assessments,
        anchors_by_id={str(row[1].point_id): row[1] for row in rows},
    )


def _summary(count: int):
    return HistoricalBatchSummaryV1(
        batch_id=BATCH_A,
        asset_id="forzy-motor-01",
        status="active",
        source_sha256="sha256:" + "6" * 64,
        manifest_sha256="sha256:" + "7" * 64,
        raw_row_count=10,
        sample_count=20,
        operating_cycle_count=2,
        assessment_count=count,
        assessment_manifest_sha256=(
            None if count == 0 else "sha256:" + "9" * 64
        ),
        staged_at=BASE - timedelta(hours=3),
        activated_at=BASE - timedelta(hours=2),
    )


def _query(*, max_points: int = 4000):
    return TimelineAssessmentQueryV1(
        asset_id="forzy-motor-01",
        from_at=None,
        to_at=None,
        sensor_id=None,
        max_points=max_points,
    )


def test_downsample_preserves_first_min_max_last_and_candidate_copy() -> None:
    rows = []
    for index in range(50):
        score = 100.0 if index == 17 else 0.0 if index == 23 else 40.0 + index % 10
        rows.append(
            _assessment(
                index,
                score=score,
                status="alert" if index == 17 else "normal",
            )
        )
    result = compose_assessment_overview_v1(
        query=_query(max_points=40),
        active_batch=_summary(50),
        assessment_slice=_slice(rows),
        point_segment_ids={str(anchor.point_id): SEGMENT for _, anchor in rows},
    )

    assert isinstance(result, TimelineAssessmentOverviewV1)
    assert result.materialization.assessment_count == 50
    assert result.aggregation_summary.original_assessment_count == 50
    assert result.aggregation_summary.returned_assessment_count == 40
    assert result.aggregation_summary.omitted_assessment_count == 10
    assert len(result.series) == 1
    series = result.series[0]
    assert series.aggregation.method == "time_bucket_envelope_v1"
    returned = {str(point.anchor_point_id) for point in series.points}
    for index in (0, 17, 23, 49):
        assert str(rows[index][1].point_id) in returned
    assert series.limitations == sorted(
        [*BASE_LIMITATIONS, "candidate_not_ground_truth"]
    )
    TimelineAssessmentOverviewV1.model_validate(result.model_dump_public())


def test_budget_rejects_when_single_point_candidate_episodes_exceed_it() -> None:
    rows = [
        _assessment(
            index,
            score=25.0,
            deterioration_score=12.5,
            status=(
                "normal"
                if index % 2 == 0
                else ("watch" if index % 4 == 1 else "alert")
            ),
        )
        for index in range(100)
    ]

    with pytest.raises(
        TimelineAssessmentBudgetConflictV1,
        match="complete assessment envelope",
    ):
        compose_assessment_overview_v1(
            query=_query(max_points=40),
            active_batch=_summary(100),
            assessment_slice=_slice(rows),
            point_segment_ids={
                str(anchor.point_id): SEGMENT for _, anchor in rows
            },
        )


def test_envelope_preserves_first_and_last_point_of_each_candidate_run() -> None:
    candidate_indexes = {*range(3, 7), *range(12, 17)}
    rows = [
        _assessment(
            index,
            score=25.0,
            deterioration_score=12.5,
            status=(
                "normal"
                if index not in candidate_indexes
                else ("watch" if index % 2 else "alert")
            ),
        )
        for index in range(20)
    ]

    selected = _envelope(tuple(row[0] for row in rows), quota=6)

    assert [str(item.anchor_point_id) for item in selected] == [
        str(rows[index][1].point_id) for index in (0, 3, 6, 12, 16, 19)
    ]


def test_candidate_boundaries_and_null_run_boundaries_are_never_bridged() -> None:
    rows = [
        _assessment(0, score=25.0, deterioration_score=12.5),
        _assessment(1, score=25.0, deterioration_score=12.5, status="watch"),
        _assessment(2, score=25.0, deterioration_score=12.5, status="alert"),
        _assessment(3, score=25.0, deterioration_score=12.5, status="watch"),
        _assessment(4, score=None, status="insufficient_data"),
        _assessment(5, score=None, status="insufficient_data"),
        _assessment(6, score=25.0, deterioration_score=12.5, status="alert"),
        _assessment(7, score=25.0, deterioration_score=12.5, status="watch"),
        _assessment(8, score=25.0, deterioration_score=12.5, status="alert"),
        _assessment(9, score=25.0, deterioration_score=12.5),
    ]

    selected = _envelope(tuple(row[0] for row in rows), quota=8)

    assert [str(item.anchor_point_id) for item in selected] == [
        str(rows[index][1].point_id)
        for index in (0, 1, 3, 4, 5, 6, 8, 9)
    ]


def test_candidate_floor_equal_to_budget_is_deterministic_across_series() -> None:
    groups = []
    expected_ids: dict[str, set[str]] = {}
    group_index = 0
    for sensor_id in ("s1", "s2"):
        for fold_id in ("fold-a", "fold-b"):
            key = f"{sensor_id}-{fold_id}"
            rows = [
                _assessment(
                    group_index * 100 + index,
                    sensor_id=sensor_id,
                    fold_id=fold_id,
                    score=25.0,
                    deterioration_score=12.5,
                    status=("watch" if index % 2 else "normal"),
                )
                for index in range(18)
            ]
            items = tuple(row[0] for row in rows)
            groups.append((key, items))
            expected_ids[key] = {
                str(rows[0][1].point_id),
                *(str(rows[index][1].point_id) for index in range(1, 18, 2)),
            }
            group_index += 1

    quotas = _allocate_quotas(groups, max_points=40)

    assert quotas == {
        "s1-fold-a": 10,
        "s1-fold-b": 10,
        "s2-fold-a": 10,
        "s2-fold-b": 10,
    }
    assert _allocate_quotas(groups, max_points=40) == quotas
    for key, items in groups:
        selected = _envelope(items, quota=quotas[key])
        assert {str(item.anchor_point_id) for item in selected} == expected_ids[key]


def test_series_grouping_matches_the_javascript_stable_json_key() -> None:
    key_builder = getattr(
        timeline_models,
        "timeline_assessment_series_key_v1",
        None,
    )
    assert callable(key_builder), "stable assessment series key is missing"
    expected_first_key = (
        '["'
        + SEGMENT
        + '","s1","robust-baseline","1.0.1","sha256:'
        + "d" * 64
        + '","walk-forward-fold-1","sha256:'
        + "e" * 64
        + '","sha256:'
        + "f" * 64
        + '","relative_to_walk_forward_historical_baseline_not_failure_probability",'
        '{"end":"2026-08-25T13:00:00.000Z",'
        '"start":"2026-08-25T12:00:00.000Z"}]'
    )
    assert key_builder(
        segment_id=SEGMENT,
        sensor_id="s1",
        model_family="robust-baseline",
        model_version="1.0.1",
        model_hash="sha256:" + "d" * 64,
        fold_id="walk-forward-fold-1",
        fold_hash="sha256:" + "e" * 64,
        report_hash="sha256:" + "f" * 64,
        score_semantics=(
            "relative_to_walk_forward_historical_baseline_not_failure_probability"
        ),
        training_window={
            "start": "2026-08-25T12:00:00.000Z",
            "end": "2026-08-25T13:00:00.000Z",
        },
    ) == expected_first_key
    collision_left = key_builder(
        segment_id=SEGMENT,
        sensor_id="s1",
        model_family="family|version",
        model_version="value",
        model_hash="sha256:" + "d" * 64,
        fold_id="walk-forward-fold-1",
        fold_hash="sha256:" + "e" * 64,
        report_hash="sha256:" + "f" * 64,
        score_semantics="relative",
        training_window={
            "start": "2026-08-25T12:00:00.000Z",
            "end": "2026-08-25T13:00:00.000Z",
        },
    )
    collision_right = key_builder(
        segment_id=SEGMENT,
        sensor_id="s1",
        model_family="family",
        model_version="version|value",
        model_hash="sha256:" + "d" * 64,
        fold_id="walk-forward-fold-1",
        fold_hash="sha256:" + "e" * 64,
        report_hash="sha256:" + "f" * 64,
        score_semantics="relative",
        training_window={
            "start": "2026-08-25T12:00:00.000Z",
            "end": "2026-08-25T13:00:00.000Z",
        },
    )
    assert collision_left != collision_right
    assert _series_id(BATCH_A, collision_left) != _series_id(
        BATCH_A,
        collision_right,
    )

    earlier_start_later_end = _assessment(
        0,
        training_start="2026-08-25T11:00:00.000Z",
        training_end="2026-08-25T13:30:00.000Z",
    )
    later_start_earlier_end = _assessment(
        1,
        training_start="2026-08-25T12:00:00.000Z",
        training_end="2026-08-25T13:00:00.000Z",
    )
    rows = [earlier_start_later_end, later_start_earlier_end]

    result = compose_assessment_overview_v1(
        query=_query(),
        active_batch=_summary(2),
        assessment_slice=_slice(rows),
        point_segment_ids={str(anchor.point_id): SEGMENT for _, anchor in rows},
    )

    assert [
        series.training_window.model_dump_public()
        for series in result.series
    ] == [
        {
            "start": "2026-08-25T12:00:00.000Z",
            "end": "2026-08-25T13:00:00.000Z",
        },
        {
            "start": "2026-08-25T11:00:00.000Z",
            "end": "2026-08-25T13:30:00.000Z",
        },
    ]


def test_composer_rejects_an_untyped_active_batch_summary() -> None:
    with pytest.raises(
        TimelineAssessmentRepositoryErrorV1,
        match="active historical batch summary",
    ):
        compose_assessment_overview_v1(
            query=_query(),
            active_batch=SimpleNamespace(
                batch_id=BATCH_A,
                assessment_count=0,
                assessment_manifest_sha256=None,
            ),
            assessment_slice=_slice([]),
            point_segment_ids={},
        )


def test_envelope_preserves_independent_extrema_for_both_visible_scores() -> None:
    shapes = (
        (40.0, 40.0),
        (0.0, 50.0),
        (100.0, 60.0),
        (50.0, 0.0),
        (60.0, 100.0),
        (55.0, 55.0),
        (52.0, 52.0),
        (45.0, 45.0),
    )
    rows = [
        _assessment(index, score=anomaly, deterioration_score=deterioration)
        for index, (anomaly, deterioration) in enumerate(shapes)
    ]

    selected = _envelope(tuple(row[0] for row in rows), quota=6)

    assert [str(item.anchor_point_id) for item in selected] == [
        str(rows[index][1].point_id) for index in (0, 1, 2, 3, 4, 7)
    ]


def test_envelope_preserves_both_boundaries_of_null_score_runs() -> None:
    rows = [
        *[
            _assessment(
                index,
                score=10.0 + index,
                deterioration_score=20.0 + index,
            )
            for index in range(5)
        ],
        _assessment(5, score=None, status="insufficient_data"),
        _assessment(6, score=None, status="insufficient_data"),
        *[
            _assessment(
                index,
                score=30.0 + index,
                deterioration_score=40.0 + index,
            )
            for index in range(7, 12)
        ],
    ]

    selected = _envelope(tuple(row[0] for row in rows), quota=6)

    assert [item.status for item in selected] == [
        "normal",
        "normal",
        "insufficient_data",
        "insufficient_data",
        "normal",
        "normal",
    ]
    assert [str(item.anchor_point_id) for item in selected] == [
        str(rows[index][1].point_id) for index in (0, 4, 5, 6, 7, 11)
    ]


def test_envelope_distributes_extra_slots_across_the_whole_time_range() -> None:
    rows = []
    for index in range(120):
        anomaly = 20.0 + index % 5
        deterioration = 30.0 + index % 7
        if index in {10, 50, 90}:
            anomaly = {10: 100.0, 50: 90.0, 90: 80.0}[index]
        if index in {30, 70, 110}:
            deterioration = {30: 95.0, 70: 85.0, 110: 75.0}[index]
        rows.append(
            _assessment(
                index,
                score=anomaly,
                deterioration_score=deterioration,
            )
        )

    selected = _envelope(tuple(row[0] for row in rows), quota=12)
    selected_ids = {str(item.anchor_point_id) for item in selected}
    selected_indexes = {
        index
        for index, (_, anchor) in enumerate(rows)
        if str(anchor.point_id) in selected_ids
    }

    assert len(selected_indexes) == 12
    for start in range(0, 120, 20):
        assert any(start <= index < start + 20 for index in selected_indexes)
    assert {50, 90, 110} <= selected_indexes


def test_quota_tail_is_spread_across_canonical_sensors_and_folds() -> None:
    groups = []
    keys = (
        "s1-fold-a",
        "s1-fold-b",
        "s1-fold-c",
        "s2-fold-a",
        "s2-fold-b",
        "s2-fold-c",
    )
    for group_index, key in enumerate(keys):
        groups.append(
            (
                key,
                tuple(
                    _assessment(
                        group_index * 10 + index,
                        sensor_id=key[:2],
                        fold_id=key,
                        score=25.0,
                        deterioration_score=12.5,
                    )[0]
                    for index in range(7)
                ),
            )
        )

    quotas = _allocate_quotas(groups, max_points=15)

    assert [quotas[key] for key in keys] == [2, 3, 2, 3, 2, 3]
    assert _allocate_quotas(groups, max_points=15) == quotas


def test_budget_below_complete_envelope_floor_fails_without_collapsing_folds() -> None:
    shapes = (
        (40.0, 40.0),
        (0.0, 50.0),
        (100.0, 60.0),
        (50.0, 0.0),
        (60.0, 100.0),
        (45.0, 45.0),
    )
    rows = [
        _assessment(
            fold_index * 6 + point_index,
            fold_id=f"walk-forward-fold-{fold_index:02d}",
            score=anomaly,
            deterioration_score=deterioration,
        )
        for fold_index in range(7)
        for point_index, (anomaly, deterioration) in enumerate(shapes)
    ]

    with pytest.raises(
        TimelineAssessmentBudgetConflictV1,
        match="complete assessment envelope",
    ):
        compose_assessment_overview_v1(
            query=_query(max_points=40),
            active_batch=_summary(42),
            assessment_slice=_slice(rows),
            point_segment_ids={
                str(anchor.point_id): SEGMENT for _, anchor in rows
            },
        )


def test_materialized_batch_with_filtered_zero_preserves_global_attestation() -> None:
    result = compose_assessment_overview_v1(
        query=_query(),
        active_batch=_summary(204),
        assessment_slice=HistoricalAssessmentSliceV1(
            assessments=(),
            anchors_by_id={},
        ),
        point_segment_ids={},
    )

    assert result.active_historical_batch_id == BATCH_A
    assert result.materialization.state == "materialized"
    assert result.materialization.assessment_count == 204
    assert result.materialization.assessment_manifest_sha256 == "sha256:" + "9" * 64
    assert result.effective_range is None
    assert result.series == []
    assert result.aggregation_summary.original_assessment_count == 0


class _AssessmentRepository(FakeTimelineRepositoryV1):
    def __init__(
        self,
        rows,
        *,
        switch_after_range: bool = False,
        extra_archive=(),
    ):
        super().__init__(
            archive=tuple(
                sorted(
                    (*tuple(row[1] for row in rows), *extra_archive),
                    key=lambda point: (
                        point.event_at,
                        str(point.sample_pair_id),
                        point.sensor_id,
                        str(point.point_id),
                    ),
                )
            )
        )
        self.rows = rows
        self.switch_after_range = switch_after_range
        self.assessment_range_reads: list[HistoricalAssessmentRangeQueryV1] = []

    def active_batch_summary(self, asset_id: str):
        assert asset_id == "forzy-motor-01"
        return _summary(len(self.rows))

    def historical_assessments(self, query: HistoricalAssessmentRangeQueryV1):
        self.assessment_range_reads.append(query)
        selected = [
            row
            for row in self.rows
            if query.from_at <= row[0].assessment_at < query.to_at
            and (query.sensor_id is None or row[0].sensor_id == query.sensor_id)
        ]
        result = _slice(selected)
        if self.switch_after_range:
            self.batch_id = "sha256:" + "c" * 64
        return result

    def historical_assessment_for_anchor(self, batch_id, anchor_point_id):
        self.assessment_anchor_reads.append((batch_id, anchor_point_id))
        return next(
            (
                assessment
                for assessment, _ in self.rows
                if str(assessment.anchor_point_id) == anchor_point_id
            ),
            None,
        )


def test_service_reads_persisted_range_once_and_rechecks_active_batch() -> None:
    rows = [_assessment(index) for index in range(5)]
    repository = _AssessmentRepository(rows)
    service = service_v1.TimelineServiceV1(repository)
    query = TimelineAssessmentQueryV1(
        asset_id="forzy-motor-01",
        from_at=BASE + timedelta(milliseconds=1),
        to_at=BASE + timedelta(milliseconds=4),
        sensor_id="s1",
        max_points=40,
    )

    result = service.assessments(query)

    assert result.materialization.assessment_count == 5
    assert result.aggregation_summary.original_assessment_count == 3
    assert len(repository.assessment_range_reads) == 1
    persisted_query = repository.assessment_range_reads[0]
    assert persisted_query.from_at == query.from_at
    assert persisted_query.to_at == query.to_at
    assert persisted_query.sensor_id == "s1"
    assert repository.active_batch_id_calls == 3


def test_service_assessment_range_fails_if_active_batch_changes_after_read() -> None:
    rows = [_assessment(index) for index in range(2)]
    repository = _AssessmentRepository(rows, switch_after_range=True)

    with pytest.raises(service_v1.TimelineOverviewSnapshotConflictV1):
        service_v1.TimelineServiceV1(repository).assessments(_query())

    assert len(repository.assessment_range_reads) == 1


def test_context_returns_assessment_only_for_the_exact_original_anchor() -> None:
    rows = [_assessment(0)]
    paired_s2 = make_point(
        500,
        event_at=BASE,
        sensor_id="s2",
        pair_key="0",
    )
    repository = _AssessmentRepository(rows, extra_archive=(paired_s2,))
    context = service_v1.TimelineServiceV1(repository).context(
        service_v1.TimelineContextQueryV1(
            asset_id="forzy-motor-01",
            point_id=str(rows[0][1].point_id),
        )
    )

    assert context.assessment == rows[0][0]
    assert context.decision_facts.condition_state == "normal"
    assert context.decision_facts.condition_source == "historical_walk_forward"
    assert context.provenance.assessment_source == "historical_walk_forward"
    assert context.capabilities.causal_assessment is True
    assert context.capabilities.baseline_comparison is True
    assert context.limitations == BASE_LIMITATIONS
    assert repository.assessment_anchor_reads == [
        (BATCH_A, str(rows[0][1].point_id))
    ]
    assert repository.active_batch_id_calls == 4
