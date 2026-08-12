from datetime import datetime, timedelta, timezone

import pandas as pd

from twinops.ml.backtest import build_walk_forward_folds, run_backtest
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
                }
            )
    return pd.DataFrame(rows)


def test_folds_never_split_cycles_or_use_future_training_rows():
    folds = build_walk_forward_folds(range(6), holdout_count=2)

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
    folds = build_walk_forward_folds(frame.cycle_id.unique(), holdout_count=2)

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
    folds = build_walk_forward_folds(frame.cycle_id.unique(), holdout_count=2)

    report = run_backtest(frame, RobustBaseline(BaselineConfig()), folds)

    assert report.candidate_events
    assert all(
        event["classification"] == "candidate_not_ground_truth"
        for event in report.candidate_events
    )

