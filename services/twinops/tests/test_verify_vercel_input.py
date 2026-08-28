import json
from pathlib import Path
import subprocess
import sys

import pytest


REQUIRED_ML_ARTIFACTS = [
    "artifacts/ml/real-forzy/backtest-report.json",
    "artifacts/ml/real-forzy/feature-manifest.json",
    "artifacts/ml/real-forzy/model-card.md",
    "artifacts/ml/real-forzy/pipeline-config.json",
    "artifacts/ml/real-forzy/pipeline.joblib",
]


def _run_gate(tmp_path: Path, paths: list[str]) -> subprocess.CompletedProcess[str]:
    payload_path = tmp_path / "vercel-dry-run.json"
    payload_path.write_text(
        json.dumps({"files": [{"path": path} for path in paths]}),
        encoding="utf-8",
    )
    repository_root = Path(__file__).parents[3]
    return subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "verify_vercel_input.py"),
            "--input",
            str(payload_path),
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_gate_stdin(paths: list[str]) -> subprocess.CompletedProcess[str]:
    repository_root = Path(__file__).parents[3]
    return subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "verify_vercel_input.py"),
            "--input",
            "-",
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        input=json.dumps({"files": [{"path": path} for path in paths]}),
        check=False,
    )


def test_accepts_exact_real_ml_bundle_without_local_runtime_data(tmp_path):
    completed = _run_gate(
        tmp_path,
        [
            ".env.example",
            "api/index.py",
            *REQUIRED_ML_ARTIFACTS,
            "public/models/conjunto-motor-bomba.glb",
            "src/App.jsx",
        ],
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        "vercel_input_check_ok ml_artifacts=5"
    )


def test_accepts_vercel_input_from_stdin():
    completed = _run_gate_stdin(REQUIRED_ML_ARTIFACTS)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        "vercel_input_check_ok ml_artifacts=5"
    )


@pytest.mark.parametrize(
    "forbidden_path",
    [
        "tmp/e2e/twinops.sqlite3",
        "test-results/deployed-real/trace.zip",
        "data/raw/forzy.csv",
    ],
)
def test_rejects_local_runtime_data_from_deployment_input(
    tmp_path,
    forbidden_path,
):
    completed = _run_gate(
        tmp_path,
        [
            *REQUIRED_ML_ARTIFACTS,
            forbidden_path,
        ],
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr.strip() == (
        "vercel_input_check_failed code=forbidden_paths count=1"
    )


def test_rejects_deployment_input_missing_one_required_ml_artifact(tmp_path):
    completed = _run_gate(tmp_path, REQUIRED_ML_ARTIFACTS[:-1])

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr.strip() == (
        "vercel_input_check_failed code=missing_ml_artifacts count=1"
    )


@pytest.mark.parametrize(
    "unexpected_path",
    [
        "artifacts/ml/real-forzy/source-summary.json",
        "artifacts/ml/pipeline.joblib",
        "artifacts/ml-public/dataset-manifest.json",
        "artifacts/twin3d/conversion-report.json",
    ],
)
def test_rejects_unapproved_file_beside_the_required_ml_bundle(
    tmp_path,
    unexpected_path,
):
    completed = _run_gate(
        tmp_path,
        [
            *REQUIRED_ML_ARTIFACTS,
            unexpected_path,
        ],
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr.strip() == (
        "vercel_input_check_failed code=unexpected_ml_artifacts count=1"
    )
