"""Run the public bearing-fault laboratory without touching operational ML."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from twinops.research.contracts import SignalWindow
from twinops.research.datasets.ims import iter_ims
from twinops.research.datasets.xjtu import iter_xjtu
from twinops.research.downloads import verify_archive
from twinops.research.experiments import run_ablation
from twinops.research.splits import GroupedSplit, grouped_splits


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_IDS = {"xjtu": "xjtu-sy", "ims": "nasa-ims"}
ADAPTERS = {"xjtu": iter_xjtu, "ims": iter_ims}


class ExternalDataGate(RuntimeError):
    """Raised when approved, hash-pinned original data is not locally ready."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _assert_research_output(output: Path) -> None:
    resolved = output.resolve(strict=False)
    operational = (REPOSITORY_ROOT / "artifacts" / "ml" / "real-forzy").resolve(strict=False)
    if resolved == operational or _within(resolved, operational):
        raise ValueError(f"research output must not target operational artifact directory {operational}")
    if resolved.exists():
        forbidden = [
            path
            for path in resolved.rglob("*")
            if path.is_file() and (path.suffix.lower() in {".joblib", ".pkl"} or "real-forzy" in path.parts)
        ]
        if forbidden:
            raise ValueError(f"research output contains an operational/model artifact: {forbidden[0]}")


