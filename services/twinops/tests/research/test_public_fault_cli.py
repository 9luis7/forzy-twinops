from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPOSITORY_ROOT / "scripts" / "run_public_fault_lab.py"


def test_cli_dry_run_reports_external_data_gate_without_writing(tmp_path) -> None:
    output = tmp_path / "research-output"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--datasets",
            "xjtu",
            "ims",
            "--output",
            str(output),
            "--dry-run",
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "not_run_external_data_gate"
    assert payload["issues"]
    assert not output.exists()


def test_cli_rejects_operational_output_boundary_even_in_dry_run() -> None:
    operational = REPOSITORY_ROOT / "artifacts" / "ml" / "real-forzy"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--datasets",
            "xjtu",
            "ims",
            "--output",
            str(operational),
            "--dry-run",
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stderr)
    assert payload["status"] == "failed_precondition"
    assert "operational" in payload["error"].lower()
