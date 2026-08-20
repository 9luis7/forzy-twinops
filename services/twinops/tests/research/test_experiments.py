from __future__ import annotations

import numpy as np
import pytest

from twinops.research.contracts import FeaturePolicy, LabelMappingPolicy
from twinops.research import experiments
from twinops.research.experiments import run_ablation

from .factories import make_window


@pytest.fixture
def feature_policy() -> FeaturePolicy:
    return FeaturePolicy(
        policy_id="synthetic-policy-v1",
        selected_acceleration_axis="radial",
        acceleration_rms_semantics_confirmed=True,
        temperature_semantics_confirmed=False,
        evidence="Synthetic-only semantic bridge.",
    )


@pytest.fixture
def label_policy() -> LabelMappingPolicy:
    return LabelMappingPolicy(
        version="canonical-labels-v1",
        mapping={"normal": "normal", "outer_race": "outer_race", "unknown": None},
    )


def _bench(
    dataset_id: str,
    prefix: str,
    *,
    bearings_per_class: int = 4,
    with_life: bool = True,
) -> list:
    windows = []
    sampling_hz = 1_024
    samples = np.arange(256, dtype=float)
    for class_index, (label, amplitude, normalized_frequency) in enumerate(
        (("normal", 0.2, 0.125), ("outer_race", 1.5, 0.375))
    ):
        for bearing_index in range(bearings_per_class):
            bearing_id = f"{prefix}-{class_index}-{bearing_index}"
            for sequence_index, run_id in enumerate(("1", "10", "2")):
                signal = amplitude * np.sin(np.pi * normalized_frequency * samples)
                signal += (sequence_index + bearing_index) * 1e-4
                windows.append(
                    make_window(
                        dataset_id=dataset_id,
                        bearing_id=bearing_id,
                        run_id=run_id,
                        sequence_index=sequence_index,
                        axes={"radial": signal},
                        window_state_label=label,
                        terminal_failure_mode="outer_race" if label == "outer_race" else None,
                        life_fraction=sequence_index / 2 if with_life else None,
                    )
                )
    return windows


def test_run_ablation_reports_mapping_coverage_baselines_and_cluster_cis(
    feature_policy, label_policy
) -> None:
    report = run_ablation(
        _bench("xjtu-sy", "x"),
        _bench("nasa-ims", "i"),
        feature_policy=feature_policy,
        label_policy=label_policy,
        seed=42,
        bootstrap_samples=50,
    )

    assert report.train_dataset_id == "xjtu-sy"
    assert report.test_dataset_id == "nasa-ims"
    assert report.label_mapping_version == "canonical-labels-v1"
    assert report.feature_policy_id == "synthetic-policy-v1"
    assert report.train_coverage.window_coverage == pytest.approx(1.0)
    assert report.test_coverage.bearing_coverage == pytest.approx(1.0)
    assert set(report.views) == {"full", "aggregate", "forzy"}
    for result in report.views.values():
        diagnostic = result.diagnostic
        assert diagnostic.confidence_intervals["balanced_accuracy"].status == "completed"
        assert diagnostic.majority_baseline.macro_f1 >= 0
        assert diagnostic.majority_baseline.balanced_accuracy >= 0
        assert result.prognostic.status == "completed"
        assert result.prognostic.confidence_intervals["life_fraction_mae"].status == "completed"
        assert result.prognostic.confidence_intervals["detection_lead_time_fraction"].status in {
            "completed",
            "not_available",
        }
    assert report.views["forzy"].feature_names == ("acceleration_rms_g__radial",)


def test_explicit_exclusion_is_counted_and_counts_are_post_filter(
    feature_policy, label_policy
) -> None:
    train = _bench("xjtu-sy", "x")
    test = _bench("nasa-ims", "i")
    train.append(
        make_window(
            dataset_id="xjtu-sy",
            bearing_id="excluded-train",
            run_id="excluded",
            sequence_index=0,
            window_state_label="unknown",
        )
    )
    test.append(
        make_window(
            dataset_id="nasa-ims",
            bearing_id="excluded-test",
            run_id="excluded",
            sequence_index=0,
            window_state_label="unknown",
        )
    )

    report = run_ablation(
        train,
        test,
        feature_policy=feature_policy,
        label_policy=label_policy,
        bootstrap_samples=30,
    )

    assert report.train_coverage.excluded_windows == 1
    assert report.test_coverage.excluded_windows == 1
    assert report.train_windows == len(train) - 1
    assert report.test_windows == len(test) - 1
    assert report.train_coverage.excluded_by_label == {"unknown": 1}
    assert report.train_coverage.excluded_labels == ("unknown",)
    assert report.train_coverage.bearings_with_excluded_windows == ("excluded-train",)
    assert report.train_coverage.fully_excluded_bearing_ids == ("excluded-train",)


