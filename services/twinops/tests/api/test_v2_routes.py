from datetime import datetime, timedelta, timezone
import os
import subprocess
import sys
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from twinops import main_v2
from twinops.config_v2 import SettingsV2
from twinops.contracts.v2_models import CanonicalSensorReadingV2
from twinops.ingestion.refresh_service import RefreshResult
from twinops.main_v2 import create_app_v2
from twinops.storage.v2_repository import (
    InsertResult,
    RefreshCycleClaimV2,
    RefreshCycleV2,
    RepositorySensorHealthV2,
)


NOW_IN_WINDOW = datetime(2026, 8, 12, 15, 0, 1, tzinfo=timezone.utc)
NOW_OUTSIDE_WINDOW = datetime(2026, 8, 13, 16, 0, 1, tzinfo=timezone.utc)


class _FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _SuccessfulFakeAsyncClient(_FakeAsyncClient):
    async def get(self, url, **kwargs):
        sensor_id = url.rsplit("_", 1)[-1]
        suffix = sensor_id[-1]
        return _FakeResponse(
            {
                f"dados{suffix}": {
                    "Velocidade": 0.04,
                    "Aceleração": 0.0,
                    "Temperatura": 34.0,
                }
            }
        )


class _Repository:
    def __init__(self):
        self.initialized = False
        self.history_queries = []
        self.samples = []
        self.health_by_sensor = {}
        self.raw_readings = []
        self.attempts = []
        self.cycles = {}

    def initialize(self):
        self.initialized = True

    def latest(self, asset_id):
        return list(self.samples)

    def history(self, query):
        self.history_queries.append(query)
        return [
            sample
            for sample in self.samples
            if query.sensor_id is None or sample.sensor_id == query.sensor_id
        ][: query.limit]

    def health(self, sensor_id):
        return self.health_by_sensor.get(sensor_id)

    def append_raw(self, reading):
        self.raw_readings.append(reading)

    def insert_distinct_sample(self, sample):
        self.samples.append(sample)
        return InsertResult(stored=True, duplicate_of=None)

    def record_attempt(self, attempt):
        self.attempts.append(attempt)

    def persist_sensor_result(self, write):
        if write.raw is not None:
            self.raw_readings.append(write.raw)
        result = None
        if write.sample is not None:
            self.samples = [
                item for item in self.samples if item.sensor_id != write.sample.sensor_id
            ]
            self.samples.append(write.sample)
            result = InsertResult(stored=True, duplicate_of=None)
        self.attempts.append(write.attempt)
        return result

    def claim_refresh_cycle(
        self,
        *,
        asset_id,
        scheduled_at,
        owner_token,
        claimed_at,
        stale_before,
    ):
        key = (asset_id, scheduled_at)
        cycle = self.cycles.get(key)
        if cycle is None or (
            cycle.completed_at is None and cycle.claimed_at <= stale_before
        ):
            cycle = RefreshCycleV2(
                asset_id=asset_id,
                scheduled_at=scheduled_at,
                owner_token=owner_token,
                claimed_at=claimed_at,
                completed_at=None,
                outcomes=None,
            )
            self.cycles[key] = cycle
            return RefreshCycleClaimV2(owned=True, cycle=cycle)
        return RefreshCycleClaimV2(owned=False, cycle=cycle)

    def complete_refresh_cycle(
        self,
        *,
        asset_id,
        scheduled_at,
        owner_token,
        completed_at,
        outcomes,
    ):
        key = (asset_id, scheduled_at)
        cycle = RefreshCycleV2(
            asset_id=asset_id,
            scheduled_at=scheduled_at,
            owner_token=owner_token,
            claimed_at=self.cycles[key].claimed_at,
            completed_at=completed_at,
            outcomes=outcomes,
        )
        self.cycles[key] = cycle
        return cycle

    def get_refresh_cycle(self, asset_id, scheduled_at):
        return self.cycles.get((asset_id, scheduled_at))


@pytest.fixture
def repository():
    return _Repository()


@pytest.fixture
def refresh_service():
    return Mock(refresh=AsyncMock())


@pytest.fixture
def settings(tmp_path):
    return SettingsV2(
        upstream_base_url="https://upstream.invalid",
        database_path=tmp_path / "twinops-v2.sqlite3",
    )


