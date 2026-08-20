from __future__ import annotations

import numpy as np
import pytest

from twinops.research.contracts import SignalWindow
from twinops.research.experiments import run_ablation


def _bench(dataset_id: str, prefix: str, *, bearings_per_class: int = 4) -> list[SignalWindow]:
    windows: list[SignalWindow] = []
    sampling_hz = 1_024
    time = np.arange(512, dtype=float) / sampling_hz
    for class_index, (label, amplitude, frequency) in enumerate(
        (("normal", 0.2, 64), ("outer_race", 1.5, 192))
    ):
        for bearing_index in range(bearings_per_class):
            bearing_id = f"{prefix}-{class_index}-{bearing_index}"
            for run_index in range(2):
                signal = amplitude * np.sin(2 * np.pi * frequency * time)
                signal = signal + (run_index + bearing_index) * 1e-4
                windows.append(
                    SignalWindow(
                        dataset_id=dataset_id,
                        bearing_id=bearing_id,
                        run_id=str(run_index),
                        sampling_hz=sampling_hz,
                        acceleration=signal,
                        fault_label=label,
                        life_fraction=run_index / 2,
                    )
                )
    return windows


def test_run_ablation_compares_all_views_cross_bench() -> None:
    report = run_ablation(_bench("xjtu-sy", "x"), _bench("nasa-ims", "i"), seed=42)

    assert report.train_dataset_id == "xjtu-sy"
    assert report.test_dataset_id == "nasa-ims"
    assert report.bootstrap_unit == "bearing_id"
    assert set(report.views) == {"full", "aggregate", "forzy"}
    for result in report.views.values():
        assert 0 <= result.diagnostic.macro_f1 <= 1
        assert 0 <= result.diagnostic.balanced_accuracy <= 1
        assert result.diagnostic.confusion_matrix
        assert result.diagnostic.confidence_intervals["macro_f1"].samples > 0
        assert result.prognostic is not None
        assert result.prognostic.life_fraction_mae >= 0
    assert report.views["forzy"].feature_names == ("acceleration_rms_g",)


def test_run_ablation_rejects_bearing_leakage_within_same_bench() -> None:
    windows = _bench("xjtu-sy", "same")

    with pytest.raises(ValueError, match="bearing overlap"):
        run_ablation(windows[:8], windows[4:])


def test_run_ablation_requires_mappable_non_unknown_labels() -> None:
    train = _bench("xjtu-sy", "x")
    test = [
        SignalWindow(
            dataset_id="nasa-ims",
            bearing_id=f"i-{index}",
            run_id="0",
            sampling_hz=1_024,
            acceleration=np.arange(32, dtype=float),
            fault_label="inner_race",
        )
        for index in range(3)
    ]

    with pytest.raises(ValueError, match="mappable label"):
        run_ablation(train, test)


def test_prognosis_is_absent_without_true_life_fraction() -> None:
    train = [
        SignalWindow(
            dataset_id=window.dataset_id,
            bearing_id=window.bearing_id,
            run_id=window.run_id,
            sampling_hz=window.sampling_hz,
            acceleration=window.acceleration,
            fault_label=window.fault_label,
        )
        for window in _bench("xjtu-sy", "x")
    ]
    test = [
        SignalWindow(
            dataset_id=window.dataset_id,
            bearing_id=window.bearing_id,
            run_id=window.run_id,
            sampling_hz=window.sampling_hz,
            acceleration=window.acceleration,
            fault_label=window.fault_label,
        )
        for window in _bench("nasa-ims", "i")
    ]

    report = run_ablation(train, test)

    assert all(result.prognostic is None for result in report.views.values())
