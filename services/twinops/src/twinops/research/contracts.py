"""Strict contracts for provenance-aware public bearing research."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

import numpy as np
from numpy.typing import ArrayLike, NDArray


STATE_LABELS = frozenset(
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
TIMESTAMP_QUALITIES = frozenset(
    {"unavailable", "source_timezone_confirmed", "source_timezone_assumed"}
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _nonempty(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


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


def _finite_optional(value: float | None, *, name: str, non_negative: bool = False) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if non_negative and value < 0:
        raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class FeaturePolicy:
    """Audited semantic bridge from public features to the Forzy API view."""

    policy_id: str
    selected_acceleration_axis: str | None
    acceleration_rms_semantics_confirmed: bool
    temperature_semantics_confirmed: bool
    evidence: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _nonempty(self.policy_id, name="policy_id"))
        object.__setattr__(self, "evidence", _nonempty(self.evidence, name="evidence"))
        if not isinstance(self.acceleration_rms_semantics_confirmed, bool):
            raise ValueError("acceleration_rms_semantics_confirmed must be boolean")
        if not isinstance(self.temperature_semantics_confirmed, bool):
            raise ValueError("temperature_semantics_confirmed must be boolean")
        if self.acceleration_rms_semantics_confirmed:
            object.__setattr__(
                self,
                "selected_acceleration_axis",
                _nonempty(self.selected_acceleration_axis, name="selected_acceleration_axis"),
            )
        elif self.selected_acceleration_axis is not None:
            object.__setattr__(
                self,
                "selected_acceleration_axis",
                _nonempty(self.selected_acceleration_axis, name="selected_acceleration_axis"),
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class LabelMappingPolicy:
    """Versioned mapping from dataset window-state labels to canonical labels."""

    version: str
    mapping: Mapping[str, str | None]

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _nonempty(self.version, name="label mapping version"))
        if not isinstance(self.mapping, Mapping) or not self.mapping:
            raise ValueError("label mapping must be a non-empty mapping")
        normalized: dict[str, str | None] = {}
        for source, target in self.mapping.items():
            source_name = _nonempty(source, name="label mapping source")
            if source_name in normalized:
                raise ValueError(f"duplicate normalized label mapping source: {source_name}")
            if target is not None:
                target = _nonempty(target, name="label mapping target")
                if target not in STATE_LABELS - {"unknown"}:
                    raise ValueError(f"label mapping target is not canonical: {target}")
            normalized[source_name] = target
        object.__setattr__(self, "mapping", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True, kw_only=True)
class SignalWindow:
    """One explicitly mapped acquisition window from one bearing and run."""

    dataset_id: str
    bearing_id: str
    run_id: str
    sampling_hz: float
    acceleration: Mapping[str, ArrayLike]
    acceleration_unit: str
    window_state_label: str
    sequence_index: int | None
    timestamp_quality: str
    source_relative_path: str
    metadata_sha256: str
    started_at: datetime | None = None
    terminal_failure_mode: str | None = None
    temperature_c: float | None = None
    rpm: float | None = None
    load: float | None = None
    life_fraction: float | None = None

    def __post_init__(self) -> None:
        for name in ("dataset_id", "bearing_id", "run_id", "acceleration_unit"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name=name))
        relative_path = _nonempty(self.source_relative_path, name="source_relative_path")
        if "\\" in relative_path or relative_path.startswith("/") or ":" in relative_path:
            raise ValueError("source_relative_path must be a normalized relative POSIX path")
        parts = relative_path.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("source_relative_path must be a normalized relative POSIX path")
        object.__setattr__(self, "source_relative_path", relative_path)
        if not isinstance(self.metadata_sha256, str) or not _SHA256.fullmatch(
            self.metadata_sha256.lower()
        ):
            raise ValueError("metadata_sha256 must be exactly 64 hexadecimal characters")
        object.__setattr__(self, "metadata_sha256", self.metadata_sha256.lower())

        if (
            isinstance(self.sampling_hz, bool)
            or not isinstance(self.sampling_hz, (int, float))
            or not np.isfinite(self.sampling_hz)
            or self.sampling_hz <= 0
        ):
            raise ValueError("sampling_hz must be finite and greater than zero")
        if not isinstance(self.acceleration, Mapping) or not self.acceleration:
            raise ValueError("acceleration must be a non-empty axis mapping")
        axes: dict[str, NDArray[np.float64]] = {}
        for axis, values in self.acceleration.items():
            axis_name = _nonempty(axis, name="acceleration axis")
            if axis_name in axes:
                raise ValueError(f"duplicate acceleration axis: {axis_name}")
            axes[axis_name] = _signal_array(values, name=f"acceleration[{axis_name!r}]")
        if len({values.size for values in axes.values()}) != 1:
            raise ValueError("all acceleration axes must contain the same number of samples")
        object.__setattr__(self, "acceleration", MappingProxyType(axes))

        object.__setattr__(
            self,
            "window_state_label",
            _nonempty(self.window_state_label, name="window_state_label"),
        )
        if self.terminal_failure_mode is not None:
            object.__setattr__(
                self,
                "terminal_failure_mode",
                _nonempty(self.terminal_failure_mode, name="terminal_failure_mode"),
            )
        if self.sequence_index is not None and (
            isinstance(self.sequence_index, bool)
            or not isinstance(self.sequence_index, int)
            or self.sequence_index < 0
        ):
            raise ValueError("sequence_index must be a non-negative integer or None")

        if self.timestamp_quality not in TIMESTAMP_QUALITIES:
            raise ValueError(f"timestamp_quality must be one of {sorted(TIMESTAMP_QUALITIES)}")
        if self.started_at is None and self.timestamp_quality != "unavailable":
            raise ValueError("started_at is required when timestamp quality is available")
        if self.started_at is not None:
            if not isinstance(self.started_at, datetime):
                raise ValueError("started_at must be a datetime or None")
            if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
                raise ValueError("started_at must include an explicit timezone")
            if self.timestamp_quality == "unavailable":
                raise ValueError("timestamp_quality unavailable cannot accompany started_at")

        _finite_optional(self.temperature_c, name="temperature_c")
        _finite_optional(self.rpm, name="rpm", non_negative=True)
        _finite_optional(self.load, name="load")
        _finite_optional(self.life_fraction, name="life_fraction")
        if self.life_fraction is not None:
            if not 0 <= self.life_fraction <= 1:
                raise ValueError("life_fraction must be in the closed interval [0, 1]")
            if self.sequence_index is None:
                raise ValueError("sequence_index is required when life_fraction is present")
