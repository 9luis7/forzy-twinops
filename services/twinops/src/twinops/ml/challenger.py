"""Optional Isolation Forest challenger kept separate from the official baseline."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


@dataclass(frozen=True)
class ChallengerConfig:
    feature_columns: tuple[str, ...] = (
        "velocity_ewma",
        "velocity_slope",
        "velocity_change_point",
        "temperature_deviation",
    )
    n_estimators: int = 100
    contamination: str | float = "auto"
    random_state: int = 42

    def __post_init__(self) -> None:
        if self.n_estimators <= 0:
            raise ValueError("n_estimators must be positive")


@dataclass(frozen=True)
class ChallengerDecision:
    recommended: bool
    promoted: bool
    reason: str


class IsolationForestChallenger:
    """Deterministic challenger trained only on explicit steady baseline rows."""

    def __init__(self, config: ChallengerConfig | None = None) -> None:
        self.config = config or ChallengerConfig()
        self.model_: IsolationForest | None = None
        self.training_rows_ = 0
        self.training_cycle_ids_: tuple[int, ...] = ()

    def fit(self, features: pd.DataFrame) -> "IsolationForestChallenger":
        self._require_columns(features)
        mask = features["feature_valid"].astype(bool) & features["operating_state"].eq(
            "steady"
        )
        if "baseline_eligible" in features:
            mask &= features["baseline_eligible"].astype(bool)
        baseline = features.loc[mask]
        if baseline.empty:
            raise ValueError("challenger requires valid steady baseline rows")
        values = baseline.loc[:, self.config.feature_columns].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("challenger baseline contains non-finite features")
        model = IsolationForest(
            n_estimators=self.config.n_estimators,
            contamination=self.config.contamination,
            random_state=self.config.random_state,
            n_jobs=1,
        )
        model.fit(values)
        self.model_ = model
        self.training_rows_ = len(baseline)
        self.training_cycle_ids_ = tuple(
            sorted(int(value) for value in baseline["cycle_id"].unique())
        )
        return self

    def score(self, features: pd.DataFrame) -> np.ndarray:
        if self.model_ is None:
            raise RuntimeError("challenger must be fitted before scoring")
        self._require_columns(features)
        values = features.loc[:, self.config.feature_columns].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("challenger input contains non-finite features")
        distance = -self.model_.decision_function(values)
        return np.clip(distance * 100.0, 0.0, 100.0)

    def _require_columns(self, features: pd.DataFrame) -> None:
        required = {
            "cycle_id",
            "operating_state",
            "feature_valid",
            *self.config.feature_columns,
        }
        missing = required.difference(features.columns)
        if missing:
            raise ValueError(f"challenger frame is missing columns: {sorted(missing)}")


def compare_challenger(
    *,
    baseline_stability: float,
    baseline_normal_alert_load: float,
    challenger_stability: float,
    challenger_normal_alert_load: float,
) -> ChallengerDecision:
    """Recommend review only when stability improves without more normal alerts."""

    recommended = (
        challenger_stability < baseline_stability
        and challenger_normal_alert_load <= baseline_normal_alert_load
    )
    reason = (
        "Challenger meets the comparison gate but requires human validation before promotion."
        if recommended
        else "Challenger does not meet the stability and normal-alert-load gate; human review retains baseline."
    )
    return ChallengerDecision(recommended=recommended, promoted=False, reason=reason)

