from datetime import datetime, timedelta, timezone

import pandas as pd

from twinops.ml.baseline import BaselineConfig, RobustBaseline


def _feature_frame(values):
    start = datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)
    return pd.DataFrame(
        {
            "event_at": [start + timedelta(seconds=index) for index in range(len(values))],
            "sensor_id": ["s1"] * len(values),
            "cycle_id": [0] * len(values),
            "operating_state": ["steady"] * len(values),
            "feature_valid": [True] * len(values),
            "velocity_ewma": values,
            "velocity_slope": [0.0] * len(values),
            "velocity_change_point": [0.0] * len(values),
            "temperature_deviation": [0.0] * len(values),
        }
    )


def test_persistent_deviation_scores_above_single_spike():
    baseline = RobustBaseline(BaselineConfig()).fit(_feature_frame([0, 0, 0, 0, 0]))

    spike = baseline.score(_feature_frame([0, 0, 8, 0, 0]))
    persistent = baseline.score(_feature_frame([0, 0, 5, 5, 5]))

    assert persistent.deterioration_score.iloc[-1] > spike.deterioration_score.iloc[-1]


def test_scores_are_finite_bounded_and_monotonic_for_current_deviation():
    baseline = RobustBaseline(BaselineConfig()).fit(_feature_frame([0, 0, 0, 0, 0]))

    scores = [
        baseline.score(_feature_frame([value])).anomaly_score.iloc[-1]
        for value in (0, 0.01, 1.0)
    ]

    assert scores == sorted(scores)
    assert all(0 <= score <= 100 for score in scores)


def test_fit_rejects_transition_only_calibration():
    frame = _feature_frame([0.1, 0.2])
    frame["operating_state"] = "startup"

    try:
        RobustBaseline(BaselineConfig()).fit(frame)
    except ValueError as error:
        assert "steady" in str(error)
    else:
        raise AssertionError("transition rows must not calibrate the baseline")