@pytest.fixture
def client(repository, refresh_service, settings):
    app = create_app_v2(
        repository=repository,
        settings=settings,
        refresh_service=refresh_service,
        assessment_scorer=None,
        clock=lambda: NOW_IN_WINDOW,
    )
    return TestClient(app)


def test_get_snapshot_never_refreshes(client, refresh_service, repository):
    response = client.get("/api/v2/assets/forzy-motor-01/snapshot")

    assert response.status_code == 200
    assert response.json()["operationalState"] == "unavailable"
    refresh_service.refresh.assert_not_called()
    assert repository.initialized is False


def test_post_refresh_returns_schedule_skip(
    repository, refresh_service, settings
):
    refresh_service.refresh.return_value = RefreshResult(False, {})
    app = create_app_v2(
        repository=repository,
        settings=settings,
        refresh_service=refresh_service,
        assessment_scorer=None,
        clock=lambda: NOW_OUTSIDE_WINDOW,
    )

    response = TestClient(app).post(
        "/api/v2/assets/forzy-motor-01/refresh"
    )

    assert response.status_code == 200
    assert response.json()["refreshAttempted"] is False
    assert response.json()["outcomes"] == {}
    assert response.json()["snapshot"]["operationalState"] == "expected_idle"
    refresh_service.refresh.assert_awaited_once_with(NOW_OUTSIDE_WINDOW)


def test_post_refresh_inside_window_returns_received_now(
    client, refresh_service
):
    refresh_service.refresh.return_value = RefreshResult(
        True, {"s1": "stored", "s2": "failed"}
    )

    response = client.post("/api/v2/assets/forzy-motor-01/refresh")

    assert response.status_code == 200
    assert response.json()["refreshAttempted"] is True
    assert response.json()["outcomes"] == {"s1": "stored", "s2": "failed"}
    assert response.json()["snapshot"]["operationalState"] == "received_now"
    assert response.json()["snapshot"]["freshnessBasis"] == "retrieval_time"


def test_post_refresh_uses_service_completion_time_for_snapshot(
    client, refresh_service
):
    completion = NOW_IN_WINDOW + timedelta(seconds=4)
    refresh_service.refresh.return_value = Mock(
        refresh_attempted=True,
        outcomes={"s1": "stored", "s2": "stored"},
        completed_at=completion,
    )

    response = client.post("/api/v2/assets/forzy-motor-01/refresh")

    assert response.status_code == 200
    assert response.json()["snapshot"]["generatedAt"] == "2026-08-12T15:00:05.000Z"


def test_post_refresh_failures_return_last_known_when_samples_exist(
    client, repository, refresh_service
):
    repository.samples = [_reading("s1"), _reading("s2")]
    refresh_service.refresh.return_value = RefreshResult(
        True, {"s1": "failed", "s2": "failed"}
    )

    response = client.post("/api/v2/assets/forzy-motor-01/refresh")

    assert response.status_code == 200
    assert response.json()["snapshot"]["operationalState"] == "last_known"
    assert response.json()["snapshot"]["freshnessBasis"] == "last_received"


def test_history_returns_only_public_sensor_frames(
    client, repository
):
    repository.samples = [_reading("s1")]

    response = client.get(
        "/api/v2/assets/forzy-motor-01/history?sensorId=s1&limit=1"
    )

    assert response.status_code == 200
    assert response.json()["limit"] == 1
    assert response.json()["items"][0]["sensorId"] == "s1"
    assert "raw" not in response.json()["items"][0]
    assert "payloadHash" not in response.json()["items"][0]
    query = repository.history_queries[-1]
    assert (query.asset_id, query.sensor_id, query.limit) == (
        "forzy-motor-01",
        "s1",
        1,
    )


@pytest.mark.parametrize(
    "query",
    ["sensorId=s3", "limit=0", "limit=501"],
)
def test_history_rejects_unknown_sensors_and_out_of_range_limits(
    client, repository, query
):
    response = client.get(
        f"/api/v2/assets/forzy-motor-01/history?{query}"
    )

    assert response.status_code == 422
    assert repository.history_queries == []


def test_history_accepts_the_500_item_boundary(client, repository):
    response = client.get(
        "/api/v2/assets/forzy-motor-01/history?sensorId=s2&limit=500"
    )

    assert response.status_code == 200
    assert repository.history_queries[-1].limit == 500


