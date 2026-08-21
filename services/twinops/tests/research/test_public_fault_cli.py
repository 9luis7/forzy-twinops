from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPOSITORY_ROOT / "scripts" / "run_public_fault_lab.py"


def _load_script_module():
    module_name = "twinops_public_fault_lab_test_module"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


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
                        "kind": "signal_window",
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
                **(
                    {"samplesPerWindow": 128}
                    if dataset_id in {"xjtu-sy", "nasa-ims"}
                    else {}
                ),
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


def test_report_pair_publication_removes_partial_generation_after_second_replace_interrupt(
    tmp_path, monkeypatch
) -> None:
    """Regression: publishing report one before report two must never expose a mixed pair."""

    module = _load_script_module()
    output = tmp_path / "output"
    output.mkdir()
    original_replace = os.replace
    interruption = KeyboardInterrupt("second report publication interrupted")
    final_replacements = 0

    def interrupt_second_final(source, target):
        nonlocal final_replacements
        if Path(target).name in module._OUTPUT_FILES:
            final_replacements += 1
            if final_replacements == 2:
                raise interruption
        return original_replace(source, target)

    monkeypatch.setattr(module.os, "replace", interrupt_second_final)

    with pytest.raises(KeyboardInterrupt) as caught:
        module._atomic_reports(
            output,
            {"schemaVersion": 2, "status": "new-ablation"},
            {"schemaVersion": 2, "status": "new-dataset"},
        )

    assert caught.value is interruption
    assert not any((output / name).exists() for name in module._OUTPUT_FILES)
    assert list(output.iterdir()) == []


