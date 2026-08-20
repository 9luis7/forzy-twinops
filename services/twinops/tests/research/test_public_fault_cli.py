from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPOSITORY_ROOT / "scripts" / "run_public_fault_lab.py"


def _run(*arguments: object) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["LOKY_MAX_CPU_COUNT"] = "1"
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(argument) for argument in arguments)],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def _signal(label: str, bearing_index: int, length: int = 128) -> np.ndarray:
    samples = np.arange(length, dtype=float)
    if label == "normal":
        return 0.2 * np.sin(np.pi * 0.125 * samples) + bearing_index * 1e-4
    return 1.5 * np.sin(np.pi * 0.375 * samples) + bearing_index * 1e-4


def _csv(values: np.ndarray) -> bytes:
    return ("Signal\n" + "\n".join(f"{value:.12f}" for value in values) + "\n").encode()


def _txt(values: np.ndarray) -> bytes:
    return ("\n".join(f"{value:.12f}" for value in values) + "\n").encode()


def _dataset_fixture(data_root: Path, dataset_id: str) -> dict[str, object]:
    dataset_root = data_root / dataset_id
    downloads = dataset_root / "downloads"
    downloads.mkdir(parents=True)
    archive_path = downloads / "synthetic.zip"
    metadata_files: dict[str, object] = {}
    with zipfile.ZipFile(archive_path, "w") as archive:
        for label in ("normal", "outer_race"):
            for bearing_index in range(4):
                bearing_id = f"{dataset_id}-{label}-{bearing_index}"
                values = _signal(label, bearing_index)
                if dataset_id == "xjtu-sy":
                    relative = f"mapped/{bearing_id}.csv"
                    archive.writestr(relative, _csv(values))
                    metadata_files[relative] = {
                        "bearingId": bearing_id,
                        "runId": f"explicit-{bearing_id}",
                        "sequenceIndex": 0,
                        "startedAt": None,
                        "timestampQuality": "unavailable",
                        "windowStateLabel": label,
                        "terminalFailureMode": "outer_race" if label == "outer_race" else None,
                        "columns": {"Signal": "radial"},
                        "hasHeader": True,
                    }
                else:
                    relative = f"mapped/{bearing_id}.txt"
                    archive.writestr(relative, _txt(values))
                    metadata_files[relative] = {
                        "runId": f"explicit-{bearing_id}",
                        "sequenceIndex": 0,
                        "startedAt": None,
                        "timestampQuality": "unavailable",
                        "channels": [
                            {
                                "columnIndex": 0,
                                "bearingId": bearing_id,
                                "axis": "radial",
                                "windowStateLabel": label,
                                "terminalFailureMode": "outer_race" if label == "outer_race" else None,
                            }
                        ],
                    }
    metadata_path = dataset_root / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "datasetId": dataset_id,
                "metadataId": f"synthetic-{dataset_id}-v1",
                "samplingHz": 1_024,
                "accelerationUnit": "g",
                "files": metadata_files,
            }
        ),
        encoding="utf-8",
    )
    return {
        "datasetId": dataset_id,
        "status": "approved_for_research",
        "landingPage": f"https://example.invalid/{dataset_id}",
        "downloadUrl": f"https://example.invalid/{dataset_id}/synthetic.zip",
        "citation": "Synthetic test fixture; not scientific evidence.",
        "license": "Synthetic test fixture.",
        "expectedSha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "archivePath": archive_path.relative_to(data_root).as_posix(),
        "rawPath": (dataset_root / "raw").relative_to(data_root).as_posix(),
        "metadataPath": metadata_path.relative_to(data_root).as_posix(),
        "expectedMetadataSha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        "accessedAt": "2026-08-20T00:00:00Z",
    }


def _scientific_fixture(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "public"
    sources = [
        _dataset_fixture(data_root, "xjtu-sy"),
        _dataset_fixture(data_root, "nasa-ims"),
    ]
    manifest = data_root / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "experimentConfig": {
                    "schemaVersion": 1,
                    "configId": "synthetic-e2e-v1",
                    "featurePolicy": {
                        "policyId": "synthetic-axis-policy-v1",
                        "selectedAccelerationAxis": "radial",
                        "accelerationRmsSemanticsConfirmed": True,
                        "temperatureSemanticsConfirmed": False,
                        "evidence": "Synthetic fixture contract only; no Forzy claim.",
                    },
                    "labelMapping": {
                        "version": "synthetic-label-map-v1",
                        "mapping": {"normal": "normal", "outer_race": "outer_race"},
                    },
                    "bootstrapSamples": 20,
                },
                "sources": sources,
            }
        ),
        encoding="utf-8",
    )
    return data_root, manifest


def test_cli_dry_run_reports_external_data_gate_without_writing(tmp_path) -> None:
    output = tmp_path / "research-output"
    result = _run("--datasets", "xjtu", "ims", "--output", output, "--dry-run")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "not_run_external_data_gate"
    assert payload["issues"]
    assert any("featurePolicy" in issue for issue in payload["issues"])
    assert payload["writesPerformed"] is False
    assert not output.exists()


