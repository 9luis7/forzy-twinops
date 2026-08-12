from datetime import datetime
import warnings
from zoneinfo import ZoneInfo

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
)
from fastapi.testclient import TestClient

from twinops.config import Settings
from twinops.main import create_app
from twinops.storage.repository import CollectionAttempt
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository


SP = ZoneInfo("America/Sao_Paulo")


def test_health_reports_expected_idle_outside_window(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path)
    repo.initialize()
    thursday = datetime(2026, 8, 13, 12, 0, tzinfo=SP)

    response = TestClient(
        create_app(repo, settings, clock=lambda: thursday)
    ).get("/api/v1/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["collector"]["state"] == "expected_idle"
    assert set(body["collector"]["sensors"]) == {"s1", "s2"}
    assert body["collector"]["sensors"]["s1"]["sampleCount"] == 0
    assert settings.upstream_base_url not in response.text


def test_health_is_independent_per_sensor_and_sanitizes_unknown_error(tmp_path):
    settings = Settings("https://secret-upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path)
    repo.initialize()
    first = datetime(2026, 8, 12, 12, 0, tzinfo=SP)
    later = datetime(2026, 8, 12, 12, 0, 5, tzinfo=SP)
    repo.record_attempt(CollectionAttempt("s1", first, first, True, 12, None))
    repo.record_attempt(
        CollectionAttempt(
            "s1",
            later,
            later,
            False,
            21,
            "secret database error at https://secret-upstream.invalid",
        )
    )

    response = TestClient(
        create_app(repo, settings, clock=lambda: later)
    ).get("/api/v1/system/health")

    body = response.json()
    assert body["collector"]["state"] == "active"
    assert body["collector"]["sensors"]["s1"] == {
        "lastAttemptAt": "2026-08-12T15:00:05Z",
        "lastSuccessAt": "2026-08-12T15:00:00Z",
        "latencyMs": 21,
        "error": "upstream_unavailable",
        "sampleCount": 0,
    }
    assert body["collector"]["sensors"]["s2"]["error"] is None
    assert "secret" not in response.text
