"""Public assessment boundary for canonical telemetry samples."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import uuid

import numpy as np
import pandas as pd

from twinops.contracts.models import (
    AssessmentDetail,
    AssessmentEvidence,
    AssessmentQuality,
    AssessmentWindow,
    AssetConditionAssessment,
    CanonicalSensorReading,
    ModelMetadata,
    OperatingContext,
)
from twinops.ml.baseline import RobustBaseline
from twinops.ml.curation import curate_samples
from twinops.ml.features import FeatureConfig, compute_trailing_features


@dataclass(frozen=True)
class ScorerConfig:
    gap_seconds: float = 15.0
    max_freshness_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.gap_seconds <= 0 or self.max_freshness_seconds < 0:
            raise ValueError("scorer time limits are invalid")


class AssessmentScorer:
    """Create contract-valid relative assessments from one sensor stream."""

    def __init__(
        self,
        baseline: RobustBaseline,
        *,
        feature_config: FeatureConfig,
        config: ScorerConfig | None = None,
    ) -> None:
        if not baseline.is_fitted:
            raise ValueError("AssessmentScorer requires a fitted baseline")
        self.baseline = baseline
        self.feature_config = feature_config
        self.config = config or ScorerConfig()

    @property
    def config_hash(self) -> str:
        payload = {
            "baseline": asdict(self.baseline.config),
            "features": asdict(self.feature_config),
            "scorer": asdict(self.config),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return f"sha256:{sha256(encoded.encode()).hexdigest()}"

    def assess(
        self,
        samples: Sequence[CanonicalSensorReading],
        *,
        now: datetime,
    ) -> AssetConditionAssessment:
        if not samples:
            raise ValueError("at least one canonical reading is required")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        now = now.astimezone(timezone.utc)

        ordered = sorted(samples, key=_event_datetime)
        sensor_ids = {sample.sensor_id for sample in ordered}
        if len(sensor_ids) != 1:
            raise ValueError(
                "AssessmentScorer.assess requires readings from a single sensor"
            )
        identity_flags: list[str] = []
        if len({sample.asset_tag for sample in ordered}) != 1:
            identity_flags.append("mixed_asset_tags")
        relevant = _relevant_tail(
            ordered,
            seconds=max(
                self.feature_config.long_window_seconds,
                self.baseline.config.persistence_seconds,
            ),
        )
        frame = curate_samples(relevant, gap_seconds=self.config.gap_seconds)
        features = compute_trailing_features(frame, self.feature_config)

        flags = list(identity_flags)
        for row_flags in frame["quality_flags"]:
            for flag in row_flags:
                if flag not in flags:
                    flags.append(flag)
        last_received = pd.Timestamp(frame.iloc[-1].received_at).to_pydatetime()
        freshness_ms = max(0.0, (now - last_received).total_seconds() * 1000.0)
        if freshness_ms > self.config.max_freshness_seconds * 1000:
            flags.append("stale_window")

        hard_quality = bool(
            identity_flags
            or any(
                marker in flag.lower()
                for flag in flags
                for marker in ("gap", "stale", "invalid")
            )
            or not bool(features.iloc[-1].feature_valid)
        )
        if hard_quality:
            if not bool(features.iloc[-1].feature_valid) and "incomplete_window" not in flags:
                flags.append("incomplete_window")
            return self._assessment(
                frame,
                now=now,
                freshness_ms=freshness_ms,
                quality_status="insufficient_data",
                flags=flags,
                score_row=None,
                evidence=[],
            )

        scored = self.baseline.score(features)
        last = scored.iloc[-1]
        quality_status = "degraded" if flags else "ok"
        evidence = self._evidence(last)
        return self._assessment(
            frame,
            now=now,
            freshness_ms=freshness_ms,
            quality_status=quality_status,
            flags=flags,
            score_row=last,
            evidence=evidence,
        )

    def _assessment(
        self,
        frame: pd.DataFrame,
        *,
        now: datetime,
        freshness_ms: float,
        quality_status: str,
        flags: list[str],
        score_row: pd.Series | None,
        evidence: list[AssessmentEvidence],
    ) -> AssetConditionAssessment:
        first = frame.iloc[0]
        last = frame.iloc[-1]
        insufficient = score_row is None
        assessment_status = "insufficient_data" if insufficient else str(score_row.status)
        anomaly_score = 0.0 if insufficient else float(score_row.anomaly_score)
        deterioration_score = 0.0 if insufficient else float(score_row.deterioration_score)
        persistence_seconds = 0.0 if insufficient else float(score_row.persistence_seconds)
        episode_id = None if insufficient else score_row.episode_id
        identity = "|".join(
            [
                *(str(value) for value in frame["reading_id"]),
                self.config_hash,
                _timestamp(now),
            ]
        )
        trained_until = self.baseline.trained_until_
        assert trained_until is not None
        return AssetConditionAssessment(
            schemaVersion="1.0",
            assessmentId=str(uuid.uuid5(uuid.NAMESPACE_URL, identity)),
            assetTag=str(first.asset_tag),
            sensorId=str(first.sensor_id),
            window=AssessmentWindow(
                start=_timestamp(pd.Timestamp(first.event_at).to_pydatetime()),
                end=_timestamp(pd.Timestamp(last.event_at).to_pydatetime()),
                receivedAt=_timestamp(pd.Timestamp(last.received_at).to_pydatetime()),
                freshnessMs=freshness_ms,
            ),
            quality=AssessmentQuality(status=quality_status, flags=flags),
            operatingContext=OperatingContext(
                state=str(last.operating_state), estimated=bool(last.state_estimated)
            ),
            assessment=AssessmentDetail(
                status=assessment_status,
                anomalyScore=anomaly_score,
                deteriorationScore=deterioration_score,
                scoreSemantics="relative_to_historical_baseline_not_failure_probability",
                episodeId=episode_id,
                persistenceSeconds=persistence_seconds,
                scoreCalculation=None if insufficient else {
                    "robustZAtScore100": self.baseline.config.robust_z_at_score_100,
                    "positiveDistanceScore": float(score_row.positive_distance_score),
                    "previousDeteriorationScore": float(score_row.previous_deterioration_score),
                    "ewmaAlpha": self.baseline.config.ewma_alpha,
                    "watchThreshold": self.baseline.config.watch_threshold,
                    "alertThreshold": self.baseline.config.alert_threshold,
                    "persistenceRequiredSeconds": self.baseline.config.persistence_seconds,
                    "shortWindowSeconds": self.feature_config.short_window_seconds,
                    "longWindowSeconds": self.feature_config.long_window_seconds,
                },
            ),
            componentTag=None,
            recommendation=None,
            humanValidationRequired=True,
            evidence=evidence,
            model=ModelMetadata(
                name=self.baseline.model_name,
                version=self.baseline.model_version,
                configHash=self.config_hash,
                trainedUntil=_timestamp(trained_until.to_pydatetime()),
            ),
            limitations=[
                "Relative historical distance is not failure probability.",
                "Operating state is estimated from vibration velocity RMS.",
                "Acceleration statistic is unknown and excluded from the official score.",
                "No physical S1-S2 comparison is performed.",
            ],
        )

    def _evidence(self, row: pd.Series) -> list[AssessmentEvidence]:
        units = {
            "velocity_ewma": "mm/s",
            "velocity_slope": "mm/s/s",
            "velocity_change_point": "mm/s",
            "temperature_deviation": "degC",
        }
        evidence: list[AssessmentEvidence] = []
        sensor_id = str(row.sensor_id)
        for feature in self.baseline.config.feature_columns:
            value = float(row[feature])
            if not np.isfinite(value):
                continue
            baseline = self.baseline.centers_[sensor_id][feature]
            deviation = value - baseline
            scale = self.baseline.scales_[sensor_id][feature]
            distance = deviation / scale
            direction = "stable" if abs(deviation) <= 1e-12 else ("up" if deviation > 0 else "down")
            evidence.append(
                AssessmentEvidence(
                    id=f"ev-v1-{feature.replace('_', '-')}",
                    feature=feature,
                    value=value,
                    unit=units[feature],
                    baseline=baseline,
                    deviation=deviation,
                    direction=direction,
                    windowSeconds=(self.feature_config.short_window_seconds
                                   if feature in ("velocity_ewma", "velocity_slope")
                                   else self.feature_config.long_window_seconds),
                    robustScale=scale,
                    normalizedDistance=distance,
                    anomalyScoreComponent=float(np.clip(abs(distance) / self.baseline.config.robust_z_at_score_100 * 100, 0, 100)),
                    positiveScoreComponent=float(np.clip(distance / self.baseline.config.robust_z_at_score_100 * 100, 0, 100)),
                )
            )
        return evidence


def _event_datetime(sample: CanonicalSensorReading) -> datetime:
    return datetime.fromisoformat((sample.observed_at or sample.received_at).replace("Z", "+00:00"))


def _relevant_tail(
    samples: list[CanonicalSensorReading], *, seconds: float
) -> list[CanonicalSensorReading]:
    times = [_event_datetime(sample).timestamp() for sample in samples]
    start = bisect_left(times, times[-1] - seconds)
    return samples[max(0, start - 1) :]


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
