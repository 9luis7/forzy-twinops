"""Chronological cycle-grouped walk-forward evaluation."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from typing import Literal, Sequence

import numpy as np
import pandas as pd

from twinops.contracts.models import AssessmentEvidence
from twinops.ml.baseline import RobustBaseline
from twinops.ml.evidence import build_assessment_evidence
from twinops.ml.features import FeatureConfig
from twinops.ml.scorer import ScorerConfig


@dataclass(frozen=True)
class WalkForwardFold:
    train_cycle_ids: tuple[int, ...]
    test_cycle_ids: tuple[int, ...]
    frozen_holdout: bool = False


@dataclass(frozen=True)
class BacktestReport:
    folds: list[dict[str, object]]
    cycle_results: list[dict[str, object]]
    threshold_stability: dict[str, float]
    candidate_events: list[dict[str, object]]
    latency_ms: dict[str, float]
    holdout_frozen: bool
    score_semantics: str = "relative_to_historical_baseline_not_failure_probability"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WalkForwardRowAssessmentV1:
    fold_id: str
    sensor_id: str
    reading_id: str
    anchor_event_at: datetime
    training_start: datetime
    training_end: datetime
    window_start: datetime
    window_end: datetime
    status: Literal["normal", "watch", "alert"]
    anomaly_score: float
    deterioration_score: float
    episode_id: str | None
    episode_started_at: datetime | None
    persistence_seconds: float
    persistence_count: int
    quality_status: Literal["ok", "degraded", "insufficient_data"]
    quality_flags: tuple[str, ...]
    evidence: tuple[AssessmentEvidence, ...]
    model_family: str
    model_version: str
    fold_model_hash: str


@dataclass(frozen=True)
class WalkForwardEvaluationV1:
    rows: tuple[WalkForwardRowAssessmentV1, ...]
    evaluated_cycle_ids: tuple[int, ...]
    skipped_cycle_ids: tuple[int, ...]
    fold_count: int


def evaluate_walk_forward_rows(
    frame: pd.DataFrame,
    pipeline: RobustBaseline,
    folds: Sequence[WalkForwardFold],
) -> WalkForwardEvaluationV1:
    """Score only finite original rows with a freshly fitted causal fold model."""

    frame = frame.reset_index(drop=True).copy()
    required = {
        "cycle_id",
        "event_at",
        "sensor_id",
        "reading_id",
        "operating_state",
        "feature_valid",
        "feature_window_start",
        "feature_window_end",
        *pipeline.config.feature_columns,
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"row evaluation frame is missing columns: {sorted(missing)}")
    if not folds:
        raise ValueError("at least one walk-forward fold is required")
    timeline = _cycle_timeline(frame)
    all_cycle_ids = {int(value) for value in timeline.index}
    rows: list[WalkForwardRowAssessmentV1] = []
    evaluated_cycle_ids: set[int] = set()
    represented_folds: set[str] = set()

    for fold_index, fold in enumerate(folds):
        _validate_fold(frame, fold)
        train = frame.loc[frame["cycle_id"].isin(fold.train_cycle_ids)].copy()
        test = frame.loc[frame["cycle_id"].isin(fold.test_cycle_ids)].copy()
        model = RobustBaseline(pipeline.config).fit(train)
        fold_id = f"fold-v1-{fold_index:04d}"
        fold_hash = _fold_model_hash(model)
        training_start = _as_datetime(pd.to_datetime(train["event_at"], utc=True).min())
        training_end = _as_datetime(model.trained_until_)

        normalized = test.copy()
        normalized["event_at"] = pd.to_datetime(
            normalized["event_at"], utc=True, errors="coerce"
        )
        normalized["feature_window_start"] = pd.to_datetime(
            normalized["feature_window_start"], utc=True, errors="coerce"
        )
        normalized["feature_window_end"] = pd.to_datetime(
            normalized["feature_window_end"], utc=True, errors="coerce"
        )
        finite = np.isfinite(
            normalized.loc[:, list(model.config.feature_columns)].to_numpy(dtype=float)
        ).all(axis=1)
        eligible = (
            normalized["feature_valid"].fillna(False).astype(bool)
            & normalized["reading_id"].notna()
            & normalized["reading_id"].astype(str).str.strip().ne("")
            & normalized["event_at"].notna()
            & normalized["feature_window_start"].notna()
            & normalized["feature_window_end"].notna()
            & normalized.get(
                "is_new_information", pd.Series(True, index=normalized.index)
            ).fillna(False).astype(bool)
            & finite
            & normalized["feature_window_start"].gt(pd.Timestamp(training_end))
            & normalized["feature_window_start"].le(normalized["feature_window_end"])
            & normalized["feature_window_end"].eq(normalized["event_at"])
        )
        eligible_rows = normalized.loc[eligible].copy()
        if eligible_rows["reading_id"].astype(str).duplicated().any():
            raise ValueError("a causal fold cannot evaluate the same reading more than once")
        scored_by_index = _score_causal_segments(normalized, eligible, model)
        state_by_boundary: dict[tuple[object, ...], tuple[str, datetime, int]] = {}
        last_boundary_by_stream: dict[tuple[str, int], tuple[object, ...]] = {}
        ordered = normalized.assign(_reading_order=normalized["reading_id"].fillna(""))
        ordered = ordered.sort_values(
            ["event_at", "_reading_order", "sensor_id"], kind="stable"
        )
        for index, source_row in ordered.iterrows():
            stream = (str(source_row.sensor_id), int(source_row.cycle_id))
            boundary = (
                str(source_row.get("source", "unknown")),
                str(source_row.sensor_id),
                int(source_row.cycle_id),
                _boundary_value(source_row.get("collection_policy_id")),
                model.model_name,
                model.model_version,
                fold_id,
            )
            previous_boundary = last_boundary_by_stream.get(stream)
            if previous_boundary is not None and previous_boundary != boundary:
                state_by_boundary.pop(previous_boundary, None)
            last_boundary_by_stream[stream] = boundary
            if index not in scored_by_index:
                state_by_boundary.pop(boundary, None)
                continue
            scored_row = scored_by_index[index]
            quality_flags = _quality_flags(source_row.get("quality_flags", ()))
            if any("gap" in flag.lower() for flag in quality_flags):
                state_by_boundary.pop(boundary, None)
            anomaly_score = float(scored_row.anomaly_score)
            deterioration_score = float(scored_row.deterioration_score)
            combined = max(anomaly_score, deterioration_score)
            anchor_at = _as_datetime(source_row.event_at)
            candidate = combined >= model.config.watch_threshold
            episode_id: str | None = None
            episode_started_at: datetime | None = None
            persistence_count = 0
            persistence_seconds = 0.0
            status: Literal["normal", "watch", "alert"] = "normal"
            if candidate:
                previous = state_by_boundary.get(boundary)
                if previous is None:
                    episode_started_at = anchor_at
                    episode_id = (
                        f"episode-v1-{fold_id}-{source_row.sensor_id}-"
                        f"{int(source_row.cycle_id)}-{source_row.reading_id}"
                    )
                    persistence_count = 1
                else:
                    episode_id, episode_started_at, previous_count = previous
                    persistence_count = previous_count + 1
                persistence_seconds = (anchor_at - episode_started_at).total_seconds()
                status = (
                    "alert"
                    if combined >= model.config.alert_threshold
                    and persistence_seconds >= model.config.persistence_seconds
                    else "watch"
                )
                state_by_boundary[boundary] = (
                    episode_id,
                    episode_started_at,
                    persistence_count,
                )
            else:
                state_by_boundary.pop(boundary, None)
            window_start = _as_datetime(source_row.feature_window_start)
            window_end = _as_datetime(source_row.feature_window_end)
            row_assessment = WalkForwardRowAssessmentV1(
                fold_id=fold_id,
                sensor_id=str(source_row.sensor_id),
                reading_id=str(source_row.reading_id),
                anchor_event_at=anchor_at,
                training_start=training_start,
                training_end=training_end,
                window_start=window_start,
                window_end=window_end,
                status=status,
                anomaly_score=anomaly_score,
                deterioration_score=deterioration_score,
                episode_id=episode_id,
                episode_started_at=episode_started_at,
                persistence_seconds=persistence_seconds,
                persistence_count=persistence_count,
                quality_status="degraded" if quality_flags else "ok",
                quality_flags=quality_flags,
                evidence=build_assessment_evidence(
                    scored_row,
                    model,
                    window_seconds=(window_end - window_start).total_seconds(),
                ),
                model_family=model.model_name,
                model_version=model.model_version,
                fold_model_hash=fold_hash,
            )
            rows.append(row_assessment)
            evaluated_cycle_ids.add(int(source_row.cycle_id))
            represented_folds.add(fold_id)

    rows.sort(
        key=lambda row: (
            row.anchor_event_at,
            row.reading_id,
            row.sensor_id,
            row.fold_id,
        )
    )
    return WalkForwardEvaluationV1(
        rows=tuple(rows),
        evaluated_cycle_ids=tuple(sorted(evaluated_cycle_ids)),
        skipped_cycle_ids=tuple(sorted(all_cycle_ids.difference(evaluated_cycle_ids))),
        fold_count=len(represented_folds),
    )


def _score_causal_segments(
    frame: pd.DataFrame,
    eligible: pd.Series,
    model: RobustBaseline,
) -> dict[int, pd.Series]:
    scored_by_index: dict[int, pd.Series] = {}
    groups = frame.groupby(["sensor_id", "cycle_id"], sort=False).indices
    for positions in groups.values():
        ordered = frame.iloc[np.asarray(positions, dtype=int)].copy()
        ordered = ordered.assign(_reading_order=ordered["reading_id"].fillna(""))
        ordered = ordered.sort_values(["event_at", "_reading_order"], kind="stable")
        segment: list[int] = []
        previous_boundary: tuple[object, object] | None = None

        def flush() -> None:
            if not segment:
                return
            scored = model.score(frame.loc[segment].copy())
            scored_by_index.update(
                {index: row for index, row in scored.iterrows()}
            )
            segment.clear()

        for index, source_row in ordered.iterrows():
            boundary = (
                str(source_row.get("source", "unknown")),
                _boundary_value(source_row.get("collection_policy_id")),
            )
            quality_flags = _quality_flags(source_row.get("quality_flags", ()))
            gap_before = any("gap" in flag.lower() for flag in quality_flags)
            if not bool(eligible.loc[index]):
                flush()
                previous_boundary = None
                continue
            if gap_before or (
                previous_boundary is not None and previous_boundary != boundary
            ):
                flush()
            segment.append(int(index))
            previous_boundary = boundary
        flush()
    return scored_by_index


def _validate_fold(frame: pd.DataFrame, fold: WalkForwardFold) -> None:
    if not fold.train_cycle_ids or not fold.test_cycle_ids:
        raise ValueError("walk-forward folds require train and test cycles")
    if set(fold.train_cycle_ids).intersection(fold.test_cycle_ids):
        raise ValueError("a fold cannot split the same cycle across train and test")
    if max(fold.train_cycle_ids) >= min(fold.test_cycle_ids):
        raise ValueError("walk-forward training cycles must precede test cycles")
    train = frame.loc[frame["cycle_id"].isin(fold.train_cycle_ids)]
    test = frame.loc[frame["cycle_id"].isin(fold.test_cycle_ids)]
    if train.empty or test.empty:
        raise ValueError("fold references a cycle absent from the feature frame")
    if pd.to_datetime(train["event_at"], utc=True).max() >= pd.to_datetime(
        test["event_at"], utc=True
    ).min():
        raise ValueError("training event_at values must be strictly before test event_at values")


def _fold_model_hash(model: RobustBaseline) -> str:
    trained_until = model.trained_until_
    if trained_until is None:
        raise ValueError("causal fold model is not fitted")
    payload = {
        "baselineConfig": asdict(model.config),
        "centers": {
            sensor: {feature: values[feature] for feature in sorted(values)}
            for sensor, values in sorted(model.centers_.items())
        },
        "modelFamily": model.model_name,
        "modelVersion": model.model_version,
        "scales": {
            sensor: {feature: values[feature] for feature in sorted(values)}
            for sensor, values in sorted(model.scales_.items())
        },
        "trainedUntil": pd.Timestamp(trained_until).isoformat(),
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return f"sha256:{sha256(canonical.encode()).hexdigest()}"


def _quality_flags(value: object) -> tuple[str, ...]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ()
    if isinstance(value, str):
        candidates = (value,)
    else:
        candidates = tuple(str(item) for item in value)
    return tuple(sorted(set(flag for flag in candidates if flag)))


def _boundary_value(value: object) -> object:
    if value is None or pd.isna(value):
        return None
    return value


def _as_datetime(value: object) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime()


def build_walk_forward_folds(
    frame: pd.DataFrame, *, holdout_count: int = 2
) -> list[WalkForwardFold]:
    timeline = _cycle_timeline(frame)
    cycle_ids = tuple(int(value) for value in timeline.index)
    if holdout_count < 1:
        raise ValueError("holdout_count must be positive")
    if len(cycle_ids) < holdout_count + 3:
        raise ValueError("walk-forward requires two seed cycles, development, and holdout")
    holdout_start = len(cycle_ids) - holdout_count
    folds = []
    for test_index in range(2, holdout_start):
        train_cycle_ids = cycle_ids[:test_index]
        if not _calibration_ready(frame, train_cycle_ids):
            continue
        folds.append(
            WalkForwardFold(
                train_cycle_ids=train_cycle_ids,
                test_cycle_ids=(cycle_ids[test_index],),
            )
        )
    frozen_train_ids = cycle_ids[:holdout_start]
    if not _calibration_ready(frame, frozen_train_ids):
        raise ValueError("walk-forward has no valid steady calibration per sensor")
    folds.append(
        WalkForwardFold(
            train_cycle_ids=frozen_train_ids,
            test_cycle_ids=cycle_ids[holdout_start:],
            frozen_holdout=True,
        )
    )
    return folds


def _calibration_ready(frame: pd.DataFrame, cycle_ids: tuple[int, ...]) -> bool:
    required = {"sensor_id", "cycle_id", "operating_state", "feature_valid"}
    if not required.issubset(frame.columns):
        return True
    expected_sensors = {str(value) for value in frame["sensor_id"].unique()}
    calibration = frame.loc[
        frame["cycle_id"].isin(cycle_ids)
        & frame["feature_valid"].astype(bool)
        & frame["operating_state"].eq("steady")
    ]
    return {str(value) for value in calibration["sensor_id"].unique()} == expected_sensors


def run_backtest(
    frame: pd.DataFrame,
    pipeline: RobustBaseline,
    folds: Sequence[WalkForwardFold],
) -> BacktestReport:
    """Fit every fold from past cycles only and report label-free metrics."""

    required = {"cycle_id", "operating_state", "event_at"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"backtest frame is missing columns: {sorted(missing)}")
    if not folds:
        raise ValueError("at least one walk-forward fold is required")
    _cycle_timeline(frame)

    cycle_results: list[dict[str, object]] = []
    candidate_events: list[dict[str, object]] = []
    fold_records: list[dict[str, object]] = []
    watch_thresholds: list[float] = []
    alert_thresholds: list[float] = []
    latencies: list[float] = []

    for fold_index, fold in enumerate(folds):
        if set(fold.train_cycle_ids).intersection(fold.test_cycle_ids):
            raise ValueError("a fold cannot split the same cycle across train and test")
        if max(fold.train_cycle_ids) >= min(fold.test_cycle_ids):
            raise ValueError("walk-forward training cycles must precede test cycles")
        train = frame.loc[frame["cycle_id"].isin(fold.train_cycle_ids)].copy()
        test = frame.loc[frame["cycle_id"].isin(fold.test_cycle_ids)].copy()
        if train.empty or test.empty:
            raise ValueError("fold references a cycle absent from the feature frame")
        if train["event_at"].max() >= test["event_at"].min():
            raise ValueError(
                "training event_at values must be strictly before test event_at values"
            )
        model = RobustBaseline(pipeline.config).fit(train)
        started = perf_counter()
        scored = model.score(test)
        latencies.append((perf_counter() - started) * 1000.0)
        watch_thresholds.append(model.config.watch_threshold)
        alert_thresholds.append(model.config.alert_threshold)
        fold_records.append(
            {
                "fold": fold_index,
                "train_cycle_ids": list(fold.train_cycle_ids),
                "test_cycle_ids": list(fold.test_cycle_ids),
                "frozen_holdout": fold.frozen_holdout,
                "trained_until": model.trained_until_.isoformat(),
            }
        )

        for (cycle_id, regime), group in scored.groupby(
            ["cycle_id", "operating_state"], sort=True
        ):
            cycle_results.append(
                {
                    "fold": fold_index,
                    "cycle_id": int(cycle_id),
                    "regime": str(regime),
                    "rows": int(len(group)),
                    "max_anomaly_score": float(group["anomaly_score"].max()),
                    "max_deterioration_score": float(
                        group["deterioration_score"].max()
                    ),
                    "watch_episodes": _episode_count(group, "watch"),
                    "alert_episodes": _episode_count(group, "alert"),
                    "steady_alert_seconds": _steady_alert_seconds(group),
                }
            )
        for _, row in scored.iterrows():
            candidate_events.append(
                {
                    "fold": fold_index,
                    "cycle_id": int(row.cycle_id),
                    "sensor_id": str(row.sensor_id),
                    "observed_at": pd.Timestamp(row.event_at).isoformat(),
                    "score": float(max(row.anomaly_score, row.deterioration_score)),
                    "classification": "candidate_not_ground_truth",
                }
            )

    candidate_events.sort(key=lambda row: (-float(row["score"]), str(row["observed_at"])))
    latency = np.asarray(latencies, dtype=float)
    return BacktestReport(
        folds=fold_records,
        cycle_results=cycle_results,
        threshold_stability={
            "watch_range": float(max(watch_thresholds) - min(watch_thresholds)),
            "alert_range": float(max(alert_thresholds) - min(alert_thresholds)),
        },
        candidate_events=candidate_events[:10],
        latency_ms={
            "p50": float(np.percentile(latency, 50)),
            "p95": float(np.percentile(latency, 95)),
            "p99": float(np.percentile(latency, 99)),
        },
        holdout_frozen=bool(folds[-1].frozen_holdout),
    )


def run_backtest_csv(
    input_path: str | Path,
    output_path: str | Path,
    *,
    holdout_count: int = 2,
    feature_config: FeatureConfig = FeatureConfig(10, 60, 3),
    scorer_config: ScorerConfig = ScorerConfig(),
) -> BacktestReport:
    """Run the frozen pipeline from an already curated feature CSV."""

    source = Path(input_path)
    frame = pd.read_csv(source)
    frame["event_at"] = pd.to_datetime(frame["event_at"], utc=True, format="mixed")
    if frame["feature_valid"].dtype != bool:
        frame["feature_valid"] = frame["feature_valid"].map(
            {"True": True, "False": False, "true": True, "false": False}
        )
    folds = build_walk_forward_folds(
        frame, holdout_count=holdout_count
    )
    baseline_template = RobustBaseline()
    report = run_backtest(frame, baseline_template, folds)
    frozen_train = frame.loc[
        frame["cycle_id"].isin(folds[-1].train_cycle_ids)
    ].copy()
    frozen_pipeline = RobustBaseline(baseline_template.config).fit(frozen_train)
    from twinops.ml.artifacts import save_artifact_bundle

    save_artifact_bundle(
        output_path,
        frozen_pipeline,
        {
            "dataset": {
                "kind": "curated_feature_csv",
                "filename": source.name,
                "sha256": f"sha256:{sha256(source.read_bytes()).hexdigest()}",
                "rows": len(frame),
                "cycleCount": int(frame["cycle_id"].nunique()),
            },
            "holdoutCount": holdout_count,
            "baseline": asdict(baseline_template.config),
            "features": asdict(feature_config),
            "scorer": asdict(scorer_config),
        },
        report,
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Chronological TwinOps backtest from a curated feature CSV."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--holdout-count", type=int, default=2)
    args = parser.parse_args(argv)
    run_backtest_csv(args.input, args.output, holdout_count=args.holdout_count)
    from twinops.ml.artifacts import compute_file_hash

    print(
        "Pin these hashes outside the artifact directory before loading:\n"
        f"expected_manifest_hash={compute_file_hash(args.output / 'feature-manifest.json')}\n"
        f"expected_model_hash={compute_file_hash(args.output / 'pipeline.joblib')}"
    )
    return 0


def _episode_count(group: pd.DataFrame, status: str) -> int:
    return int(group.loc[group["status"].eq(status), "episode_id"].dropna().nunique())


def _steady_alert_seconds(group: pd.DataFrame) -> float:
    ordered = group.sort_values("event_at").reset_index(drop=True)
    if len(ordered) < 2:
        return 0.0
    total = 0.0
    for index in range(1, len(ordered)):
        previous = ordered.iloc[index - 1]
        current = ordered.iloc[index]
        if not (
            previous.operating_state == "steady"
            and current.operating_state == "steady"
            and previous.status == "alert"
            and current.status == "alert"
        ):
            continue
        flags = current.get("quality_flags", ())
        if isinstance(flags, str):
            flags = (flags,)
        if any("gap" in str(flag).lower() for flag in flags):
            continue
        cadence = current.get("cadence_seconds")
        if cadence is None or not np.isfinite(float(cadence)) or float(cadence) <= 0:
            continue
        actual_delta = (
            pd.Timestamp(current.event_at) - pd.Timestamp(previous.event_at)
        ).total_seconds()
        cadence = float(cadence)
        if 0.5 * cadence <= actual_delta <= 1.5 * cadence:
            total += cadence
    return total


def _cycle_timeline(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"cycle_id", "event_at"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"cycle frame is missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("cycle frame cannot be empty")
    normalized = frame.loc[:, ["cycle_id", "event_at"]].copy()
    normalized["event_at"] = pd.to_datetime(normalized["event_at"], utc=True)
    if normalized["event_at"].isna().any():
        raise ValueError("cycle event_at values must be valid timestamps")
    timeline = normalized.groupby("cycle_id")["event_at"].agg(start="min", end="max")
    timeline.index = timeline.index.map(int)
    timeline = timeline.sort_values(["start", "end"], kind="stable")
    chronological_ids = tuple(int(value) for value in timeline.index)
    if chronological_ids != tuple(sorted(chronological_ids)):
        raise ValueError("cycle IDs contradict event_at chronology")
    previous_end: pd.Timestamp | None = None
    for row in timeline.itertuples():
        if previous_end is not None and previous_end >= row.start:
            raise ValueError("cycle event_at ranges overlap or are not strictly chronological")
        previous_end = row.end
    return timeline


if __name__ == "__main__":
    raise SystemExit(main())
