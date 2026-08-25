import math
from importlib.util import find_spec

import pandas as pd
import pytest

from twinops.ml.curation import curate_samples
from twinops.ml.features import FeatureConfig, compute_trailing_features


CONFIG = FeatureConfig(short_window_seconds=4, long_window_seconds=10, min_points=2)
EXPORTER_AVAILABLE = find_spec("twinops.ml.historical_assessments_v1") is not None


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


def test_duplicate_payload_does_not_enter_trailing_feature_history(sample_factory):
    curated = curate_samples(
        [
            sample_factory(second=0, velocity=0.1, payload_hash="duplicate"),
            sample_factory(second=1, velocity=10.0, payload_hash="duplicate"),
            sample_factory(second=2, velocity=0.1),
        ],
        gap_seconds=10,
    )

    features = compute_trailing_features(curated, CONFIG)

    assert not features.iloc[1].feature_valid
    assert features.iloc[2].feature_valid
    assert features.iloc[2].velocity_median == 0.1
    assert features.iloc[2].velocity_ewma == 0.1


@pytest.mark.skipif(not EXPORTER_AVAILABLE, reason="covered by the VS6A RED tracer")
def test_valid_feature_rows_record_exact_actual_trailing_window_bounds(sample_factory):
    curated = _curated(
        sample_factory,
        [0.10, 0.11, 0.12, 0.13],
        seconds=[0, 4, 10, 14],
    )

    features = compute_trailing_features(curated, CONFIG)

    assert pd.isna(features.iloc[0].feature_window_start)
    assert pd.isna(features.iloc[0].feature_window_end)
    assert features.iloc[2].feature_window_start == features.iloc[0].event_at
    assert features.iloc[2].feature_window_end == features.iloc[2].event_at
    assert features.iloc[3].feature_window_start == features.iloc[1].event_at
    assert features.iloc[3].feature_window_end == features.iloc[3].event_at
    assert (
        features.loc[features.feature_valid, "feature_window_start"]
        <= features.loc[features.feature_valid, "feature_window_end"]
    ).all()


@pytest.mark.skipif(not EXPORTER_AVAILABLE, reason="covered by the VS6A RED tracer")
def test_duplicate_rows_have_no_feature_window_provenance(sample_factory):
    curated = curate_samples(
        [
            sample_factory(second=0, velocity=0.1, payload_hash="duplicate"),
            sample_factory(second=1, velocity=0.1, payload_hash="duplicate"),
            sample_factory(second=2, velocity=0.2),
        ],
        gap_seconds=10,
    )

    features = compute_trailing_features(curated, CONFIG)

    duplicate = features.iloc[1]
    assert not duplicate.is_new_information
    assert not duplicate.feature_valid
    assert pd.isna(duplicate.feature_window_start)
    assert pd.isna(duplicate.feature_window_end)
