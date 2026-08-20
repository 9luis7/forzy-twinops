"""Canonical nested feature views with explicit semantic policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from scipy import signal as scipy_signal
from scipy import stats

from twinops.research.contracts import FeaturePolicy, SignalWindow


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
    unconfirmed_semantics: Mapping[str, str]
    feature_policy_id: str | None


def _periodogram_features(
    values: np.ndarray,
    sampling_hz: float,
    *,
    prefix: str,
    axis: str,
) -> dict[str, float]:
    """Return one-sided boxcar spectrum whose sum equals signal mean-square.

    SciPy ``periodogram(..., scaling="spectrum", detrend=False)`` applies the
    correct one-sided doubling while keeping DC and Nyquist single-counted.
    The total therefore obeys Parseval and is independent of window length.
    """

    frequencies, spectrum = scipy_signal.periodogram(
        values,
        fs=sampling_hz,
        window="boxcar",
        detrend=False,
        return_onesided=True,
        scaling="spectrum",
    )
    normalized = frequencies / (sampling_hz / 2.0)
    total = float(np.sum(spectrum))
    result = {f"{prefix}_spectral_energy_g2__{axis}": total}
    for lower, upper, label in _BANDS:
        if upper == 1.0:
            mask = (normalized >= lower) & (normalized <= upper)
        else:
            mask = (normalized >= lower) & (normalized < upper)
        fraction = float(np.sum(spectrum[mask]) / total) if total > 0 else 0.0
        result[f"{prefix}_spectral_fraction_{label}_nyquist__{axis}"] = fraction
    return result


def _axis_features(values: np.ndarray, sampling_hz: float, axis: str) -> tuple[dict[str, float], dict[str, float]]:
    rms = float(np.sqrt(np.mean(np.square(values))))
    standard_deviation = float(np.std(values))
    peak_to_peak = float(np.ptp(values))
    aggregate = {
        f"acceleration_rms_g__{axis}": rms,
        f"acceleration_std_g__{axis}": standard_deviation,
        f"acceleration_peak_to_peak_g__{axis}": peak_to_peak,
    }
    peak = float(np.max(np.abs(values)))
    if standard_deviation > 0 and values.size >= 3:
        skewness = float(stats.skew(values, bias=True))
        excess_kurtosis = float(stats.kurtosis(values, fisher=True, bias=True))
    else:
        skewness = 0.0
        excess_kurtosis = 0.0
    detailed = {
        f"acceleration_crest_factor__{axis}": peak / rms if rms > 0 else 0.0,
        f"acceleration_skewness_bias_true__{axis}": skewness,
        f"acceleration_excess_kurtosis_fisher_true_bias_true__{axis}": excess_kurtosis,
    }
    detailed.update(
        _periodogram_features(
            values,
            sampling_hz,
            prefix="acceleration",
            axis=axis,
        )
    )
    envelope = np.abs(scipy_signal.hilbert(values))
    detailed.update(
        _periodogram_features(
            envelope,
            sampling_hz,
            prefix="acceleration_envelope",
            axis=axis,
        )
    )
    return aggregate, detailed


def extract_views(
    window: SignalWindow, *, policy: FeaturePolicy | None = None
) -> FeatureViews:
    """Build a canonical vector and nested masks without pooling axes."""

    if window.acceleration_unit.strip().lower() != "g":
        raise ValueError(
            f"acceleration unit {window.acceleration_unit!r} is not validated for *_g features"
        )

    aggregate: dict[str, float] = {}
    detailed: dict[str, float] = {}
    for axis in sorted(window.acceleration):
        axis_aggregate, axis_detailed = _axis_features(
            np.asarray(window.acceleration[axis], dtype=float), window.sampling_hz, axis
        )
        aggregate.update(axis_aggregate)
        detailed.update(axis_detailed)

    if window.temperature_c is not None:
        aggregate["temperature_c"] = float(window.temperature_c)
    if window.rpm is not None:
        aggregate["rpm"] = float(window.rpm)
    if window.load is not None:
        aggregate["load"] = float(window.load)

    full = dict(aggregate)
    full.update(detailed)
    forzy: dict[str, float] = {}
    unconfirmed: dict[str, str] = {}
    if policy is None or not policy.acceleration_rms_semantics_confirmed:
        unconfirmed["acceleration_rms_g"] = "unconfirmed_semantics"
    else:
        axis = policy.selected_acceleration_axis
        name = f"acceleration_rms_g__{axis}"
        if name not in aggregate:
            raise ValueError(
                f"feature policy axis {axis!r} is not present in window {window.source_relative_path}"
            )
        forzy[name] = aggregate[name]

    if window.temperature_c is not None:
        if policy is not None and policy.temperature_semantics_confirmed:
            forzy["temperature_c"] = aggregate["temperature_c"]
        else:
            unconfirmed["temperature_c"] = "unconfirmed_semantics"
    else:
        unconfirmed["temperature_c"] = "unavailable_in_dataset"
    unconfirmed["velocity_rms_mm_s"] = "unconfirmed_integration_and_filter_semantics"

    if not set(forzy) <= set(aggregate) or not set(aggregate) <= set(full):
        raise AssertionError("feature view masks must satisfy full >= aggregate >= forzy")
    return FeatureViews(
        full=full,
        aggregate=aggregate,
        forzy=forzy,
        unconfirmed_semantics=unconfirmed,
        feature_policy_id=policy.policy_id if policy is not None else None,
    )
