from __future__ import annotations

import math

import numpy as np
import pytest

from twinops.research.contracts import SignalWindow
from twinops.research.features import extract_views


@pytest.fixture
def sine_window() -> SignalWindow:
    sampling_hz = 2_048
    time = np.arange(sampling_hz, dtype=float) / sampling_hz
    signal = np.sin(2 * np.pi * 128 * time)
    return SignalWindow(
        dataset_id="synthetic-fixture",
        bearing_id="bearing-a",
        run_id="run-1",
        sampling_hz=sampling_hz,
        acceleration=signal,
        temperature_c=41.25,
        fault_label="normal",
    )


def test_views_are_nested_without_semantic_invention(sine_window) -> None:
    views = extract_views(sine_window)

    assert {"rms_g", "kurtosis", "crest_factor", "band_energy"} <= views.full.keys()
    assert {"acceleration_rms_g"} <= views.aggregate.keys()
    assert set(views.forzy) <= {
        "acceleration_rms_g",
        "velocity_rms_mm_s",
        "temperature_c",
    }
    assert set(views.forzy) <= set(views.aggregate)
    assert "velocity_rms_mm_s" not in views.forzy
    assert views.forzy["temperature_c"] == pytest.approx(41.25)


def test_sine_features_have_explicit_numeric_tolerances(sine_window) -> None:
    views = extract_views(sine_window)

    assert views.full["rms_g"] == pytest.approx(math.sqrt(0.5), rel=1e-6)
    assert views.full["crest_factor"] == pytest.approx(math.sqrt(2), rel=1e-5)
    assert views.full["skewness"] == pytest.approx(0.0, abs=1e-10)
    assert views.full["kurtosis"] == pytest.approx(-1.5, rel=1e-5)
    assert views.full["spectral_band_0p1_0p25_nyquist"] > 0.99
    assert sum(
        value for name, value in views.full.items() if name.startswith("spectral_band_")
    ) == pytest.approx(1.0, rel=1e-8)
    assert sum(
        value for name, value in views.full.items() if name.startswith("envelope_band_")
    ) == pytest.approx(1.0, rel=1e-8)


def test_multiaxis_features_are_order_invariant() -> None:
    horizontal = np.array([1.0, -1.0, 1.0, -1.0])
    vertical = np.array([0.5, -0.5, 0.5, -0.5])
    common = dict(
        dataset_id="fixture",
        bearing_id="bearing-a",
        run_id="1",
        sampling_hz=1_000,
        fault_label="unknown",
    )

    first = extract_views(
        SignalWindow(acceleration={"horizontal": horizontal, "vertical": vertical}, **common)
    )
    second = extract_views(
        SignalWindow(acceleration={"vertical": vertical, "horizontal": horizontal}, **common)
    )

    assert first.full == pytest.approx(second.full)
    assert first.aggregate == pytest.approx(second.aggregate)


def test_temperature_is_not_invented_and_unknown_units_are_rejected() -> None:
    window = SignalWindow(
        dataset_id="fixture",
        bearing_id="bearing-a",
        run_id="1",
        sampling_hz=1_000,
        acceleration=np.array([0.1, -0.1, 0.2, -0.2]),
        fault_label="normal",
    )
    assert "temperature_c" not in extract_views(window).forzy

    millisecond_window = SignalWindow(
        dataset_id="fixture",
        bearing_id="bearing-a",
        run_id="2",
        sampling_hz=1_000,
        acceleration=np.array([1.0, -1.0]),
        acceleration_unit="m/s^2",
        fault_label="normal",
    )
    with pytest.raises(ValueError, match="unit"):
        extract_views(millisecond_window)
