"""Semantic compatibility matrix between laboratory and Forzy API features."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from twinops.research.contracts import SignalWindow


FULL_FEATURES = (
    "rms_g",
    "std_g",
    "peak_to_peak_g",
    "crest_factor",
    "skewness",
    "kurtosis",
    "band_energy",
    "envelope_band_energy",
)
AGGREGATE_BASE = ("acceleration_rms_g",)


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    full_features: tuple[str, ...]
    aggregate_features: tuple[str, ...]
    forzy_features: tuple[str, ...]
    missing_semantics: Mapping[str, str]


def compatibility(window: SignalWindow) -> CompatibilityReport:
    """Describe reproducible views without manufacturing unavailable context."""

    aggregate = list(AGGREGATE_BASE)
    forzy = list(AGGREGATE_BASE)
    missing: dict[str, str] = {
        "velocity_rms_mm_s": (
            "Acceleration waveform does not establish the validated filter and "
            "integration semantics used by the Forzy sensor."
        )
    }

    if window.temperature_c is not None:
        aggregate.append("temperature_c")
        forzy.append("temperature_c")
    else:
        missing["temperature_c"] = "Dataset window has no measured temperature."

    if window.rpm is not None:
        aggregate.append("rpm")
    else:
        missing["rpm"] = "Dataset window has no measured rotation speed."

    if window.load is not None:
        aggregate.append("load")
    else:
        missing["load"] = "Dataset window has no measured load."

    return CompatibilityReport(
        full_features=FULL_FEATURES,
        aggregate_features=tuple(aggregate),
        forzy_features=tuple(forzy),
        missing_semantics=MappingProxyType(missing),
    )