def _load_sources(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not path.is_file():
        raise FileNotFoundError(f"source manifest does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("source manifest must contain a sources array")
    indexed: dict[str, dict[str, Any]] = {}
    required = {
        "datasetId",
        "landingPage",
        "downloadUrl",
        "citation",
        "license",
        "expectedSha256",
        "accessedAt",
    }
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("each source manifest entry must be an object")
        missing = required - set(source)
        if missing:
            raise ValueError(f"source entry is missing required fields: {sorted(missing)}")
        dataset_id = source["datasetId"]
        if not isinstance(dataset_id, str) or not dataset_id:
            raise ValueError("source datasetId must be a non-empty string")
        if dataset_id in indexed:
            raise ValueError(f"duplicate source entry for {dataset_id}")
        indexed[dataset_id] = source
    return payload, indexed


def _source_issues(
    dataset_aliases: list[str], sources: dict[str, dict[str, Any]], data_root: Path
) -> tuple[list[str], dict[str, str]]:
    issues: list[str] = []
    verified: dict[str, str] = {}
    data_root_resolved = data_root.resolve(strict=False)
    for alias in dataset_aliases:
        dataset_id = DATASET_IDS[alias]
        source = sources.get(dataset_id)
        if source is None:
            issues.append(f"{dataset_id}: source manifest entry is missing")
            continue
        for field in ("downloadUrl", "expectedSha256", "accessedAt", "archivePath"):
            if not source.get(field):
                issues.append(f"{dataset_id}: {field} is pending an approved official-source download")
        archive_path_value = source.get("archivePath")
        expected_hash = source.get("expectedSha256")
        if archive_path_value and expected_hash:
            archive = (data_root / str(archive_path_value)).resolve(strict=False)
            if not _within(archive, data_root_resolved):
                issues.append(f"{dataset_id}: archivePath escapes data/public")
            else:
                try:
                    verified[dataset_id] = verify_archive(archive, str(expected_hash))
                except (FileNotFoundError, ValueError) as exc:
                    issues.append(f"{dataset_id}: {exc}")
        raw_root = data_root / dataset_id / "raw"
        if not raw_root.is_dir():
            issues.append(f"{dataset_id}: extracted raw directory is missing: {raw_root}")
        elif not (raw_root / "metadata.json").is_file():
            issues.append(f"{dataset_id}: curated adapter metadata.json is missing from raw directory")
    return issues, verified


def _load_windows(dataset_aliases: list[str], data_root: Path) -> dict[str, tuple[SignalWindow, ...]]:
    windows: dict[str, tuple[SignalWindow, ...]] = {}
    for alias in dataset_aliases:
        dataset_id = DATASET_IDS[alias]
        loaded = tuple(ADAPTERS[alias](data_root / dataset_id / "raw"))
        if not loaded:
            raise ValueError(f"{dataset_id}: adapter produced no windows")
        windows[dataset_id] = loaded
    return windows


def _assert_disjoint(split: GroupedSplit) -> None:
    train = set(split.train_bearings)
    validation = set(split.validation_bearings)
    test = set(split.test_bearings)
    if train & validation or train & test or validation & test:
        raise ValueError("bearing overlap exists in grouped split")


def _split_manifest(split: GroupedSplit) -> dict[str, Any]:
    return {
        "groupField": split.group_field,
        "seed": split.seed,
        "trainBearings": list(split.train_bearings),
        "validationBearings": list(split.validation_bearings),
        "testBearings": list(split.test_bearings),
        "trainWindows": len(split.train_indices),
        "validationWindows": len(split.validation_indices),
        "testWindows": len(split.test_indices),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run(
    dataset_aliases: list[str],
    *,
    data_root: Path,
    source_manifest: Path,
    output: Path,
    seed: int,
    dry_run: bool,
) -> dict[str, Any]:
    if len(set(dataset_aliases)) < 2:
        raise ValueError("at least two distinct benches are required for cross-bench validation")
    _assert_research_output(output)
    source_payload, sources = _load_sources(source_manifest)
    issues, verified_hashes = _source_issues(dataset_aliases, sources, data_root)
    if dry_run:
        return {
            "status": "not_run_external_data_gate" if issues else "ready",
            "datasets": [DATASET_IDS[alias] for alias in dataset_aliases],
            "issues": issues,
            "output": str(output),
            "writesPerformed": False,
        }
    if issues:
        raise ExternalDataGate("; ".join(issues))

    started = time.perf_counter()
    windows = _load_windows(dataset_aliases, data_root)
    splits: dict[str, GroupedSplit] = {}
    evaluations: dict[str, Any] = {}
    evaluation_times: dict[str, float] = {}
    for dataset_id, dataset_windows in windows.items():
        split = grouped_splits(dataset_windows, seed=seed)
        _assert_disjoint(split)
        splits[dataset_id] = split
        train = tuple(dataset_windows[index] for index in split.train_indices)
        test = tuple(dataset_windows[index] for index in split.test_indices)
        label = f"{dataset_id}:within_bench_holdout"
        evaluation_started = time.perf_counter()
        evaluations[label] = run_ablation(train, test, seed=seed).to_dict()
        evaluation_times[label] = time.perf_counter() - evaluation_started

    dataset_ids = [DATASET_IDS[alias] for alias in dataset_aliases]
    for train_id in dataset_ids:
        for test_id in dataset_ids:
            if train_id == test_id:
                continue
            label = f"{train_id}->{test_id}"
            evaluation_started = time.perf_counter()
            evaluations[label] = run_ablation(windows[train_id], windows[test_id], seed=seed).to_dict()
            evaluation_times[label] = time.perf_counter() - evaluation_started

    elapsed = time.perf_counter() - started
    completed_at = _utc_now()
    ablation_report = {
        "schemaVersion": 1,
        "status": "completed_with_verified_original_data",
        "generatedAt": completed_at,
        "config": {
            "datasets": dataset_ids,
            "seed": seed,
            "views": ["full", "aggregate", "forzy"],
            "bootstrapUnit": "bearing_id",
            "operationalCalibration": False,
        },
        "elapsedSeconds": elapsed,
        "evaluationSeconds": evaluation_times,
        "evaluations": evaluations,
        "operationalImpact": "none; research evidence only",
    }
    dataset_manifest = {
        "schemaVersion": 1,
        "status": "verified_original_data_used",
        "generatedAt": completed_at,
        "sourceManifestSchemaVersion": source_payload.get("schemaVersion"),
        "datasets": {
            dataset_id: {
                "source": sources[dataset_id],
                "verifiedSha256": verified_hashes[dataset_id],
                "windowCount": len(windows[dataset_id]),
                "bearingCount": len({window.bearing_id for window in windows[dataset_id]}),
                "split": _split_manifest(splits[dataset_id]),
            }
            for dataset_id in dataset_ids
        },
    }

    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "ablation-report.json", ablation_report)
    _write_json(output / "dataset-manifest.json", dataset_manifest)
    return {
        "status": "completed_with_verified_original_data",
        "output": str(output),
        "elapsedSeconds": elapsed,
        "evaluations": sorted(evaluations),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", choices=sorted(DATASET_IDS), required=True)
    parser.add_argument("--data-root", type=Path, default=REPOSITORY_ROOT / "data" / "public")
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "public" / "sources.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(
            args.datasets,
            data_root=args.data_root,
            source_manifest=args.source_manifest,
            output=args.output,
            seed=args.seed,
            dry_run=args.dry_run,
        )
    except ExternalDataGate as exc:
        print(
            json.dumps({"status": "not_run_external_data_gate", "error": str(exc)}, indent=2),
            file=sys.stderr,
        )
        return 3
    except Exception as exc:
        print(
            json.dumps({"status": "failed_precondition", "error": str(exc)}, indent=2),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
