"""Feature ablation views for the public fault-dataset laboratory."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from scipy import signal as scipy_signal
from scipy import stats

from twinops.research.contracts import SignalWindow


_BANDS = (
    (0.0, 0.1, "0_0p1"),
    (0.1, 0.25, "0p1_0p25"),
    (0.25, 0.5, "0p25_0p5"),
    (0.5, 1.0, "0p5_1"),
)


@dataclass(frozen=True, slots=True)
class FeatureViews:
    full: Mapping[str, float]
    aggregate: Mapping[str, float]
    forzy: Mapping[str, float]


def _axes(window: SignalWindow) -> tuple[np.ndarray, ...]:
    acceleration = window.acceleration
    if isinstance(acceleration, Mapping):
        return tuple(np.asarray(acceleration[name], dtype=float) for name in sorted(acceleration))
    return (np.asarray(acceleration, dtype=float),)


def _band_fractions(values: np.ndarray, sampling_hz: float) -> tuple[float, dict[str, float]]:
    centered = values - np.mean(values)
    spectrum = np.abs(np.fft.rfft(centered)) ** 2
    frequencies = np.fft.rfftfreq(values.size, d=1.0 / sampling_hz)
    normalized_frequency = frequencies / (sampling_hz / 2.0)
    total = float(np.sum(spectrum))
    fractions: dict[str, float] = {}
    for lower, upper, label in _BANDS:
        if upper == 1.0:
            mask = (normalized_frequency >= lower) & (normalized_frequency <= upper)
        else:
            mask = (normalized_frequency >= lower) & (normalized_frequency < upper)
        fractions[f"spectral_band_{label}_nyquist"] = (
            float(np.sum(spectrum[mask]) / total) if total > 0 else 0.0
        )
    return total / values.size, fractions


def _envelope_features(values: np.ndarray, sampling_hz: float) -> tuple[float, dict[str, float]]:
    envelope = np.abs(scipy_signal.hilbert(values))
    energy, spectral_names = _band_fractions(envelope, sampling_hz)
    fractions = {
        name.replace("spectral_band_", "envelope_band_"): value
        for name, value in spectral_names.items()
    }
    return energy, fractions


def extract_views(window: SignalWindow) -> FeatureViews:
    """Extract full, aggregate, and semantically Forzy-compatible views.

    The current adapter contract permits acceleration in arbitrary preserved
    units. This extractor intentionally refuses non-``g`` inputs rather than
    silently converting and mislabelling ``*_g`` features.
    """

    if window.acceleration_unit.strip().lower() != "g":
        raise ValueError(
            f"acceleration unit {window.acceleration_unit!r} is not validated for *_g features"
        )

    axes = _axes(window)
    pooled = np.concatenate(axes)
    rms = float(np.sqrt(np.mean(np.square(pooled))))
    standard_deviation = float(np.std(pooled))
    peak_to_peak = float(np.ptp(pooled))
    peak = float(np.max(np.abs(pooled)))
    crest = peak / rms if rms > 0 else 0.0
    if standard_deviation > 0 and pooled.size >= 3:
        skewness = float(stats.skew(pooled, bias=True))
        kurtosis = float(stats.kurtosis(pooled, fisher=True, bias=True))
    else:
        skewness = 0.0
        kurtosis = 0.0

    axis_bands: list[dict[str, float]] = []
    axis_envelope_bands: list[dict[str, float]] = []
    raw_band_energies: list[float] = []
    envelope_energies: list[float] = []
    for axis in axes:
        energy, fractions = _band_fractions(axis, window.sampling_hz)
        raw_band_energies.append(energy)
        axis_bands.append(fractions)
        envelope_energy, envelope_fractions = _envelope_features(axis, window.sampling_hz)
        envelope_energies.append(envelope_energy)
        axis_envelope_bands.append(envelope_fractions)

    full: dict[str, float] = {
        "rms_g": rms,
        "std_g": standard_deviation,
        "peak_to_peak_g": peak_to_peak,
        "crest_factor": crest,
        "skewness": skewness,
        "kurtosis": kurtosis,
        "band_energy": float(np.mean(raw_band_energies)),
        "envelope_band_energy": float(np.mean(envelope_energies)),
    }
    for name in axis_bands[0]:
        full[name] = float(np.mean([bands[name] for bands in axis_bands]))
    for name in axis_envelope_bands[0]:
        full[name] = float(np.mean([bands[name] for bands in axis_envelope_bands]))

    aggregate: dict[str, float] = {
        "acceleration_rms_g": rms,
        "acceleration_std_g": standard_deviation,
        "acceleration_peak_to_peak_g": peak_to_peak,
    }
    forzy: dict[str, float] = {"acceleration_rms_g": rms}
    if window.temperature_c is not None:
        aggregate["temperature_c"] = float(window.temperature_c)
        forzy["temperature_c"] = float(window.temperature_c)
    if window.rpm is not None:
        aggregate["rpm"] = float(window.rpm)
    if window.load is not None:
        aggregate["load"] = float(window.load)

    return FeatureViews(full=full, aggregate=aggregate, forzy=forzy)
