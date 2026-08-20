"""Run the provenance-gated public bearing-fault laboratory."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from twinops.research.contracts import FeaturePolicy, LabelMappingPolicy, SignalWindow
from twinops.research.datasets.ims import iter_ims
from twinops.research.datasets.xjtu import iter_xjtu
from twinops.research.downloads import (
    RawInventory,
    hash_file,
    inspect_archive,
    safe_extract_archive,
    verify_archive,
)
from twinops.research.experiments import AblationReport, run_ablation
from twinops.research.metadata import LoadedMetadata, load_metadata
from twinops.research.splits import GroupedSplit, grouped_splits


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_IDS = {"xjtu": "xjtu-sy", "ims": "nasa-ims"}
ADAPTERS = {"xjtu": iter_xjtu, "ims": iter_ims}
_OUTPUT_FILES = {"ablation-report.json", "dataset-manifest.json"}


class ExternalDataGate(RuntimeError):
    """Raised when approved, hash-pinned original data is not locally ready."""


@dataclass(frozen=True, slots=True)
class PreparedSource:
    alias: str
    dataset_id: str
    source: dict[str, Any]
    archive_path: Path
    archive_sha256: str
    raw_path: Path
    inspected_inventory: RawInventory
    metadata_path: Path
    metadata: LoadedMetadata


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    config_id: str
    config_sha256: str
    feature_policy: FeaturePolicy
    label_policy: LabelMappingPolicy
    bootstrap_samples: int
    raw: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _absolute_https(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty HTTPS URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{field} must be an absolute HTTPS URL")
    return value


def _rfc3339(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return value


def _data_path(data_root: Path, value: object, *, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty path relative to data root")
    if "\\" in value or value.startswith("/") or ":" in value:
        raise ValueError(f"{field} must be a normalized relative POSIX path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{field} must be a normalized relative POSIX path")
    resolved_root = data_root.resolve(strict=False)
    resolved = data_root.joinpath(*parts).resolve(strict=False)
    if not _within(resolved, resolved_root):
        raise ValueError(f"{field} escapes data root")
    return resolved


def _assert_operational_boundary(output: Path) -> None:
    resolved = output.resolve(strict=False)
    operational_roots = (
        (REPOSITORY_ROOT / "artifacts" / "ml" / "real-forzy").resolve(strict=False),
        (
            REPOSITORY_ROOT / "services" / "twinops" / "src" / "twinops" / "ml"
        ).resolve(strict=False),
    )
    for operational in operational_roots:
        if (
            resolved == operational
            or _within(resolved, operational)
            or _within(operational, resolved)
        ):
            raise ValueError(
                f"research output must not overlap operational tree {operational}"
            )
    if resolved.exists() and resolved.is_dir():
        forbidden = [
            path
            for path in resolved.rglob("*")
            if path.is_file()
            and (path.suffix.lower() in {".joblib", ".pkl"} or "real-forzy" in path.parts)
        ]
        if forbidden:
            raise ValueError(f"research output contains an operational/model artifact: {forbidden[0]}")


def _prepare_output(output: Path, *, overwrite: bool) -> None:
    _assert_operational_boundary(output)
    if output.exists() and not output.is_dir():
        raise ValueError(f"research output must be a directory: {output}")
    existing = set()
    if output.exists():
        existing = {path.name for path in output.iterdir()}
    if existing and not overwrite:
        raise ValueError("research output is not empty; pass --overwrite explicitly")
    unknown = existing - _OUTPUT_FILES
    if unknown:
        raise ValueError(f"research output contains unknown files that cannot be overwritten: {sorted(unknown)}")
    output.mkdir(parents=True, exist_ok=True)


def _load_sources(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not path.is_file():
        raise FileNotFoundError(f"source manifest does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 2:
        raise ValueError("source manifest schemaVersion must be 2")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("source manifest must contain a sources array")
    required = {
        "datasetId",
        "status",
        "landingPage",
        "downloadUrl",
        "citation",
        "license",
        "expectedSha256",
        "archivePath",
        "rawPath",
        "metadataPath",
        "expectedMetadataSha256",
        "accessedAt",
    }
    indexed: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("each source manifest entry must be an object")
        missing = required - set(source)
        if missing:
            raise ValueError(f"source entry is missing required fields: {sorted(missing)}")
        dataset_id = source.get("datasetId")
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise ValueError("source datasetId must be a non-empty string")
        if dataset_id in indexed:
            raise ValueError(f"duplicate source entry for {dataset_id}")
        indexed[dataset_id] = source
    return payload, indexed


def _experiment_config(payload: dict[str, Any]) -> ExperimentConfig:
    raw = payload.get("experimentConfig")
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
        raise ValueError("experimentConfig schemaVersion must be 1")
    config_id = raw.get("configId")
    if not isinstance(config_id, str) or not config_id.strip():
        raise ValueError("experimentConfig configId must be a non-empty string")
    feature = raw.get("featurePolicy")
    if not isinstance(feature, dict):
        raise ValueError("experimentConfig featurePolicy must be an object")
    label = raw.get("labelMapping")
    if not isinstance(label, dict) or not isinstance(label.get("mapping"), dict):
        raise ValueError("experimentConfig labelMapping must contain a mapping")
    samples = raw.get("bootstrapSamples")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 20:
        raise ValueError("experimentConfig bootstrapSamples must be an integer >= 20")
    policy = FeaturePolicy(
        policy_id=feature.get("policyId"),
        selected_acceleration_axis=feature.get("selectedAccelerationAxis"),
        acceleration_rms_semantics_confirmed=feature.get("accelerationRmsSemanticsConfirmed"),
        temperature_semantics_confirmed=feature.get("temperatureSemanticsConfirmed"),
        evidence=feature.get("evidence"),
    )
    label_policy = LabelMappingPolicy(
        version=label.get("version"), mapping=label["mapping"]
    )
    return ExperimentConfig(
        config_id=config_id.strip(),
        config_sha256=_canonical_sha256(raw),
        feature_policy=policy,
        label_policy=label_policy,
        bootstrap_samples=samples,
        raw=raw,
    )


def _source_validation(
    dataset_aliases: list[str], sources: dict[str, dict[str, Any]], data_root: Path
) -> tuple[list[str], dict[str, PreparedSource]]:
    issues: list[str] = []
    prepared: dict[str, PreparedSource] = {}
    for alias in dataset_aliases:
        dataset_id = DATASET_IDS[alias]
        source = sources.get(dataset_id)
        if source is None:
            issues.append(f"{dataset_id}: source manifest entry is missing")
            continue
        source_issues: list[str] = []
        if source.get("status") != "approved_for_research":
            source_issues.append(f"status must be approved_for_research, got {source.get('status')!r}")
        for field in ("citation", "license"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                source_issues.append(f"{field} must be a non-empty string")
        for field in ("landingPage", "downloadUrl"):
            try:
                _absolute_https(source.get(field), field=field)
            except ValueError as exc:
                source_issues.append(str(exc))
        try:
            _rfc3339(source.get("accessedAt"), field="accessedAt")
        except ValueError as exc:
            source_issues.append(str(exc))

        archive_path = metadata_path = raw_path = None
        for field, target in (
            ("archivePath", "archive"),
            ("metadataPath", "metadata"),
            ("rawPath", "raw"),
        ):
            try:
                resolved = _data_path(data_root, source.get(field), field=field)
                if target == "archive":
                    archive_path = resolved
                elif target == "metadata":
                    metadata_path = resolved
                else:
                    raw_path = resolved
            except ValueError as exc:
                source_issues.append(str(exc))

        archive_hash = None
        inventory = None
        metadata = None
        expected_archive = source.get("expectedSha256")
        if archive_path is not None:
            try:
                archive_hash = verify_archive(archive_path, expected_archive)
                inventory = inspect_archive(archive_path)
            except (FileNotFoundError, ValueError, TypeError) as exc:
                source_issues.append(str(exc))
        if metadata_path is not None and inventory is not None:
            try:
                metadata = load_metadata(
                    metadata_path,
                    expected_sha256=source.get("expectedMetadataSha256"),
                    dataset_id=dataset_id,
                    raw_inventory=inventory,
                )
            except (FileNotFoundError, ValueError, TypeError) as exc:
                source_issues.append(str(exc))
        if raw_path is not None and raw_path.exists() and (
            not raw_path.is_dir() or any(raw_path.iterdir())
        ):
            source_issues.append(f"rawPath extraction destination must be empty: {raw_path}")
        if source_issues:
            issues.extend(f"{dataset_id}: {issue}" for issue in source_issues)
            continue
        if not all(
            value is not None
            for value in (archive_path, archive_hash, inventory, metadata_path, metadata, raw_path)
        ):
            issues.append(f"{dataset_id}: source preparation is incomplete")
            continue
        prepared[dataset_id] = PreparedSource(
            alias=alias,
            dataset_id=dataset_id,
            source=source,
            archive_path=archive_path,
            archive_sha256=archive_hash,
            raw_path=raw_path,
            inspected_inventory=inventory,
            metadata_path=metadata_path,
            metadata=metadata,
        )
    return issues, prepared


def _load_windows(
    prepared: dict[str, PreparedSource]
) -> tuple[dict[str, tuple[SignalWindow, ...]], dict[str, RawInventory]]:
    windows: dict[str, tuple[SignalWindow, ...]] = {}
    inventories: dict[str, RawInventory] = {}
    for dataset_id, source in prepared.items():
        extracted = safe_extract_archive(
            source.archive_path,
            source.raw_path,
            expected_sha256=source.archive_sha256,
        )
        if extracted.inventory_sha256 != source.inspected_inventory.inventory_sha256:
            raise ValueError(f"{dataset_id}: extraction inventory changed after source validation")
        loaded = tuple(ADAPTERS[source.alias](source.raw_path, source.metadata))
        if not loaded:
            raise ValueError(f"{dataset_id}: adapter produced no windows")
        windows[dataset_id] = loaded
        inventories[dataset_id] = extracted
    return windows, inventories


def _mapped_split_rows(
    windows: tuple[SignalWindow, ...], policy: LabelMappingPolicy
) -> tuple[tuple[SignalWindow, ...], list[dict[str, str]]]:
    included: list[SignalWindow] = []
    rows: list[dict[str, str]] = []
    for window in windows:
        label = window.window_state_label
        if label not in policy.mapping:
            raise ValueError(f"split: unexpected label {label!r} is absent from mapping {policy.version}")
        target = policy.mapping[label]
        if target is None:
            continue
        included.append(window)
        rows.append({"bearing_id": window.bearing_id, "window_state_label": target})
    return tuple(included), rows


def _split_manifest(split: GroupedSplit) -> dict[str, Any]:
    return {
        "strategy": split.strategy,
        "groupField": split.group_field,
        "labelField": split.label_field,
        "seed": split.seed,
        "trainBearings": list(split.train_bearings),
        "testBearings": list(split.test_bearings),
        "trainWindows": len(split.train_indices),
        "testWindows": len(split.test_indices),
        "trainClassCounts": dict(split.train_class_counts),
        "testClassCounts": dict(split.test_class_counts),
        "limitations": list(split.limitations),
    }


def _cross_summary(report: AblationReport) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for metric in ("macro_f1", "balanced_accuracy"):
        full = float(getattr(report.views["full"].diagnostic, metric))
        aggregate = float(getattr(report.views["aggregate"].diagnostic, metric))
        forzy = float(getattr(report.views["forzy"].diagnostic, metric))
        baseline = float(getattr(report.views["forzy"].diagnostic.majority_baseline, metric))
        if forzy > baseline:
            verdict = "above_majority_baseline"
        elif forzy < baseline:
            verdict = "below_majority_baseline"
        else:
            verdict = "equal_to_majority_baseline"
        metrics[metric] = {
            "full": full,
            "aggregate": aggregate,
            "forzy": forzy,
            "majorityBaseline": baseline,
            "fullToAggregateDelta": aggregate - full,
            "aggregateToForzyDelta": forzy - aggregate,
            "fullToForzyDelta": forzy - full,
            "forzyVerdict": verdict,
        }
    return {
        "status": "valid_cross_bench",
        "trainDatasetId": report.train_dataset_id,
        "testDatasetId": report.test_dataset_id,
        "labelMappingVersion": report.label_mapping_version,
        "featurePolicyId": report.feature_policy_id,
        "trainCoverage": asdict(report.train_coverage),
        "testCoverage": asdict(report.test_coverage),
        "metrics": metrics,
    }


def _code_sha256() -> str:
    paths = sorted(
        [
            *(
                REPOSITORY_ROOT / "services" / "twinops" / "src" / "twinops" / "research"
            ).rglob("*.py"),
            Path(__file__).resolve(),
        ],
        key=lambda path: path.as_posix(),
    )
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(REPOSITORY_ROOT).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _git_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _dependency_versions() -> dict[str, str]:
    return {
        name: importlib.metadata.version(distribution)
        for name, distribution in (
            ("numpy", "numpy"),
            ("pandas", "pandas"),
            ("scipy", "scipy"),
            ("scikitLearn", "scikit-learn"),
        )
    }


def _stage_json(output: Path, name: str, payload: dict[str, Any]) -> Path:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return _stage_bytes(output, name, encoded)


def _stage_bytes(output: Path, name: str, payload: bytes) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=output)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException as exc:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException as cleanup_exc:
            exc.add_note(f"temporary report cleanup failed: {cleanup_exc!r}")
        raise
    return temporary


def _bind_report_pair(
    ablation_report: dict[str, Any], dataset_manifest: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    documents = {
        "ablation-report.json": dict(ablation_report),
        "dataset-manifest.json": dict(dataset_manifest),
    }
    for document in documents.values():
        document.pop("publication", None)
    hashes = {name: _canonical_sha256(document) for name, document in documents.items()}
    publication = {
        "schemaVersion": 1,
        "generationId": _canonical_sha256(
            {"schemaVersion": 1, "documents": hashes}
        ),
        "documents": hashes,
    }
    return {
        name: {**document, "publication": publication}
        for name, document in documents.items()
    }


def _verify_published_report_pair(output: Path) -> None:
    try:
        documents = {
            name: json.loads((output / name).read_text(encoding="utf-8"))
            for name in _OUTPUT_FILES
        }
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"published report pair cannot be read: {exc}") from exc
    if any(not isinstance(document, dict) for document in documents.values()):
        raise ValueError("published report pair must contain two JSON objects")
    publications = [document.get("publication") for document in documents.values()]
    publication = publications[0]
    if (
        not isinstance(publication, dict)
        or any(candidate != publication for candidate in publications[1:])
        or publication.get("schemaVersion") != 1
    ):
        raise ValueError("published report pair has incompatible publication metadata")
    unbound = {}
    for name, document in documents.items():
        payload = dict(document)
        payload.pop("publication", None)
        unbound[name] = payload
    hashes = {name: _canonical_sha256(payload) for name, payload in unbound.items()}
    if publication.get("documents") != hashes:
        raise ValueError("published report pair document hashes do not match")
    generation_id = _canonical_sha256({"schemaVersion": 1, "documents": hashes})
    if publication.get("generationId") != generation_id:
        raise ValueError("published report pair generationId does not match")


def _rollback_report_pair(
    output: Path, previous: dict[str, bytes | None]
) -> list[BaseException]:
    rollback_staged: dict[str, Path] = {}
    errors: list[BaseException] = []
    try:
        for name, payload in previous.items():
            if payload is not None:
                rollback_staged[name] = _stage_bytes(output, f"rollback-{name}", payload)
        for name in sorted(_OUTPUT_FILES):
            payload = previous[name]
            if payload is None:
                (output / name).unlink(missing_ok=True)
            else:
                os.replace(rollback_staged[name], output / name)
    except BaseException as exc:
        errors.append(exc)
        for name in _OUTPUT_FILES:
            try:
                (output / name).unlink(missing_ok=True)
            except BaseException as cleanup_exc:
                errors.append(cleanup_exc)
    finally:
        for temporary in rollback_staged.values():
            try:
                temporary.unlink(missing_ok=True)
            except BaseException as cleanup_exc:
                errors.append(cleanup_exc)
    return errors


def _atomic_reports(
    output: Path, ablation_report: dict[str, Any], dataset_manifest: dict[str, Any]
) -> None:
    existing = {name for name in _OUTPUT_FILES if (output / name).exists()}
    if existing and existing != _OUTPUT_FILES:
        raise ValueError("existing research output contains an incomplete report pair")
    previous = {
        name: (output / name).read_bytes() if name in existing else None
        for name in _OUTPUT_FILES
    }
    documents = _bind_report_pair(ablation_report, dataset_manifest)
    staged: dict[str, Path] = {}
    active_error: BaseException | None = None
    publication_attempted = False
    try:
        for name, document in documents.items():
            staged[name] = _stage_json(output, name, document)
        for name in sorted(staged):
            publication_attempted = True
            os.replace(staged[name], output / name)
        _verify_published_report_pair(output)
    except BaseException as exc:
        active_error = exc
        if publication_attempted:
            rollback_errors = _rollback_report_pair(output, previous)
            for rollback_error in rollback_errors:
                exc.add_note(f"report pair rollback incomplete: {rollback_error!r}")
        raise
    finally:
        for temporary in staged.values():
            try:
                temporary.unlink(missing_ok=True)
            except BaseException as cleanup_exc:
                if active_error is not None:
                    active_error.add_note(f"staged report cleanup failed: {cleanup_exc!r}")
                else:
                    raise


def _run(
    dataset_aliases: list[str],
    *,
    data_root: Path,
    source_manifest: Path,
    output: Path,
    seed: int,
    dry_run: bool,
    overwrite: bool,
) -> dict[str, Any]:
    if len(dataset_aliases) != 2 or set(dataset_aliases) != set(DATASET_IDS):
        raise ValueError(
            "exactly the two distinct supported benches (xjtu and ims) are required"
        )
    _assert_operational_boundary(output)
    source_payload, sources = _load_sources(source_manifest)
    config = _experiment_config(source_payload)
    issues, prepared = _source_validation(dataset_aliases, sources, data_root)
    if not (
        config.feature_policy.acceleration_rms_semantics_confirmed
        or config.feature_policy.temperature_semantics_confirmed
    ):
        issues.insert(
            0,
            "experimentConfig featurePolicy confirms no Forzy-compatible measurement "
            "semantics; supply an explicit audited policy",
        )
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
    _prepare_output(output, overwrite=overwrite)

    started = time.perf_counter()
    windows, inventories = _load_windows(prepared)
    splits: dict[str, GroupedSplit] = {}
    evaluations: dict[str, Any] = {}
    evaluation_times: dict[str, float] = {}
    dataset_ids = [DATASET_IDS[alias] for alias in dataset_aliases]
    for dataset_id in dataset_ids:
        split_windows, split_rows = _mapped_split_rows(
            windows[dataset_id], config.label_policy
        )
        split = grouped_splits(split_rows, seed=seed)
        splits[dataset_id] = split
        train = tuple(split_windows[index] for index in split.train_indices)
        test = tuple(split_windows[index] for index in split.test_indices)
        label = f"{dataset_id}:within_bench_holdout"
        evaluation_started = time.perf_counter()
        evaluations[label] = run_ablation(
            train,
            test,
            feature_policy=config.feature_policy,
            label_policy=config.label_policy,
            seed=seed,
            bootstrap_samples=config.bootstrap_samples,
        ).to_dict()
        evaluation_times[label] = time.perf_counter() - evaluation_started

    cross_summaries: dict[str, Any] = {}
    for train_id, test_id in ((dataset_ids[0], dataset_ids[1]), (dataset_ids[1], dataset_ids[0])):
        label = f"{train_id}->{test_id}"
        evaluation_started = time.perf_counter()
        report = run_ablation(
            windows[train_id],
            windows[test_id],
            feature_policy=config.feature_policy,
            label_policy=config.label_policy,
            seed=seed,
            bootstrap_samples=config.bootstrap_samples,
        )
        evaluations[label] = report.to_dict()
        cross_summaries[label] = _cross_summary(report)
        evaluation_times[label] = time.perf_counter() - evaluation_started
    expected_directions = {f"{dataset_ids[0]}->{dataset_ids[1]}", f"{dataset_ids[1]}->{dataset_ids[0]}"}
    if set(cross_summaries) != expected_directions or any(
        summary.get("status") != "valid_cross_bench" for summary in cross_summaries.values()
    ):
        raise ValueError("both cross-bench directions must be valid before completion")

    elapsed = time.perf_counter() - started
    completed_at = _utc_now()
    effective_config = {
        "datasets": dataset_ids,
        "seed": seed,
        "views": ["full", "aggregate", "forzy"],
        "bootstrapUnit": "bearing_id",
        "bootstrapSamples": config.bootstrap_samples,
        "featurePolicy": config.raw["featurePolicy"],
        "labelMapping": config.raw["labelMapping"],
        "operationalCalibration": False,
    }
    reproduction = {
        "codeSha256": _code_sha256(),
        "gitCommit": _git_commit(),
        "sourceManifestSha256": hash_file(source_manifest),
        "experimentConfigId": config.config_id,
        "experimentConfigSha256": config.config_sha256,
        "effectiveConfigSha256": _canonical_sha256(effective_config),
        "dependencyVersions": _dependency_versions(),
    }
    ablation_report = {
        "schemaVersion": 2,
        "status": "completed_with_verified_sources",
        "generatedAt": completed_at,
        "config": effective_config,
        "reproduction": reproduction,
        "elapsedSeconds": elapsed,
        "evaluationSeconds": evaluation_times,
        "evaluations": evaluations,
        "crossBenchSummary": cross_summaries,
        "operationalImpact": "none; research evidence only",
    }
    dataset_manifest = {
        "schemaVersion": 2,
        "status": "verified_sources_used",
        "generatedAt": completed_at,
        "reproduction": reproduction,
        "datasets": {
            dataset_id: {
                "source": {
                    "landingPage": prepared[dataset_id].source["landingPage"],
                    "downloadUrl": prepared[dataset_id].source["downloadUrl"],
                    "accessedAt": prepared[dataset_id].source["accessedAt"],
                    "citation": prepared[dataset_id].source["citation"],
                    "license": prepared[dataset_id].source["license"],
                    "archivePath": prepared[dataset_id].source["archivePath"],
                    "archiveSha256": prepared[dataset_id].archive_sha256,
                },
                "rawInventory": inventories[dataset_id].to_dict(),
                "metadata": {
                    "metadataPath": prepared[dataset_id].source["metadataPath"],
                    "metadataSchemaVersion": prepared[dataset_id].metadata.schema_version,
                    "metadataId": prepared[dataset_id].metadata.metadata_id,
                    "metadataSha256": prepared[dataset_id].metadata.metadata_sha256,
                },
                "windowCount": len(windows[dataset_id]),
                "bearingCount": len({window.bearing_id for window in windows[dataset_id]}),
                "split": _split_manifest(splits[dataset_id]),
            }
            for dataset_id in dataset_ids
        },
    }
    _atomic_reports(output, ablation_report, dataset_manifest)
    return {
        "status": "completed_with_verified_sources",
        "output": str(output),
        "elapsedSeconds": elapsed,
        "crossBenchDirections": sorted(cross_summaries),
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
    parser.add_argument("--overwrite", action="store_true")
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
            overwrite=args.overwrite,
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
