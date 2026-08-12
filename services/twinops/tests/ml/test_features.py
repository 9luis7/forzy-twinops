import math

import pandas as pd

from twinops.ml.curation import curate_samples
from twinops.ml.features import FeatureConfig, compute_trailing_features


CONFIG = FeatureConfig(short_window_seconds=4, long_window_seconds=10, min_points=2)


def _curated(sample_factory, values, *, seconds=None, temperatures=None):
    seconds = seconds or list(range(len(values)))
    temperatures = temperatures or [30.0] * len(values)
    return curate_samples(
        [
            sample_factory(second=second, velocity=value, temperature=temperature)
            for second, value, temperature in zip(seconds, values, temperatures, strict=True)
        ],
        gap_seconds=10,
    )


def test_future_mutation_does_not_change_prior_features(sample_factory):
    curated = _curated(sample_factory, [0.1, 0.11, 0.12, 0.13, 0.14])
    first = compute_trailing_features(curated, CONFIG)
    mutated = curated.copy()
    mutated.loc[mutated.index[-1], "velocity_rms"] *= 100

    second = compute_trailing_features(mutated, CONFIG)

    pd.testing.assert_frame_equal(first.iloc[:-1], second.iloc[:-1])


def test_gap_resets_feature_history(sample_factory):
    curated = _curated(sample_factory, [0.1, 0.2, 0.3], seconds=[0, 2, 30])

    features = compute_trailing_features(curated, CONFIG)

    assert features.iloc[1].feature_valid
    assert not features.iloc[2].feature_valid
    assert math.isnan(features.iloc[2].velocity_median)


def test_zero_mad_never_produces_infinite_robust_z(sample_factory):
    curated = _curated(sample_factory, [0.1, 0.1, 0.1, 0.2])

    features = compute_trailing_features(curated, CONFIG)

    assert features.loc[:2, "velocity_robust_z"].fillna(0).eq(0).all()
    assert math.isfinite(features.iloc[-1].velocity_robust_z)


def test_min_points_gates_features(sample_factory):
    curated = _curated(sample_factory, [0.1, 0.11, 0.12])
    config = FeatureConfig(short_window_seconds=4, long_window_seconds=10, min_points=3)

    features = compute_trailing_features(curated, config)

    assert features["feature_valid"].tolist() == [False, False, True]


def test_temperature_baseline_is_kept_separate_by_operating_phase(sample_factory):
    curated = _curated(
        sample_factory,
        [0.1, 0.1, 0.01, 0.01],
        temperatures=[30.0, 31.0, 60.0, 58.0],
    )

    features = compute_trailing_features(curated, CONFIG)

    assert curated["operating_state"].tolist() == ["startup", "steady", "shutdown", "stopped"]
    assert features["temperature_phase_points"].tolist() == [1, 1, 1, 1]
    assert features.iloc[2].temperature_median == 60.0