@pytest.mark.parametrize(
    "query",
    [
        "from=2026-08-12T15:00:00",
        "to=2026-08-12T15:00:05",
        "from=2026-08-12T15:00:05Z&to=2026-08-12T15:00:00Z",
    ],
)
def test_history_rejects_naive_or_reversed_ranges(client, repository, query):
    response = client.get(
        f"/api/v2/assets/forzy-motor-01/history?{query}"
    )

    assert response.status_code == 422
    assert repository.history_queries == []


def test_integration_health_sanitizes_repository_errors(client, repository):
    repository.health_by_sensor["s1"] = RepositorySensorHealthV2(
        sensor_id="s1",
        last_attempt_at=NOW_IN_WINDOW,
        last_success_at=None,
        latency_ms=19,
        error_code="db.internal.example\nTraceback: secret",
        sample_count=3,
    )

    response = client.get("/api/v2/integration/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["integration"]["state"] == "active"
    assert body["integration"]["sensors"]["s1"]["error"] == "upstream_unavailable"
    assert body["integration"]["sensors"]["s2"]["sampleCount"] == 0
    assert "internal.example" not in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v2/assets/fake/snapshot"),
        ("post", "/api/v2/assets/fake/refresh"),
        ("get", "/api/v2/assets/fake/history"),
    ],
)
def test_unknown_asset_is_404_before_any_effect(
    method, path, repository, refresh_service, settings
):
    clock = Mock(return_value=NOW_IN_WINDOW)
    app = create_app_v2(
        repository=repository,
        settings=settings,
        refresh_service=refresh_service,
        assessment_scorer=None,
        clock=clock,
    )

    response = getattr(TestClient(app), method)(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "asset_not_found"}
    clock.assert_not_called()
    refresh_service.refresh.assert_not_called()
    assert repository.history_queries == []


def test_mutated_asset_setting_cannot_expand_the_public_boundary(
    repository, refresh_service, tmp_path
):
    clock = Mock(return_value=NOW_IN_WINDOW)
    settings = SettingsV2(
        upstream_base_url="https://upstream.invalid",
        database_path=tmp_path / "mutated.sqlite3",
        asset_id="fake",
    )
    app = create_app_v2(
        repository=repository,
        settings=settings,
        refresh_service=refresh_service,
        assessment_scorer=None,
        clock=clock,
    )

    response = TestClient(app).post("/api/v2/assets/fake/refresh")

    assert response.status_code == 404
    assert response.json() == {"detail": "asset_not_found"}
    clock.assert_not_called()
    refresh_service.refresh.assert_not_called()
    assert repository.history_queries == []


def test_database_failure_returns_only_a_sanitized_error(
    client, repository
):
    repository.latest = Mock(
        side_effect=RuntimeError(
            "postgresql://secret@db.internal.example/twinops\nTraceback: secret"
        )
    )

    response = TestClient(
        client.app, raise_server_exceptions=False
    ).get("/api/v2/assets/forzy-motor-01/snapshot")

    assert response.status_code == 500
    assert response.json() == {"detail": "internal_error"}
    assert "secret" not in response.text
    assert "internal.example" not in response.text
    assert "Traceback" not in response.text


def test_model_failure_degrades_without_exposing_details(
    repository, refresh_service, settings
):
    repository.samples = [_reading("s1"), _reading("s2")]
    scorer = Mock()
    scorer.assess.side_effect = RuntimeError(
        "model host ml.internal.example\nTraceback: secret"
    )
    app = create_app_v2(
        repository=repository,
        settings=settings,
        refresh_service=refresh_service,
        assessment_scorer=scorer,
        clock=lambda: NOW_IN_WINDOW,
    )

    response = TestClient(app).get(
        "/api/v2/assets/forzy-motor-01/snapshot"
    )

    assert response.status_code == 200
    assert response.json()["assessment"] is None
    assert response.json()["status"] == "insufficient_data"
    assert "secret" not in response.text
    assert "internal.example" not in response.text
    assert "Traceback" not in response.text


