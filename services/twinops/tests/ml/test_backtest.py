from datetime import datetime, timedelta, timezone
from importlib.util import find_spec
import json

import pandas as pd
import pytest

from twinops.ml.backtest import (
    WalkForwardFold,
    _steady_alert_seconds,
    build_walk_forward_folds,
    run_backtest,
    run_backtest_csv,
)
from twinops.ml.baseline import BaselineConfig, RobustBaseline


EXPORTER_AVAILABLE = find_spec("twinops.ml.historical_assessments_v1") is not None


def _six_cycle_features():
    start = datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)
    rows = []
    for cycle_id in range(6):
        for offset in range(5):
            rows.append(
                {
                    "event_at": start + timedelta(minutes=cycle_id, seconds=offset),
                    "sensor_id": "s1",
                    "cycle_id": cycle_id,
                    "operating_state": "steady",
                    "feature_valid": True,
                    "velocity_ewma": 0.1 + cycle_id * 0.01 + offset * 0.001,
                    "velocity_slope": 0.001,
                    "velocity_change_point": 0.002,
                    "temperature_deviation": offset * 0.01,
                    "cadence_seconds": 1.0 if offset else None,
                    "quality_flags": (),
                }
            )
    return pd.DataFrame(rows)


def _row_evaluation_frame():
    frame = _six_cycle_features()
    frame["reading_id"] = [f"reading-{index:03d}" for index in range(len(frame))]
    frame["source"] = "forzy-csv"
    frame["is_new_information"] = True
    frame["feature_window_start"] = frame["event_at"] - timedelta(seconds=4)
    frame["feature_window_end"] = frame["event_at"]
    return frame


def test_folds_never_split_cycles_or_use_future_training_rows():
    folds = build_walk_forward_folds(_six_cycle_features(), holdout_count=2)

    assert set(folds[-1].train_cycle_ids).isdisjoint(folds[-1].test_cycle_ids)
    assert max(folds[-1].train_cycle_ids) < min(folds[-1].test_cycle_ids)
    assert folds[-1].test_cycle_ids == (4, 5)
    assert folds[-1].frozen_holdout
    assert [(fold.train_cycle_ids, fold.test_cycle_ids) for fold in folds[:-1]] == [
        ((0, 1), (2,)),
        ((0, 1, 2), (3,)),
    ]


def test_backtest_reports_valid_cycle_metrics_without_label_metrics():
    frame = _six_cycle_features()
    folds = build_walk_forward_folds(frame, holdout_count=2)

    report = run_backtest(frame, RobustBaseline(BaselineConfig()), folds)
    payload = report.to_dict()

    assert {row["cycle_id"] for row in payload["cycle_results"]} == {2, 3, 4, 5}
    assert all(row["regime"] == "steady" for row in payload["cycle_results"])
    assert payload["holdout_frozen"] is True
    assert payload["threshold_stability"]["watch_range"] == 0
    assert payload["threshold_stability"]["alert_range"] == 0
    serialized_keys = str(payload).lower()
    assert "precision" not in serialized_keys
    assert "recall" not in serialized_keys
    assert "f1" not in serialized_keys
    assert "rul" not in serialized_keys


def test_candidate_ranking_is_explicitly_not_ground_truth():
    frame = _six_cycle_features()
    folds = build_walk_forward_folds(frame, holdout_count=2)

    report = run_backtest(frame, RobustBaseline(BaselineConfig()), folds)

    assert report.candidate_events
    assert all(
        event["classification"] == "candidate_not_ground_truth"
        for event in report.candidate_events
    )
    assert all(event["sensor_id"] == "s1" for event in report.candidate_events)


def test_curated_csv_entrypoint_writes_a_verified_bundle(tmp_path):
    input_path = tmp_path / "curated-features.csv"
    output_path = tmp_path / "artifacts"
    _six_cycle_features().to_csv(input_path, index=False)

    report = run_backtest_csv(input_path, output_path)

    assert report.holdout_frozen
    assert (output_path / "pipeline.joblib").is_file()
    assert (output_path / "feature-manifest.json").is_file()
    assert (output_path / "backtest-report.json").is_file()


def test_curated_csv_accepts_mixed_iso_fractional_seconds(tmp_path):
    input_path = tmp_path / "curated-features.csv"
    output_path = tmp_path / "artifacts"
    frame = _six_cycle_features()
    frame["event_at"] = [
        value.isoformat(timespec="seconds" if index % 2 else "milliseconds")
        for index, value in enumerate(frame["event_at"])
    ]
    frame.to_csv(input_path, index=False)

    report = run_backtest_csv(input_path, output_path)

    assert report.holdout_frozen


def test_fold_builder_rejects_cycle_ids_that_contradict_event_chronology():
    frame = _six_cycle_features()
    frame.loc[frame["cycle_id"].eq(5), "event_at"] -= timedelta(minutes=10)

    try:
        build_walk_forward_folds(frame, holdout_count=2)
    except ValueError as error:
        assert "chronolog" in str(error).lower()
    else:
        raise AssertionError("cycle IDs must agree with event chronology")