def test_cli_rejects_operational_output_boundary_even_in_dry_run() -> None:
    operational_roots = (
        REPOSITORY_ROOT / "artifacts" / "ml" / "real-forzy",
        REPOSITORY_ROOT / "services" / "twinops" / "src" / "twinops" / "ml",
    )
    for operational in operational_roots:
        result = _run(
            "--datasets", "xjtu", "ims", "--output", operational, "--dry-run"
        )

        assert result.returncode == 2
        payload = json.loads(result.stderr)
        assert payload["status"] == "failed_precondition"
        assert "operational" in payload["error"].lower()


def test_cli_requires_exactly_the_two_distinct_supported_benches(tmp_path) -> None:
    result = _run(
        "--datasets",
        "xjtu",
        "ims",
        "xjtu",
        "--output",
        tmp_path / "output",
        "--dry-run",
    )

    assert result.returncode == 2
    payload = json.loads(result.stderr)
    assert payload["status"] == "failed_precondition"
    assert "exactly" in payload["error"]


def test_cli_success_path_extracts_binds_provenance_and_reports_both_directions(tmp_path) -> None:
    data_root, manifest = _scientific_fixture(tmp_path)
    output = tmp_path / "output"

    result = _run(
        "--datasets",
        "xjtu",
        "ims",
        "--data-root",
        data_root,
        "--source-manifest",
        manifest,
        "--output",
        output,
        "--seed",
        42,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed_with_verified_sources"
    assert set(payload["crossBenchDirections"]) == {
        "xjtu-sy->nasa-ims",
        "nasa-ims->xjtu-sy",
    }
    assert {path.name for path in output.iterdir()} == {
        "ablation-report.json",
        "dataset-manifest.json",
    }
    report = json.loads((output / "ablation-report.json").read_text(encoding="utf-8"))
    dataset_manifest = json.loads(
        (output / "dataset-manifest.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "completed_with_verified_sources"
    assert set(report["crossBenchSummary"]) == {
        "xjtu-sy->nasa-ims",
        "nasa-ims->xjtu-sy",
    }
    for summary in report["crossBenchSummary"].values():
        assert summary["status"] == "valid_cross_bench"
        assert summary["trainCoverage"]["window_coverage"] == 1.0
        for metric in summary["metrics"].values():
            assert "fullToAggregateDelta" in metric
            assert "aggregateToForzyDelta" in metric
            assert metric["forzyVerdict"] in {
                "above_majority_baseline",
                "equal_to_majority_baseline",
                "below_majority_baseline",
            }
    assert len(report["reproduction"]["codeSha256"]) == 64
    assert len(report["reproduction"]["experimentConfigSha256"]) == 64
    assert len(report["reproduction"]["effectiveConfigSha256"]) == 64
    for dataset_id, dataset in dataset_manifest["datasets"].items():
        assert len(dataset["source"]["archiveSha256"]) == 64
        assert len(dataset["metadata"]["metadataSha256"]) == 64
        assert len(dataset["rawInventory"]["inventorySha256"]) == 64
        assert dataset["rawInventory"]["files"]
        assert (data_root / dataset_id / "raw").is_dir()


def test_cli_rejects_invalid_status_url_and_metadata_hash_without_writes(tmp_path) -> None:
    data_root, manifest = _scientific_fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["sources"][0]["status"] = "unapproved_mirror"
    payload["sources"][0]["downloadUrl"] = "not-a-url"
    payload["sources"][1]["expectedMetadataSha256"] = "0" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "output"

    result = _run(
        "--datasets",
        "xjtu",
        "ims",
        "--data-root",
        data_root,
        "--source-manifest",
        manifest,
        "--output",
        output,
        "--dry-run",
    )

    assert result.returncode == 0
    dry = json.loads(result.stdout)
    assert dry["status"] == "not_run_external_data_gate"
    joined = " ".join(dry["issues"])
    assert "approved_for_research" in joined
    assert "absolute HTTPS URL" in joined
    assert "SHA-256 mismatch" in joined
    assert not output.exists()
    assert not (data_root / "xjtu-sy" / "raw").exists()


def test_cli_requires_empty_output_or_explicit_safe_overwrite(tmp_path) -> None:
    data_root, manifest = _scientific_fixture(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "unknown.txt").write_text("preserve me", encoding="utf-8")

    result = _run(
        "--datasets",
        "xjtu",
        "ims",
        "--data-root",
        data_root,
        "--source-manifest",
        manifest,
        "--output",
        output,
    )
    assert result.returncode == 2
    assert "--overwrite" in json.loads(result.stderr)["error"]
    assert (output / "unknown.txt").read_text(encoding="utf-8") == "preserve me"
    assert not (data_root / "xjtu-sy" / "raw").exists()

    overwrite = _run(
        "--datasets",
        "xjtu",
        "ims",
        "--data-root",
        data_root,
        "--source-manifest",
        manifest,
        "--output",
        output,
        "--overwrite",
    )
    assert overwrite.returncode == 2
    assert "unknown files" in json.loads(overwrite.stderr)["error"]