def test_report_pair_publication_binds_both_documents_to_one_verified_generation(
    tmp_path,
) -> None:
    """Regression: independently replaced JSON files need a verifiable common generation."""

    module = _load_script_module()
    output = tmp_path / "output"
    output.mkdir()
    module._atomic_reports(
        output,
        {"schemaVersion": 2, "status": "ablation"},
        {"schemaVersion": 2, "status": "dataset"},
    )

    documents = {
        name: json.loads((output / name).read_text(encoding="utf-8"))
        for name in module._OUTPUT_FILES
    }
    publications = [document["publication"] for document in documents.values()]
    assert publications[0] == publications[1]
    publication = publications[0]
    assert publication["schemaVersion"] == 1
    assert len(publication["generationId"]) == 64
    assert set(publication["documents"]) == module._OUTPUT_FILES
    expected_hashes = {}
    for name, document in documents.items():
        unbound = dict(document)
        unbound.pop("publication")
        expected = hashlib.sha256(
            json.dumps(unbound, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert publication["documents"][name] == expected
        expected_hashes[name] = expected
    expected_generation = hashlib.sha256(
        json.dumps(
            {"schemaVersion": 1, "documents": expected_hashes},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert publication["generationId"] == expected_generation


def test_report_pair_publication_verifies_disk_pair_and_rolls_back_tampering(
    tmp_path, monkeypatch
) -> None:
    """Regression: success cannot be reported for a mismatched on-disk pair."""

    module = _load_script_module()
    output = tmp_path / "output"
    output.mkdir()
    original_replace = os.replace
    final_replacements = 0

    def tamper_after_second_final(source, target):
        nonlocal final_replacements
        original_replace(source, target)
        if Path(target).name in module._OUTPUT_FILES:
            final_replacements += 1
            if final_replacements == 2:
                payload = json.loads(Path(target).read_text(encoding="utf-8"))
                payload["status"] = "tampered-after-publication"
                Path(target).write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(module.os, "replace", tamper_after_second_final)

    with pytest.raises(ValueError, match="published report pair"):
        module._atomic_reports(
            output,
            {"schemaVersion": 2, "status": "ablation"},
            {"schemaVersion": 2, "status": "dataset"},
        )

    assert list(output.iterdir()) == []


def test_report_pair_publication_restores_previous_pair_after_second_replace_failure(
    tmp_path, monkeypatch
) -> None:
    """Regression: an overwrite failure must restore both previous reports byte-for-byte."""

    module = _load_script_module()
    output = tmp_path / "output"
    output.mkdir()
    module._atomic_reports(
        output,
        {"schemaVersion": 2, "status": "old-ablation"},
        {"schemaVersion": 2, "status": "old-dataset"},
    )
    previous = {name: (output / name).read_bytes() for name in module._OUTPUT_FILES}
    original_replace = os.replace
    final_replacements = 0

    def fail_second_final(source, target):
        nonlocal final_replacements
        if Path(target).name in module._OUTPUT_FILES:
            final_replacements += 1
            if final_replacements == 2:
                raise RuntimeError("second report replace failed")
        return original_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_second_final)

    with pytest.raises(RuntimeError, match="second report replace failed"):
        module._atomic_reports(
            output,
            {"schemaVersion": 2, "status": "new-ablation"},
            {"schemaVersion": 2, "status": "new-dataset"},
        )

    assert {name: (output / name).read_bytes() for name in module._OUTPUT_FILES} == previous
    assert {path.name for path in output.iterdir()} == module._OUTPUT_FILES


def test_report_pair_publication_preserves_original_exception_if_rollback_replace_fails(
    tmp_path, monkeypatch
) -> None:
    """Regression: rollback errors cannot mask the publish interrupt or leave a mixed pair."""

    module = _load_script_module()
    output = tmp_path / "output"
    output.mkdir()
    module._atomic_reports(
        output,
        {"schemaVersion": 2, "status": "old-ablation"},
        {"schemaVersion": 2, "status": "old-dataset"},
    )
    original_replace = os.replace
    publication_error = KeyboardInterrupt("publication interrupted")
    final_replacements = 0

    def fail_publication_and_rollback(source, target):
        nonlocal final_replacements
        if Path(target).name in module._OUTPUT_FILES:
            final_replacements += 1
            if final_replacements == 2:
                raise publication_error
            if final_replacements >= 3:
                raise RuntimeError("rollback replace failed")
        return original_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_publication_and_rollback)

    with pytest.raises(KeyboardInterrupt) as caught:
        module._atomic_reports(
            output,
            {"schemaVersion": 2, "status": "new-ablation"},
            {"schemaVersion": 2, "status": "new-dataset"},
        )

    assert caught.value is publication_error
    assert any("rollback" in note.lower() for note in getattr(caught.value, "__notes__", ()))
    assert list(output.iterdir()) == []


def test_report_pair_staging_interrupt_keeps_previous_pair_without_running_rollback(
    tmp_path, monkeypatch
) -> None:
    """Regression: a failure before publication starts must leave the old pair untouched."""

    module = _load_script_module()
    output = tmp_path / "output"
    output.mkdir()
    module._atomic_reports(
        output,
        {"schemaVersion": 2, "status": "old-ablation"},
        {"schemaVersion": 2, "status": "old-dataset"},
    )
    previous = {name: (output / name).read_bytes() for name in module._OUTPUT_FILES}
    staging_error = KeyboardInterrupt("staging interrupted")

    def interrupt_staging(*_arguments, **_keywords):
        raise staging_error

    def forbid_replace(*_arguments, **_keywords):
        raise AssertionError("rollback must not run before the first publication replace")

    monkeypatch.setattr(module, "_stage_json", interrupt_staging)
    monkeypatch.setattr(module.os, "replace", forbid_replace)

    with pytest.raises(KeyboardInterrupt) as caught:
        module._atomic_reports(
            output,
            {"schemaVersion": 2, "status": "new-ablation"},
            {"schemaVersion": 2, "status": "new-dataset"},
        )

    assert caught.value is staging_error
    assert {name: (output / name).read_bytes() for name in module._OUTPUT_FILES} == previous


def test_report_pair_first_replace_failure_restores_previous_pair(
    tmp_path, monkeypatch
) -> None:
    """Regression: a failed first atomic replace must leave the old pair observable."""

    module = _load_script_module()
    output = tmp_path / "output"
    output.mkdir()
    module._atomic_reports(
        output,
        {"schemaVersion": 2, "status": "old-ablation"},
        {"schemaVersion": 2, "status": "old-dataset"},
    )
    previous = {name: (output / name).read_bytes() for name in module._OUTPUT_FILES}
    publication_error = OSError("first replace rejected before mutation")
    replace_calls = 0

    def fail_first_before_mutation(*_arguments, **_keywords):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 1:
            raise publication_error
        return original_replace(*_arguments, **_keywords)

    original_replace = os.replace
    monkeypatch.setattr(module.os, "replace", fail_first_before_mutation)

    with pytest.raises(OSError) as caught:
        module._atomic_reports(
            output,
            {"schemaVersion": 2, "status": "new-ablation"},
            {"schemaVersion": 2, "status": "new-dataset"},
        )

    assert caught.value is publication_error
    assert {name: (output / name).read_bytes() for name in module._OUTPUT_FILES} == previous


def test_report_pair_first_replace_mutates_then_interrupts_and_restores_previous_pair(
    tmp_path, monkeypatch
) -> None:
    """Regression: an interrupt after the filesystem swap is an ambiguous replace failure."""

    module = _load_script_module()
    output = tmp_path / "output"
    output.mkdir()
    module._atomic_reports(
        output,
        {"schemaVersion": 2, "status": "old-ablation"},
        {"schemaVersion": 2, "status": "old-dataset"},
    )
    previous = {name: (output / name).read_bytes() for name in module._OUTPUT_FILES}
    original_replace = os.replace
    publication_error = KeyboardInterrupt("interrupted after filesystem mutation")
    replace_calls = 0

    def mutate_then_interrupt(source, target):
        nonlocal replace_calls
        replace_calls += 1
        original_replace(source, target)
        if replace_calls == 1:
            raise publication_error

    monkeypatch.setattr(module.os, "replace", mutate_then_interrupt)

    with pytest.raises(KeyboardInterrupt) as caught:
        module._atomic_reports(
            output,
            {"schemaVersion": 2, "status": "new-ablation"},
            {"schemaVersion": 2, "status": "new-dataset"},
        )

    assert caught.value is publication_error
    assert {name: (output / name).read_bytes() for name in module._OUTPUT_FILES} == previous
    assert {path.name for path in output.iterdir()} == module._OUTPUT_FILES
