from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from twinops.ml.challenger import (
    ChallengerConfig,
    IsolationForestChallenger,
    compare_challenger,
)


def _features():
    start = datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)
    values = [0.1, 0.11, 0.09, 0.1, 99.0]
    return pd.DataFrame(
        {
            "event_at": [start + timedelta(seconds=i) for i in range(5)],
            "sensor_id": ["s1"] * 5,
            "cycle_id": [0, 0, 1, 1, 2],
            "operating_state": ["steady", "steady", "steady", "steady", "startup"],
            "feature_valid": [True] * 5,
            "velocity_ewma": values,
            "velocity_slope": [0.0] * 5,
            "velocity_change_point": [0.0] * 5,
            "temperature_deviation": [0.0] * 5,
        }
    )


def test_challenger_trains_only_on_valid_steady_baseline_rows():
    challenger = IsolationForestChallenger(ChallengerConfig(n_estimators=20))

    challenger.fit(_features())

    assert challenger.training_rows_ == 4
    assert challenger.training_cycle_ids_ == (0, 1)


def test_challenger_is_deterministic_for_frozen_random_state():
    frame = _features()
    first = IsolationForestChallenger(ChallengerConfig(n_estimators=20)).fit(frame)
    second = IsolationForestChallenger(ChallengerConfig(n_estimators=20)).fit(frame)

    np.testing.assert_allclose(first.score(frame), second.score(frame))


def test_comparison_can_recommend_but_never_auto_promotes_challenger():
    decision = compare_challenger(
        baseline_stability=8.0,
        baseline_normal_alert_load=4.0,
        challenger_stability=5.0,
        challenger_normal_alert_load=3.0,
    )

    assert decision.recommended
    assert not decision.promoted
    assert "human" in decision.reason.lower()

