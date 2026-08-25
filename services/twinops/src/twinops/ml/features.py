"""Causal, trailing-only features for vibration and phase-aware temperature."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureConfig:
    short_window_seconds: float
    long_window_seconds: float
    min_points: int

    def __post_init__(self) -> None:
        if self.short_window_seconds <= 0 or self.long_window_seconds <= 0:
            raise ValueError("feature windows must be positive")
        if self.short_window_seconds > self.long_window_seconds:
            raise ValueError("short window cannot exceed long window")
        if self.min_points < 2:
            raise ValueError("min_points must be at least two")


_FEATURE_COLUMNS = [
    "velocity_median",
    "velocity_mad",
    "velocity_robust_z",
    "velocity_ewma",
    "velocity_slope",
    "velocity_persistence_seconds",
    "velocity_change_point",
    "temperature_median",
    "temperature_deviation",
    "temperature_phase_points",
    "feature_window_start",
    "feature_window_end",
    "feature_valid",
]


def compute_trailing_features(frame: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    """Compute features using only each row and rows preceding it in its cycle."""

    required = {
        "event_at",
        "sensor_id",
        "cycle_id",
        "velocity_rms",
        "temperature",
        "operating_state",
        "is_new_information",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"curated frame is missing columns: {sorted(missing)}")

    output = frame.copy()
    for column in _FEATURE_COLUMNS[:-3]:
        output[column] = np.nan
    output["temperature_phase_points"] = 0
    output["feature_window_start"] = pd.Series(
        pd.NaT, index=output.index, dtype="datetime64[ns, UTC]"
    )
    output["feature_window_end"] = pd.Series(
        pd.NaT, index=output.index, dtype="datetime64[ns, UTC]"
    )
    output["feature_valid"] = False
    if output.empty:
        return output

    grouped = output.groupby(["sensor_id", "cycle_id"], sort=False)
    for _, positions in grouped.indices.items():
        ordered_positions = np.asarray(
            [
                position
                for position in positions
                if bool(output.iloc[position].is_new_information)
            ],
            dtype=int,
        )
        if not len(ordered_positions):
            continue
        times = pd.to_datetime(output.iloc[ordered_positions]["event_at"], utc=True)
        order = np.argsort(times.array.asi8, kind="stable")
        ordered_positions = ordered_positions[order]
        ordered_times = pd.to_datetime(
            output.iloc[ordered_positions]["event_at"], utc=True
        )
        epoch_seconds = ordered_times.array.asi8.astype(float) / 1_000_000_000
        velocities = output.iloc[ordered_positions]["velocity_rms"].to_numpy(dtype=float)

        persistence_started: float | None = None
        for local_index, position in enumerate(ordered_positions):
            now = epoch_seconds[local_index]
            long_start = int(
                np.searchsorted(
                    epoch_seconds[: local_index + 1],
                    now - config.long_window_seconds,
                    side="left",
                )
            )
            short_start = int(
                np.searchsorted(
                    epoch_seconds[: local_index + 1],
                    now - config.short_window_seconds,
                    side="left",
                )
            )
            long_values = velocities[long_start : local_index + 1]
            short_values = velocities[short_start : local_index + 1]
            valid = len(long_values) >= config.min_points
            output.at[output.index[position], "feature_valid"] = bool(valid)
            if not valid:
                persistence_started = None
                continue

            median = float(np.median(long_values))
            mad = float(np.median(np.abs(long_values - median)))
            scale = max(1.4826 * mad, 1e-9)
            robust_z = float(np.clip((velocities[local_index] - median) / scale, -50, 50))
            ewma = _ewma(short_values)
            slope = _slope(
                epoch_seconds[short_start : local_index + 1], short_values
            )
            change_point = _change_point(long_values)
            if abs(robust_z) >= 3:
                if persistence_started is None:
                    persistence_started = now
                persistence_seconds = now - persistence_started
            else:
                persistence_started = None
                persistence_seconds = 0.0

            row_index = output.index[position]
            output.at[row_index, "velocity_median"] = median
            output.at[row_index, "velocity_mad"] = mad
            output.at[row_index, "velocity_robust_z"] = robust_z
            output.at[row_index, "velocity_ewma"] = ewma
            output.at[row_index, "velocity_slope"] = slope
            output.at[row_index, "velocity_persistence_seconds"] = persistence_seconds
            output.at[row_index, "velocity_change_point"] = change_point
            output.at[row_index, "feature_window_start"] = ordered_times.iloc[long_start]
            output.at[row_index, "feature_window_end"] = ordered_times.iloc[local_index]

    _compute_phase_temperature(output, config)
    return output


def _compute_phase_temperature(output: pd.DataFrame, config: FeatureConfig) -> None:
    groups = output.groupby(
        ["sensor_id", "cycle_id", "operating_state"], sort=False
    ).indices
    for _, positions in groups.items():
        ordered = np.asarray(
            [
                position
                for position in positions
                if bool(output.iloc[position].is_new_information)
            ],
            dtype=int,
        )
        if not len(ordered):
            continue
        times = pd.to_datetime(output.iloc[ordered]["event_at"], utc=True)
        order = np.argsort(times.array.asi8, kind="stable")
        ordered = ordered[order]
        ordered_times = pd.to_datetime(output.iloc[ordered]["event_at"], utc=True)
        seconds = ordered_times.array.asi8.astype(float) / 1_000_000_000
        values = output.iloc[ordered]["temperature"].to_numpy(dtype=float)
        for local_index, position in enumerate(ordered):
            start = int(
                np.searchsorted(
                    seconds[: local_index + 1],
                    seconds[local_index] - config.long_window_seconds,
                    side="left",
                )
            )
            trailing = values[start : local_index + 1]
            median = float(np.median(trailing))
            row_index = output.index[position]
            output.at[row_index, "temperature_median"] = median
            output.at[row_index, "temperature_deviation"] = float(values[local_index] - median)
            output.at[row_index, "temperature_phase_points"] = len(trailing)


def _ewma(values: np.ndarray) -> float:
    alpha = 2.0 / (len(values) + 1.0)
    result = float(values[0])
    for value in values[1:]:
        result = alpha * float(value) + (1.0 - alpha) * result
    return result


def _slope(times: np.ndarray, values: np.ndarray) -> float:
    if len(values) < 2 or float(times[-1] - times[0]) == 0:
        return 0.0
    shifted = times - times[0]
    return float(np.polyfit(shifted, values, 1)[0])


def _change_point(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    split = max(1, len(values) // 2)
    return float(np.median(values[split:]) - np.median(values[:split]))