def test_unexpected_label_fails_instead_of_silent_filter(feature_policy, label_policy) -> None:
    train = _bench("xjtu-sy", "x")
    train[0] = make_window(
        dataset_id="xjtu-sy",
        bearing_id="unexpected",
        run_id="0",
        sequence_index=0,
        window_state_label="inner_race",
    )

    with pytest.raises(ValueError, match="unexpected label"):
        run_ablation(
            train,
            _bench("nasa-ims", "i"),
            feature_policy=feature_policy,
            label_policy=label_policy,
        )


def test_prognosis_absence_and_partial_targets_are_structured(
    feature_policy, label_policy
) -> None:
    without_life = run_ablation(
        _bench("xjtu-sy", "x", with_life=False),
        _bench("nasa-ims", "i", with_life=False),
        feature_policy=feature_policy,
        label_policy=label_policy,
        bootstrap_samples=30,
    )
    assert all(result.prognostic.status == "not_available" for result in without_life.views.values())
    assert all(result.prognostic.reason for result in without_life.views.values())

    partial = _bench("xjtu-sy", "x")
    partial[0] = make_window(
        dataset_id="xjtu-sy",
        bearing_id=partial[0].bearing_id,
        run_id=partial[0].run_id,
        sequence_index=partial[0].sequence_index,
        axes=partial[0].acceleration,
        window_state_label=partial[0].window_state_label,
        life_fraction=None,
    )
    with pytest.raises(ValueError, match="partially available"):
        run_ablation(
            partial,
            _bench("nasa-ims", "i"),
            feature_policy=feature_policy,
            label_policy=label_policy,
        )


def test_run_ablation_rejects_bearing_leakage_and_unmappable_classes(
    feature_policy, label_policy
) -> None:
    windows = _bench("xjtu-sy", "same")
    with pytest.raises(ValueError, match="bearing overlap"):
        run_ablation(
            windows[:15],
            windows[12:],
            feature_policy=feature_policy,
            label_policy=label_policy,
        )

    only_inner = [
        make_window(
            dataset_id="nasa-ims",
            bearing_id=f"i-{index}",
            run_id="0",
            sequence_index=0,
            window_state_label="inner_race",
        )
        for index in range(3)
    ]
    mapping = LabelMappingPolicy(
        version="inner-v1",
        mapping={"normal": "normal", "outer_race": "outer_race", "inner_race": "inner_race"},
    )
    with pytest.raises(ValueError, match="mappable label"):
        run_ablation(
            _bench("xjtu-sy", "x"),
            only_inner,
            feature_policy=feature_policy,
            label_policy=mapping,
        )


def test_prognosis_lead_time_is_unavailable_when_any_test_bearing_is_undetected(
    monkeypatch,
) -> None:
    """Regression: lead time must not average only bearings that crossed the threshold."""

    class PartialDetectionRegressor:
        def __init__(self, *, random_state):
            self.random_state = random_state

        def fit(self, features, targets):
            return self

        def predict(self, features):
            return np.asarray([0.85, 0.9, 0.2, 0.3], dtype=float)

    monkeypatch.setattr(experiments, "HistGradientBoostingRegressor", PartialDetectionRegressor)
    train_windows = [
        make_window(
            dataset_id="xjtu-sy",
            bearing_id="train-a",
            run_id=f"train-{index}",
            sequence_index=index,
            life_fraction=float(index),
        )
        for index in range(2)
    ]
    test_windows = [
        make_window(
            dataset_id="nasa-ims",
            bearing_id=bearing_id,
            run_id=f"{bearing_id}-{index}",
            sequence_index=index,
            life_fraction=float(index),
        )
        for bearing_id in ("detected", "undetected")
        for index in range(2)
    ]

    metrics = experiments._prognose(
        np.asarray([[0.0], [1.0]]),
        train_windows,
        np.asarray([[0.0], [1.0], [2.0], [3.0]]),
        test_windows,
        seed=42,
        bootstrap_samples=20,
    )

    assert metrics.status == "completed"
    assert metrics.life_fraction_mae is not None
    assert metrics.detection_lead_time_fraction is None
    assert metrics.detection_lead_time_status == "not_available"
    assert metrics.detection_lead_time_reason and "1 of 2" in metrics.detection_lead_time_reason
    assert metrics.lead_time_detected_bearings == 1
    assert metrics.lead_time_total_bearings == 2
    assert metrics.lead_time_detection_coverage == pytest.approx(0.5)
    assert metrics.undetected_bearing_ids == ("undetected",)
    interval = metrics.confidence_intervals["detection_lead_time_fraction"]
    assert interval.status == "not_available"
    assert interval.reason == metrics.detection_lead_time_reason