def test_backtest_rejects_manual_fold_whose_training_reaches_test_time():
    frame = _six_cycle_features()
    frame.loc[frame["cycle_id"].eq(1), "event_at"] += timedelta(minutes=10)
    folds = [WalkForwardFold(train_cycle_ids=(0, 1), test_cycle_ids=(2,))]

    try:
        run_backtest(frame, RobustBaseline(BaselineConfig()), folds)
    except ValueError as error:
        assert "event_at" in str(error)
    else:
        raise AssertionError("training timestamps must be strictly before test")


def test_fold_builder_skips_early_cycles_without_per_sensor_calibration():
    frame = _six_cycle_features()
    second_sensor = frame.copy()
    second_sensor["sensor_id"] = "s2"
    frame = pd.concat([frame, second_sensor], ignore_index=True)
    frame.loc[frame["cycle_id"].isin([0, 1]), "feature_valid"] = False

    folds = build_walk_forward_folds(frame, holdout_count=2)

    assert folds[0].train_cycle_ids == (0, 1, 2)
    assert folds[0].test_cycle_ids == (3,)
    assert folds[-1].frozen_holdout


def test_steady_alert_seconds_only_sums_contiguous_alert_cadence():
    start = datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)
    group = pd.DataFrame(
        {
            "event_at": [start + timedelta(seconds=i) for i in (0, 2, 4, 6, 8)],
            "operating_state": ["steady"] * 5,
            "status": ["alert", "alert", "normal", "alert", "alert"],
            "cadence_seconds": [None, 2.0, 2.0, 2.0, 2.0],
            "quality_flags": [(), (), (), (), ("gap_before",)],
        }
    )

    assert _steady_alert_seconds(group) == 2.0


def test_steady_alert_seconds_rejects_timestamp_jump_that_breaks_cadence():
    start = datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)
    group = pd.DataFrame(
        {
            "event_at": [start, start + timedelta(seconds=100)],
            "operating_state": ["steady", "steady"],
            "status": ["alert", "alert"],
            "cadence_seconds": [None, 2.0],
            "quality_flags": [(), ()],
        }
    )

    assert _steady_alert_seconds(group) == 0.0


@pytest.mark.skipif(not EXPORTER_AVAILABLE, reason="covered by the VS6A RED tracer")
def test_row_evaluator_uses_only_fold_training_and_has_deterministic_order():
    from twinops.ml.backtest import evaluate_walk_forward_rows

    frame = _row_evaluation_frame()
    folds = build_walk_forward_folds(frame, holdout_count=2)

    first = evaluate_walk_forward_rows(frame, RobustBaseline(), folds)
    second = evaluate_walk_forward_rows(frame, RobustBaseline(), folds)

    assert first == second
    assert first.fold_count == 3
    assert first.evaluated_cycle_ids == (2, 3, 4, 5)
    assert first.skipped_cycle_ids == (0, 1)
    assert [(row.anchor_event_at, row.reading_id, row.sensor_id, row.fold_id) for row in first.rows] == sorted(
        (row.anchor_event_at, row.reading_id, row.sensor_id, row.fold_id) for row in first.rows
    )
    assert len({(row.fold_id, row.reading_id) for row in first.rows}) == len(first.rows)
    assert all(row.training_end < row.window_start <= row.window_end <= row.anchor_event_at for row in first.rows)
    assert all(row.fold_model_hash.startswith("sha256:") for row in first.rows)
    assert first.rows[0].training_end == frame.loc[frame.cycle_id.eq(1), "event_at"].max()

    future_mutated = frame.copy()
    future_mutated.loc[future_mutated.cycle_id.eq(5), "velocity_ewma"] = 999_999.0
    replay = evaluate_walk_forward_rows(future_mutated, RobustBaseline(), folds)
    cycle_two = [row for row in first.rows if row.anchor_event_at.minute == 2]
    replay_cycle_two = [row for row in replay.rows if row.anchor_event_at.minute == 2]
    assert cycle_two == replay_cycle_two


@pytest.mark.skipif(not EXPORTER_AVAILABLE, reason="covered by the VS6A RED tracer")
def test_row_evaluator_omits_duplicate_missing_and_non_finite_anchors():
    from twinops.ml.backtest import evaluate_walk_forward_rows

    frame = _row_evaluation_frame()
    folds = build_walk_forward_folds(frame, holdout_count=2)
    test_rows = frame.index[frame.cycle_id.eq(2)].tolist()
    frame.loc[test_rows[0], "is_new_information"] = False
    frame.loc[test_rows[1], "reading_id"] = None
    frame.loc[test_rows[2], "velocity_ewma"] = float("nan")
    frame.loc[test_rows[3], "feature_window_start"] = pd.NaT

    result = evaluate_walk_forward_rows(frame, RobustBaseline(), folds)

    omitted = {f"reading-{index:03d}" for index in (test_rows[0], test_rows[2], test_rows[3])}
    assert omitted.isdisjoint({row.reading_id for row in result.rows})
    assert all(row.reading_id for row in result.rows)
    assert not any(
        row.anchor_event_at == frame.loc[index, "event_at"]
        for index in test_rows[:4]
        for row in result.rows
    )


