"""Chronological cycle-grouped walk-forward evaluation."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from twinops.ml.baseline import RobustBaseline


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


def build_walk_forward_folds(
    cycles: Iterable[int], *, holdout_count: int = 2
) -> list[WalkForwardFold]:
    cycle_ids = tuple(sorted({int(value) for value in cycles}))
    if holdout_count < 1:
        raise ValueError("holdout_count must be positive")
    if len(cycle_ids) < holdout_count + 3:
        raise ValueError("walk-forward requires two seed cycles, development, and holdout")
    holdout_start = len(cycle_ids) - holdout_count
    folds = [
        WalkForwardFold(
            train_cycle_ids=cycle_ids[:test_index],
            test_cycle_ids=(cycle_ids[test_index],),
        )
        for test_index in range(2, holdout_start)
    ]
    folds.append(
        WalkForwardFold(
            train_cycle_ids=cycle_ids[:holdout_start],
            test_cycle_ids=cycle_ids[holdout_start:],
            frozen_holdout=True,
        )
    )
    return folds


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
) -> BacktestReport:
    """Run the frozen pipeline from an already curated feature CSV."""

    source = Path(input_path)
    frame = pd.read_csv(source)
    frame["event_at"] = pd.to_datetime(frame["event_at"], utc=True)
    if frame["feature_valid"].dtype != bool:
        frame["feature_valid"] = frame["feature_valid"].map(
            {"True": True, "False": False, "true": True, "false": False}
        )
    folds = build_walk_forward_folds(
        frame["cycle_id"].unique(), holdout_count=holdout_count
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
    return 0


def _episode_count(group: pd.DataFrame, status: str) -> int:
    return int(group.loc[group["status"].eq(status), "episode_id"].dropna().nunique())


def _steady_alert_seconds(group: pd.DataFrame) -> float:
    steady = group.loc[
        group["operating_state"].eq("steady") & group["status"].eq("alert")
    ].sort_values("event_at")
    if len(steady) < 2:
        return 0.0
    times = pd.to_datetime(steady["event_at"], utc=True).array.asi8 / 1_000_000_000
    return float(np.diff(times).sum())


if __name__ == "__main__":
    raise SystemExit(main())
