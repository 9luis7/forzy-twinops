import os
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from twinops.cli import create_collector
from twinops.config import Settings
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository

FIXTURE = Path("services/twinops/tests/fixtures/telemetry.csv")


def test_import_csv_command_reports_counts_and_reimport_is_duplicate(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://invalid.example",
            "TWINOPS_DATABASE_PATH": str(tmp_path / "telemetry.db"),
        }
    )
    command = [sys.executable, "-m", "twinops.cli", "import-csv", str(FIXTURE)]

    first = subprocess.run(command, capture_output=True, text=True, env=env)
    second = subprocess.run(command, capture_output=True, text=True, env=env)

    assert first.returncode == 0, first.stderr
    assert "rows_read=2" in first.stdout
    assert "samples_inserted=2" in first.stdout
    assert "rejected=0" in first.stdout
    assert second.returncode == 0, second.stderr
    assert "samples_inserted=0" in second.stdout
    assert "duplicates=2" in second.stdout
    assert "invalid.example" not in first.stdout + first.stderr


@pytest.mark.asyncio
async def test_runtime_collector_uses_configured_timezone(tmp_path):
    settings = Settings(
        "https://invalid.example",
        tmp_path / "telemetry.db",
        timezone_name="UTC",
    )
    repository = SQLiteTelemetryRepository(settings.database_path)

    async with httpx.AsyncClient() as http:
        collector = create_collector(http, repository, settings)

        assert collector.window.timezone_name == "UTC"
