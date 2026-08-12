"""Versioned, hash-verified artifact bundles for the classical ML pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import joblib

from twinops.ml.baseline import RobustBaseline


class ArtifactIntegrityError(ValueError):
    """Raised when a versioned artifact does not match its manifest hash."""


@dataclass(frozen=True)
class ArtifactBundle:
    pipeline: RobustBaseline
    config: dict[str, Any]
    report: dict[str, Any]
    manifest: dict[str, Any]


def save_artifact_bundle(
    path: str | Path,
    pipeline: RobustBaseline,
    config: object,
    report: object,
) -> dict[str, Any]:
    """Serialize a fitted pipeline and write a hash manifest last."""

    if not pipeline.is_fitted:
        raise ValueError("only fitted pipelines can be serialized")
    destination = Path(path)
    destination.mkdir(parents=True, exist_ok=True)
    config_payload = _json_payload(config)
    report_payload = _json_payload(report)

    pipeline_path = destination / "pipeline.joblib"
    config_path = destination / "pipeline-config.json"
    report_path = destination / "backtest-report.json"
    model_card_path = destination / "model-card.md"
    joblib.dump(pipeline, pipeline_path)
    _write_json(config_path, config_payload)
    _write_json(report_path, report_payload)
    model_card_path.write_text(
        _model_card(pipeline, config_payload, report_payload), encoding="utf-8"
    )

    files = {
        file_path.name: _file_hash(file_path)
        for file_path in (pipeline_path, config_path, report_path, model_card_path)
    }
    manifest: dict[str, Any] = {
        "schemaVersion": "1.0",
        "model": {
            "name": pipeline.model_name,
            "version": pipeline.model_version,
            "configHash": pipeline.config_hash,
        },
        "scoreSemantics": "relative_to_historical_baseline_not_failure_probability",
        "features": [
            {
                "name": "velocity_ewma",
                "unit": "mm/s",
                "causality": "trailing_only",
            },
            {
                "name": "velocity_slope",
                "unit": "mm/s/s",
                "causality": "trailing_only",
            },
            {
                "name": "velocity_change_point",
                "unit": "mm/s",
                "causality": "trailing_only",
            },
            {
                "name": "temperature_deviation",
                "unit": "degC",
                "causality": "trailing_only_phase_separated",
            },
        ],
        "officialScoreExclusions": [
            "vibration_acceleration_statistic_unknown",
            "physical_s1_s2_difference_unconfirmed",
        ],
        "files": files,
    }
    _write_json(destination / "feature-manifest.json", manifest)
    return manifest


def load_artifact_bundle(path: str | Path) -> ArtifactBundle:
    """Verify every declared file before deserializing the pipeline."""

    source = Path(path)
    manifest_path = source / "feature-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != "1.0":
        raise ArtifactIntegrityError("unsupported feature manifest schema version")
    declared = manifest.get("files")
    if not isinstance(declared, dict):
        raise ArtifactIntegrityError("feature manifest does not declare files")
    for filename, expected_hash in declared.items():
        if Path(filename).name != filename:
            raise ArtifactIntegrityError(f"unsafe artifact filename: {filename}")
        file_path = source / filename
        if not file_path.is_file() or _file_hash(file_path) != expected_hash:
            raise ArtifactIntegrityError(f"artifact hash mismatch: {filename}")

    pipeline = joblib.load(source / "pipeline.joblib")
    if not isinstance(pipeline, RobustBaseline):
        raise ArtifactIntegrityError("pipeline artifact has an unexpected type")
    config = json.loads((source / "pipeline-config.json").read_text(encoding="utf-8"))
    report = json.loads((source / "backtest-report.json").read_text(encoding="utf-8"))
    return ArtifactBundle(
        pipeline=pipeline,
        config=config,
        report=report,
        manifest=manifest,
    )


def _json_payload(value: object) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    elif is_dataclass(value):
        value = asdict(value)
    encoded = json.dumps(value, sort_keys=True, allow_nan=False)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise TypeError("artifact config and report must serialize to JSON objects")
    return decoded


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _model_card(
    pipeline: RobustBaseline,
    config: dict[str, Any],
    report: dict[str, Any],
) -> str:
    trained_until = pipeline.trained_until_.isoformat() if pipeline.trained_until_ else "unknown"
    dataset_kind = config.get("dataset", {}).get("kind", "unspecified")
    report_status = report.get("status", "completed")
    return f"""# Model card - {pipeline.model_name} {pipeline.model_version}

## Intended use

Relative anomaly and deterioration scoring against a historical steady-regime
baseline. Scores are not failure probabilities and do not diagnose components.

## Training evidence

- Dataset kind: `{dataset_kind}`
- Trained until: `{trained_until}`
- Report status: `{report_status}`
- Config hash: `{pipeline.config_hash}`

## Limitations

- Acceleration is excluded while its statistic remains unknown.
- S1-S2 physical differences are excluded until mounting and axis are confirmed.
- Operating phases are estimated from vibration velocity RMS.
- No deep learning, RUL, automatic online learning, or failure classification.
- Human validation remains required before operational action.
"""