@pytest.mark.skipif(not EXPORTER_AVAILABLE, reason="covered by the VS6A RED tracer")
def test_row_evaluator_resets_candidate_episode_on_every_causal_break():
    from twinops.ml.backtest import evaluate_walk_forward_rows

    frame = _row_evaluation_frame()
    frame.loc[frame.cycle_id.isin((0, 1)), [
        "velocity_ewma", "velocity_slope", "velocity_change_point", "temperature_deviation"
    ]] = 0.0
    candidate_indexes = frame.index[frame.cycle_id.eq(2)].tolist()
    frame.loc[candidate_indexes, [
        "velocity_ewma", "velocity_slope", "velocity_change_point", "temperature_deviation"
    ]] = 0.0
    frame.loc[candidate_indexes, "velocity_ewma"] = [100.0, 100.0, 0.0, 100.0, 100.0]
    frame.loc[candidate_indexes[3], "quality_flags"] = ("gap_before",)
    folds = [WalkForwardFold(train_cycle_ids=(0, 1), test_cycle_ids=(2,))]

    result = evaluate_walk_forward_rows(
        frame,
        RobustBaseline(BaselineConfig(persistence_seconds=1)),
        folds,
    )
    rows = [row for row in result.rows if row.anchor_event_at.minute == 2]

    assert [row.persistence_count for row in rows] == [1, 2, 0, 1, 2]
    assert rows[0].episode_started_at == rows[0].anchor_event_at
    assert rows[1].episode_started_at == rows[0].anchor_event_at
    assert rows[2].episode_id is None
    assert rows[3].episode_started_at == rows[3].anchor_event_at
    assert rows[4].episode_started_at == rows[3].anchor_event_at
    assert rows[0].status == "watch"
    assert rows[1].status == "alert"
    assert rows[3].status == "watch"
    assert rows[4].status == "alert"


@pytest.mark.skipif(not EXPORTER_AVAILABLE, reason="covered by the VS6A RED tracer")
def test_legacy_top_ten_candidate_event_bytes_remain_unchanged():
    frame = _six_cycle_features()
    report = run_backtest(
        frame,
        RobustBaseline(BaselineConfig()),
        build_walk_forward_folds(frame, holdout_count=2),
    )

    actual = json.dumps(report.candidate_events, sort_keys=True, separators=(",", ":"))
    assert actual == (
        '[{"classification":"candidate_not_ground_truth","cycle_id":5,"fold":2,'
        '"observed_at":"2026-08-12T13:05:04+00:00","score":41.59359683439005,"sensor_id":"s1"},'
        '{"classification":"candidate_not_ground_truth","cycle_id":5,"fold":2,'
        '"observed_at":"2026-08-12T13:05:03+00:00","score":40.469445568595724,"sensor_id":"s1"},'
        '{"classification":"candidate_not_ground_truth","cycle_id":5,"fold":2,'
        '"observed_at":"2026-08-12T13:05:02+00:00","score":39.3452943028014,"sensor_id":"s1"},'
        '{"classification":"candidate_not_ground_truth","cycle_id":2,"fold":0,'
        '"observed_at":"2026-08-12T13:02:04+00:00","score":38.22114303700708,"sensor_id":"s1"},'
        '{"classification":"candidate_not_ground_truth","cycle_id":5,"fold":2,'
        '"observed_at":"2026-08-12T13:05:01+00:00","score":38.221143037007074,"sensor_id":"s1"},'
        '{"classification":"candidate_not_ground_truth","cycle_id":5,"fold":2,'
        '"observed_at":"2026-08-12T13:05:00+00:00","score":37.09699177121274,"sensor_id":"s1"},'
        '{"classification":"candidate_not_ground_truth","cycle_id":2,"fold":0,'
        '"observed_at":"2026-08-12T13:02:03+00:00","score":35.97284050541843,"sensor_id":"s1"},'
        '{"classification":"candidate_not_ground_truth","cycle_id":2,"fold":0,'
        '"observed_at":"2026-08-12T13:02:02+00:00","score":33.724537973829776,"sensor_id":"s1"},'
        '{"classification":"candidate_not_ground_truth","cycle_id":2,"fold":0,'
        '"observed_at":"2026-08-12T13:02:01+00:00","score":31.476235442241123,"sensor_id":"s1"},'
        '{"classification":"candidate_not_ground_truth","cycle_id":4,"fold":2,'
        '"observed_at":"2026-08-12T13:04:04+00:00","score":30.352084176446787,"sensor_id":"s1"}]'
    )
