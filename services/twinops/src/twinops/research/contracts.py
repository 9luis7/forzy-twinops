"""Common, provenance-preserving contract for public bearing datasets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import TypeAlias

import numpy as np
from numpy.typing import ArrayLike, NDArray


FAULT_LABELS = frozenset(
    {
        "normal",
        "inner_race",
        "outer_race",
        "rolling_element",
        "cage",
        "compound",
        "unknown",
    }
)

Acceleration: TypeAlias = NDArray[np.float64] | Mapping[str, NDArray[np.float64]]


def _signal_array(value: ArrayLike, *, name: str) -> NDArray[np.float64]:
    try:
        signal = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if signal.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if signal.size == 0:
        raise ValueError(f"{name} must not be empty")
    if not np.isfinite(signal).all():
        raise ValueError(f"{name} must contain only finite values")
    signal.setflags(write=False)
    return signal


def _finite_optional(value: float | None, *, name: str, positive: bool = False) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not np.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if positive and value < 0:
        raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class SignalWindow:
    """One acquisition window from one bearing/run.

    ``acceleration`` is either one 1-D signal or an axis-to-signal mapping. The
    adapter must preserve the source unit in ``acceleration_unit``; this class
    never performs a silent unit conversion.
    """

    dataset_id: str
    bearing_id: str
    run_id: str
    sampling_hz: float
    acceleration: ArrayLike | Mapping[str, ArrayLike]
    fault_label: str
    started_at: datetime | None = None
    temperature_c: float | None = None
    rpm: float | None = None
    load: float | None = None
    life_fraction: float | None = None
    acceleration_unit: str = "g"

    def __post_init__(self) -> None:
        for name in ("dataset_id", "bearing_id", "run_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
            object.__setattr__(self, name, value.strip())

        if isinstance(self.sampling_hz, bool) or not np.isfinite(self.sampling_hz) or self.sampling_hz <= 0:
            raise ValueError("sampling_hz must be finite and greater than zero")
        if self.started_at is not None:
            if not isinstance(self.started_at, datetime):
                raise ValueError("started_at must be a datetime or None")
            if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
                raise ValueError("started_at must include a timezone")
        if self.fault_label not in FAULT_LABELS:
            raise ValueError(f"fault_label must be one of {sorted(FAULT_LABELS)}")
        if not isinstance(self.acceleration_unit, str) or not self.acceleration_unit.strip():
            raise ValueError("acceleration_unit must be a non-empty string")

        if isinstance(self.acceleration, Mapping):
            if not self.acceleration:
                raise ValueError("acceleration axis mapping must not be empty")
            axes: dict[str, NDArray[np.float64]] = {}
            for axis, values in self.acceleration.items():
                if not isinstance(axis, str) or not axis.strip():
                    raise ValueError("acceleration axis names must be non-empty strings")
                axes[axis.strip()] = _signal_array(values, name=f"acceleration[{axis!r}]")
            if len({values.size for values in axes.values()}) != 1:
                raise ValueError("all acceleration axes must contain the same number of samples")
            object.__setattr__(self, "acceleration", MappingProxyType(axes))
        else:
            object.__setattr__(self, "acceleration", _signal_array(self.acceleration, name="acceleration"))

        _finite_optional(self.temperature_c, name="temperature_c")
        _finite_optional(self.rpm, name="rpm", positive=True)
        _finite_optional(self.load, name="load")
        _finite_optional(self.life_fraction, name="life_fraction")
        if self.life_fraction is not None and not 0 <= self.life_fraction <= 1:
            raise ValueError("life_fraction must be in the closed interval [0, 1]")
