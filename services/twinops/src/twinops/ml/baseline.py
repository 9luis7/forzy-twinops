"""Versioned robust baseline with deterministic EWMA persistence scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BaselineConfig:
    feature_columns: tuple[str, ...] = (
        "velocity_ewma",
        "velocity_slope",
        "velocity_change_point",
        "temperature_deviation",
    )
    watch_threshold: float = 40.0
    alert_threshold: float = 70.0
    persistence_seconds: float = 30.0
    ewma_alpha: float = 0.35
    robust_z_at_score_100: float = 6.0
    minimum_scale: float = 1e-6

    def __post_init__(self) -> None:
        if not self.feature_columns:
            raise ValueError("at least one official feature is required")
        if not 0 <= self.watch_threshold <= self.alert_threshold <= 100:
            raise ValueError("score thresholds must satisfy 0 <= watch <= alert <= 100")
        if self.persistence_seconds < 0:
            raise ValueError("persistence_seconds cannot be negative")
        if not 0 < self.ewma_alpha <= 1:
            raise ValueError("ewma_alpha must be in (0, 1]")
        if self.robust_z_at_score_100 <= 0 or self.minimum_scale <= 0:
            raise ValueError("score scale values must be positive")


class RobustBaseline:
    """Median/MAD baseline fitted only from valid steady-regime rows."""

    model_name = "robust-baseline"
    model_version = "1.0.1"

    def __init__(self, config: BaselineConfig | None = None) -> None:
        self.config = config or BaselineConfig()
        self.centers_: dict[str, dict[str, float]] = {}
        self.scales_: dict[str, dict[str, float]] = {}
        self.trained_until_: pd.Timestamp | None = None

    @property
    def config_hash(self) -> str:
        encoded = json.dumps(asdict(self.config), sort_keys=True, separators=(",", ":"))
        return f"sha256:{sha256(encoded.encode()).hexdigest()}"

    @property
    def is_fitted(self) -> bool:
        return bool(self.centers_)

    def fit(self, features: pd.DataFrame) -> "RobustBaseline":
        self._require_columns(features)
        calibration = features.loc[
            features["feature_valid"].astype(bool)
            & features["operating_state"].eq("steady")
        ]
        if calibration.empty:
            raise ValueError("baseline calibration requires valid steady rows")

        centers: dict[str, dict[str, float]] = {}
        scales: dict[str, dict[str, float]] = {}
        for sensor_id, sensor_rows in calibration.groupby("sensor_id", sort=True):
            sensor_centers: dict[str, float] = {}
            sensor_scales: dict[str, float] = {}
            for column in self.config.feature_columns:
                values = sensor_rows[column].to_numpy(dtype=float)
                values = values[np.isfinite(values)]
                if not len(values):
                    raise ValueError(
                        f"baseline feature has no finite steady values for {sensor_id}: {column}"
                    )
                center = float(np.median(values))
                mad = float(np.median(np.abs(values - center)))
                sensor_centers[column] = center
                sensor_scales[column] = max(
                    1.4826 * mad,
                    abs(center) * 0.01,
                    self.config.minimum_scale,
                )
            centers[str(sensor_id)] = sensor_centers
            scales[str(sensor_id)] = sensor_scales
        self.centers_ = centers
        self.scales_ = scales
        self.trained_until_ = pd.to_datetime(calibration["event_at"], utc=True).max()
        return self

    def score(self, features: pd.DataFrame) -> pd.DataFrame:
        if not self.is_fitted:
            raise RuntimeError("baseline must be fitted before scoring")
        self._require_columns(features)
        result = features.copy()
        requested_sensors = {str(value) for value in result["sensor_id"].unique()}
        unknown_sensors = requested_sensors.difference(self.centers_)
        if unknown_sensors:
            raise ValueError(
                f"no fitted sensor baseline for: {sorted(unknown_sensors)}"
            )
        signed_z = np.zeros((len(result), len(self.config.feature_columns)), dtype=float)
        for sensor_id, positions in result.groupby("sensor_id", sort=False).indices.items():
            sensor_key = str(sensor_id)
            position_array = np.asarray(positions, dtype=int)
            signed_z[position_array] = np.column_stack(
                [
                    (
                        result.iloc[position_array][column].to_numpy(dtype=float)
                        - self.centers_[sensor_key][column]
                    )
                    / self.scales_[sensor_key][column]
                    for column in self.config.feature_columns
                ]
            )
        signed_z[~np.isfinite(signed_z)] = 0.0
        anomaly = np.clip(
            np.max(np.abs(signed_z), axis=1)
            / self.config.robust_z_at_score_100
            * 100.0,
            0.0,
            100.0,
        )
        positive_distance = np.clip(
            np.max(signed_z, axis=1)
            / self.config.robust_z_at_score_100
            * 100.0,
            0.0,
            100.0,
        )
        result["anomaly_score"] = anomaly
        result["deterioration_score"] = 0.0
        result["persistence_seconds"] = 0.0
        result["status"] = "normal"
        result["episode_id"] = None

        groups = result.groupby(["sensor_id", "cycle_id"], sort=False).indices
        for _, positions in groups.items():
            ordered = np.asarray(positions, dtype=int)
            times = pd.to_datetime(result.iloc[ordered]["event_at"], utc=True)
            order = np.argsort(times.array.asi8, kind="stable")
            ordered = ordered[order]
            seconds = (
                pd.to_datetime(result.iloc[ordered]["event_at"], utc=True).array.asi8.astype(float)
                / 1_000_000_000
            )
            ewma = 0.0
            episode_started: float | None = None
            episode_id: str | None = None
            for position, second in zip(ordered, seconds, strict=True):
                ewma = (
                    self.config.ewma_alpha * float(positive_distance[position])
                    + (1.0 - self.config.ewma_alpha) * ewma
                )
                row_index = result.index[position]
                result.at[row_index, "deterioration_score"] = float(np.clip(ewma, 0, 100))
                combined = max(float(anomaly[position]), ewma)
                if combined >= self.config.watch_threshold:
                    if episode_started is None:
                        episode_started = float(second)
                        episode_id = (
                            f"episode-v1-{result.iloc[position].sensor_id}-"
                            f"{result.iloc[position].cycle_id}-{int(second)}"
                        )
                    persistence = float(second) - episode_started
                    status = (
                        "alert"
                        if combined >= self.config.alert_threshold
                        and persistence >= self.config.persistence_seconds
                        else "watch"
                    )
                    result.at[row_index, "persistence_seconds"] = persistence
                    result.at[row_index, "status"] = status
                    result.at[row_index, "episode_id"] = episode_id
                else:
                    episode_started = None
                    episode_id = None
        return result

    def _require_columns(self, features: pd.DataFrame) -> None:
        required = {
            "event_at",
            "sensor_id",
            "cycle_id",
            "operating_state",
            "feature_valid",
            *self.config.feature_columns,
        }
        missing = required.difference(features.columns)
        if missing:
            raise ValueError(f"feature frame is missing columns: {sorted(missing)}")
