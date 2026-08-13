from datetime import datetime, timedelta, timezone

import pandas as pd

from twinops.ml.backtest import (
    WalkForwardFold,
    _steady_alert_seconds,
    build_walk_forward_folds,
    run_backtest,
    run_backtest_csv,
)
from twinops.ml.baseline import BaselineConfig, RobustBaseline


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
