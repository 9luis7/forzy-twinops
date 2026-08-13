"""Reproducible real-data path from native Forzy export to ML backtest."""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from twinops.ingestion.forzy_history import read_forzy_history
from twinops.ml.artifacts import compute_file_hash
from twinops.ml.backtest import BacktestReport, run_backtest_csv
from twinops.ml.curation import curate_samples
from twinops.ml.features import FeatureConfig, compute_trailing_features
from twinops.ml.scorer import ScorerConfig


DEFAULT_FEATURE_CONFIG = FeatureConfig(
    short_window_seconds=10,
    long_window_seconds=60,
    min_points=3,
)


def prepare_forzy_history_features(
    input_path: str | Path,
    *,
    asset_tag: str,
    timezone_name: str,
    received_at: datetime,
    gap_seconds: float = 15.0,
    feature_config: FeatureConfig = DEFAULT_FEATURE_CONFIG,
) -> pd.DataFrame:
    samples = read_forzy_history(
        input_path,
        asset_tag=asset_tag,
        timezone_name=timezone_name,
        received_at=received_at,
    )
    curated = curate_samples(samples, gap_seconds=gap_seconds)
    return compute_trailing_features(curated, feature_config)


def run_forzy_history_backtest(
    input_path: str | Path,
    output_path: str | Path,
    *,
    asset_tag: str,
    timezone_name: str,
    received_at: datetime,
    gap_seconds: float = 15.0,
    holdout_count: int = 2,
) -> BacktestReport:
    source = Path(input_path)
    destination = Path(output_path)
    destination.mkdir(parents=True, exist_ok=True)
    features = prepare_forzy_history_features(
        source,
        asset_tag=asset_tag,
        timezone_name=timezone_name,
        received_at=received_at,
        gap_seconds=gap_seconds,
    )
    feature_path = destination / "curated-features.csv"
    features.to_csv(feature_path, index=False)
    report = run_backtest_csv(
        feature_path,
        destination,
        holdout_count=holdout_count,
        feature_config=DEFAULT_FEATURE_CONFIG,
        scorer_config=ScorerConfig(
            gap_seconds=gap_seconds,
            max_freshness_seconds=30,
        ),
    )
    summary = {
        "schemaVersion": "1.0",
        "sourceFile": source.name,
        "sourceSha256": f"sha256:{sha256(source.read_bytes()).hexdigest()}",
        "sourceDataRows": int(len(features) / 2),
        "canonicalSamples": int(len(features)),
        "sensorRows": {
            str(sensor): int(count)
            for sensor, count in features.groupby("sensor_id").size().items()
        },
        "cycleCount": int(features["cycle_id"].nunique()),
        "validFeatureRows": int(features["feature_valid"].sum()),
        "newInformationRows": int(features["is_new_information"].sum()),
        "consecutiveDuplicateRows": int((~features["is_new_information"]).sum()),
        "observedStartUtc": pd.Timestamp(features["event_at"].min()).isoformat(),
        "observedEndUtc": pd.Timestamp(features["event_at"].max()).isoformat(),
        "sourceTimezoneAssumption": timezone_name,
        "gapSeconds": gap_seconds,
        "scoreSemantics": report.score_semantics,
        "groundTruthLabelsAvailable": False,
    }
    (destination / "source-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the chronological ML backtest from a native Forzy history CSV."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--asset-tag", default="MTR-BMB-042")
    parser.add_argument("--timezone", default="America/Sao_Paulo")
    parser.add_argument("--received-at", required=True)
    parser.add_argument("--gap-seconds", type=float, default=15.0)
    parser.add_argument("--holdout-count", type=int, default=2)
    args = parser.parse_args(argv)
    received_at = datetime.fromisoformat(args.received_at.replace("Z", "+00:00"))
    report = run_forzy_history_backtest(
        args.input,
        args.output,
        asset_tag=args.asset_tag,
        timezone_name=args.timezone,
        received_at=received_at,
        gap_seconds=args.gap_seconds,
        holdout_count=args.holdout_count,
    )
    print(
        json.dumps(
            {
                "folds": len(report.folds),
                "cycleResults": len(report.cycle_results),
                "candidateEvents": len(report.candidate_events),
                "latencyMs": report.latency_ms,
                "holdoutFrozen": report.holdout_frozen,
                "expectedManifestHash": compute_file_hash(
                    args.output / "feature-manifest.json"
                ),
                "expectedModelHash": compute_file_hash(
                    args.output / "pipeline.joblib"
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
