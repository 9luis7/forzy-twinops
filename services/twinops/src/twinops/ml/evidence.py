"""Shared evidence projection for live and historical baseline scores."""

from __future__ import annotations

import numpy as np
import pandas as pd

from twinops.contracts.models import AssessmentEvidence
from twinops.ml.baseline import RobustBaseline


_EVIDENCE_UNITS = {
    "velocity_ewma": "mm/s",
    "velocity_slope": "mm/s/s",
    "velocity_change_point": "mm/s",
    "temperature_deviation": "degC",
}


def build_assessment_evidence(
    row: pd.Series,
    baseline: RobustBaseline,
    *,
    window_seconds: float,
) -> tuple[AssessmentEvidence, ...]:
    """Project the four official finite features with stable units/directions."""

    sensor_id = str(row.sensor_id)
    evidence: list[AssessmentEvidence] = []
    for feature in baseline.config.feature_columns:
        if feature not in _EVIDENCE_UNITS:
            raise ValueError(f"unsupported official evidence feature: {feature}")
        value = float(row[feature])
        if not np.isfinite(value):
            continue
        center = float(baseline.centers_[sensor_id][feature])
        deviation = value - center
        direction = (
            "stable"
            if abs(deviation) <= 1e-12
            else ("up" if deviation > 0 else "down")
        )
        evidence.append(
            AssessmentEvidence(
                id=f"ev-v1-{feature.replace('_', '-')}",
                feature=feature,
                value=value,
                unit=_EVIDENCE_UNITS[feature],
                baseline=center,
                deviation=deviation,
                direction=direction,
                windowSeconds=window_seconds,
            )
        )
    return tuple(evidence)
