from __future__ import annotations

import math

import numpy as np
import pytest

from twinops.research.contracts import FeaturePolicy
from twinops.research.features import extract_views

from .factories import make_window


@pytest.fixture
def confirmed_policy() -> FeaturePolicy:
    return FeaturePolicy(
        policy_id="synthetic-policy-v1",
        selected_acceleration_axis="radial",
        acceleration_rms_semantics_confirmed=True,
        temperature_semantics_confirmed=True,
        evidence="Synthetic test-only semantics.",
    )


def _tone(length: int, normalized_frequency: float = 0.125) -> np.ndarray:
    samples = np.arange(length, dtype=float)
    return np.sin(np.pi * normalized_frequency * samples)


def test_views_are_canonical_and_really_nested(confirmed_policy) -> None:
    window = make_window(
        axes={"radial": _tone(512), "axial": 0.5 * _tone(512)},
        temperature_c=41.25,
    )

    views = extract_views(window, policy=confirmed_policy)

    assert set(views.full) >= set(views.aggregate) >= set(views.forzy)
    assert "acceleration_rms_g__radial" in views.forzy
    assert "temperature_c" in views.full
    assert "temperature_c" in views.aggregate
    assert "temperature_c" in views.forzy
    assert "acceleration_excess_kurtosis_fisher_true_bias_true__radial" in views.full
    assert "acceleration_rms_g" not in views.unconfirmed_semantics
    assert "temperature_c" not in views.unconfirmed_semantics
    assert views.unconfirmed_semantics["velocity_rms_mm_s"].startswith("unconfirmed")


def test_multiaxis_features_are_not_pooled_or_relabelled(confirmed_policy) -> None:
    window = make_window(
        axes={
            "radial": np.array([1.0, -1.0, 1.0, -1.0]),
            "axial": np.array([0.5, -0.5, 0.5, -0.5]),
        }
    )

    views = extract_views(window, policy=confirmed_policy)

    assert views.full["acceleration_rms_g__radial"] == pytest.approx(1.0)
    assert views.full["acceleration_rms_g__axial"] == pytest.approx(0.5)
    assert views.full["acceleration_spectral_energy_g2__radial"] == pytest.approx(1.0)
    assert views.full["acceleration_spectral_energy_g2__axial"] == pytest.approx(0.25)
    assert not any("pooled" in name for name in views.full)
    assert set(views.forzy) == {"acceleration_rms_g__radial"}


def test_forzy_view_omits_unconfirmed_acceleration_and_temperature() -> None:
    views = extract_views(make_window(temperature_c=40.0))

    assert views.forzy == {}
    assert views.unconfirmed_semantics["acceleration_rms_g"] == "unconfirmed_semantics"
    assert views.unconfirmed_semantics["temperature_c"] == "unconfirmed_semantics"


@pytest.mark.parametrize("length", [256, 1_024])
def test_periodogram_energy_is_parseval_correct_and_length_invariant(length) -> None:
    values = _tone(length, normalized_frequency=0.25)
    views = extract_views(make_window(axes={"radial": values}))

    assert views.full["acceleration_spectral_energy_g2__radial"] == pytest.approx(0.5, rel=1e-10)
    assert views.full["acceleration_rms_g__radial"] == pytest.approx(math.sqrt(0.5), rel=1e-10)
    spectral_fractions = [
        value
        for name, value in views.full.items()
        if name.startswith("acceleration_spectral_fraction_") and name.endswith("__radial")
    ]
    assert sum(spectral_fractions) == pytest.approx(1.0, rel=1e-12)


def test_periodogram_handles_dc_and_nyquist_without_missing_or_double_counting() -> None:
    dc = extract_views(make_window(axes={"radial": np.ones(512)}))
    nyquist = extract_views(
        make_window(axes={"radial": np.where(np.arange(512) % 2 == 0, 1.0, -1.0)})
    )

    assert dc.full["acceleration_spectral_energy_g2__radial"] == pytest.approx(1.0)
    assert dc.full["acceleration_spectral_fraction_0_0p1_nyquist__radial"] == pytest.approx(1.0)
    assert nyquist.full["acceleration_spectral_energy_g2__radial"] == pytest.approx(1.0)
    assert nyquist.full["acceleration_spectral_fraction_0p5_1_nyquist__radial"] == pytest.approx(1.0)


def test_unknown_unit_is_rejected_without_silent_conversion() -> None:
    window = make_window()
    object.__setattr__(window, "acceleration_unit", "m/s^2")

    with pytest.raises(ValueError, match="unit"):
        extract_views(window)