def test_importing_main_v2_has_no_environment_or_database_side_effects(tmp_path):
    database_path = tmp_path / "must-not-exist.sqlite3"
    env = os.environ.copy()
    env.pop("TWINOPS_UPSTREAM_BASE_URL", None)
    env.pop("DATABASE_URL", None)
    env["TWINOPS_DATABASE_PATH"] = str(database_path)

    completed = subprocess.run(
        [sys.executable, "-c", "import twinops.main_v2; print('imported')"],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "imported"
    assert database_path.exists() is False


def test_environment_factory_selects_sqlite_and_initializes_in_lifespan(
    monkeypatch, tmp_path
):
    repository = _Repository()
    sqlite_factory = Mock(return_value=repository)
    postgres_factory = Mock()
    async_client_factory = Mock(return_value=_FakeAsyncClient())
    monkeypatch.setattr(
        main_v2, "SQLiteTelemetryRepositoryV2", sqlite_factory, raising=False
    )
    monkeypatch.setattr(
        main_v2, "PostgresTelemetryRepository", postgres_factory, raising=False
    )
    monkeypatch.setattr(
        main_v2,
        "httpx",
        Mock(AsyncClient=async_client_factory),
        raising=False,
    )
    database_path = tmp_path / "runtime.sqlite3"

    app = getattr(main_v2, "create_app_v2_from_env")(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "TWINOPS_DATABASE_PATH": str(database_path),
        },
        clock=lambda: NOW_IN_WINDOW,
    )

    assert repository.initialized is False
    async_client_factory.assert_not_called()
    sqlite_factory.assert_called_once_with(database_path)
    postgres_factory.assert_not_called()
    with TestClient(app):
        assert repository.initialized is True
        async_client_factory.assert_called_once_with()


def test_environment_factory_selects_postgres_when_database_url_exists(
    monkeypatch,
):
    database_url = (
        "postgresql://runtime@runtime-pooler.invalid/twinops?sslmode=require"
    )
    repository = _Repository()
    sqlite_factory = Mock()
    postgres_factory = Mock(return_value=repository)
    monkeypatch.setattr(
        main_v2, "SQLiteTelemetryRepositoryV2", sqlite_factory
    )
    monkeypatch.setattr(
        main_v2, "PostgresTelemetryRepository", postgres_factory
    )

    app = main_v2.create_app_v2_from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "DATABASE_URL": database_url,
            "VERCEL": "1",
        }
    )

    assert app.state.repository is repository
    assert repository.initialized is False
    postgres_factory.assert_called_once_with(database_url)
    sqlite_factory.assert_not_called()


def test_vercel_environment_requires_database_url():
    with pytest.raises(ValueError, match="DATABASE_URL is required for deployment"):
        main_v2.create_app_v2_from_env(
            {
                "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
                "VERCEL": "1",
            }
        )


def test_environment_factory_refreshes_only_the_canonical_asset(
    monkeypatch,
):
    repository = _Repository()
    monkeypatch.setattr(
        main_v2,
        "SQLiteTelemetryRepositoryV2",
        Mock(return_value=repository),
    )
    monkeypatch.setattr(
        main_v2,
        "httpx",
        Mock(
            AsyncClient=Mock(return_value=_SuccessfulFakeAsyncClient())
        ),
    )
    app = main_v2.create_app_v2_from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "TWINOPS_ASSET_ID": "fake",
        },
        clock=lambda: NOW_IN_WINDOW,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/assets/forzy-motor-01/refresh"
        )
        history = client.get(
            "/api/v2/assets/forzy-motor-01/history?limit=2"
        )

    assert response.status_code == 200
    assert response.json()["outcomes"] == {"s1": "stored", "s2": "stored"}
    assert history.status_code == 200
    assert {item["assetId"] for item in history.json()["items"]} == {
        "forzy-motor-01"
    }


def test_runtime_loads_scorer_only_with_all_three_anchors(
    monkeypatch, tmp_path
):
    repository = _Repository()
    scorer = Mock()
    scorer_loader = Mock(return_value=scorer)
    monkeypatch.setattr(
        main_v2,
        "SQLiteTelemetryRepositoryV2",
        Mock(return_value=repository),
    )
    monkeypatch.setattr(
        main_v2,
        "httpx",
        Mock(AsyncClient=Mock(return_value=_FakeAsyncClient())),
    )
    monkeypatch.setattr(main_v2, "load_assessment_scorer", scorer_loader)
    artifact_path = tmp_path / "model"
    manifest_hash = f"sha256:{'1' * 64}"
    model_hash = f"sha256:{'2' * 64}"
    app = main_v2.create_app_v2_from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "TWINOPS_ML_ARTIFACT_PATH": str(artifact_path),
            "TWINOPS_ML_MANIFEST_HASH": manifest_hash,
            "TWINOPS_ML_MODEL_HASH": model_hash,
        }
    )

    scorer_loader.assert_not_called()
    with TestClient(app):
        scorer_loader.assert_called_once_with(
            artifact_path,
            expected_manifest_hash=manifest_hash,
            expected_model_hash=model_hash,
        )
        assert app.state.assessment_scorer is scorer


def test_runtime_keeps_telemetry_available_when_scorer_loader_fails(
    monkeypatch, tmp_path, caplog
):
    caplog.set_level("WARNING", logger="twinops.api")
    repository = _Repository()
    scorer_loader = Mock(
        side_effect=RuntimeError(
            "artifact host ml.internal.example\nTraceback: secret"
        )
    )
    monkeypatch.setattr(
        main_v2,
        "SQLiteTelemetryRepositoryV2",
        Mock(return_value=repository),
    )
    monkeypatch.setattr(
        main_v2,
        "httpx",
        Mock(AsyncClient=Mock(return_value=_FakeAsyncClient())),
    )
    monkeypatch.setattr(main_v2, "load_assessment_scorer", scorer_loader)
    app = main_v2.create_app_v2_from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "TWINOPS_ML_ARTIFACT_PATH": str(tmp_path / "model"),
            "TWINOPS_ML_MANIFEST_HASH": f"sha256:{'1' * 64}",
            "TWINOPS_ML_MODEL_HASH": f"sha256:{'2' * 64}",
        },
        clock=lambda: NOW_IN_WINDOW,
    )

    with TestClient(app) as client:
        snapshot = client.get(
            "/api/v2/assets/forzy-motor-01/snapshot"
        )
        health = client.get("/api/v2/integration/health")

    assert snapshot.status_code == 200
    assert snapshot.json()["assessment"] is None
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert "internal.example" not in snapshot.text + health.text
    assert "Traceback" not in snapshot.text + health.text
    assert "secret" not in snapshot.text + health.text
    assert "assessment_scorer_unavailable error_type=RuntimeError" in caplog.text
    assert "internal.example" not in caplog.text
    assert "Traceback" not in caplog.text
    assert "secret" not in caplog.text


def test_runtime_does_not_load_scorer_without_anchors(monkeypatch):
    repository = _Repository()
    scorer_loader = Mock()
    monkeypatch.setattr(
        main_v2,
        "SQLiteTelemetryRepositoryV2",
        Mock(return_value=repository),
    )
    monkeypatch.setattr(
        main_v2,
        "httpx",
        Mock(AsyncClient=Mock(return_value=_FakeAsyncClient())),
    )
    monkeypatch.setattr(main_v2, "load_assessment_scorer", scorer_loader)
    app = main_v2.create_app_v2_from_env(
        {"TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid"}
    )

    with TestClient(app):
        scorer_loader.assert_not_called()


def _reading(sensor_id: str) -> CanonicalSensorReadingV2:
    suffix = "1" if sensor_id == "s1" else "2"
    return CanonicalSensorReadingV2.model_validate(
        {
            "schemaVersion": "2.0",
            "readingId": f"00000000-0000-4000-8000-00000000000{suffix}",
            "source": "forzy-live",
            "assetId": "forzy-motor-01",
            "sensorId": sensor_id,
            "scheduledAt": "2026-08-12T15:00:00.000Z",
            "observedAt": "2026-08-12T15:00:01.000Z",
            "receivedAt": "2026-08-12T15:00:01.000Z",
            "timestampQuality": "assumed_from_retrieval",
            "measurements": {
                "vibrationVelocityRms": {
                    "value": 0.04,
                    "unit": "mm/s",
                    "semanticConfidence": "inferred_from_datasheet",
                },
                "vibrationAcceleration": {
                    "value": 0.0,
                    "unit": "g",
                    "statistic": "unknown",
                    "semanticConfidence": "unconfirmed",
                },
                "temperature": {
                    "value": 34.0,
                    "unit": "degC",
                    "semanticConfidence": "inferred_from_datasheet",
                },
            },
            "qualityFlags": [],
            "payloadHash": f"sha256:{suffix * 64}",
            "raw": {},
            "provenance": {
                "sourceSystem": "forzy-api",
                "ingestedAt": "2026-08-12T15:00:01.000Z",
                "sourceTimestampProvided": False,
            },
        }
    )
