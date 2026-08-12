from datetime import datetime, timezone
import warnings

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
)
from fastapi.testclient import TestClient

from twinops.config import Settings
from twinops.contracts.models import DigitalTwinSnapshot
from twinops.ingestion.live_adapter import adapt_live_payload
from twinops.main import create_app
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository


def api_setup(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path)
    repo.initialize()
    slot = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
    samples = []
    for sensor_id in ("s1", "s2"):
        samples.append(
            adapt_live_payload(
                sensor_id=sensor_id,
                payload={
                    f"dados{sensor_id[-1]}": {
                        "Velocidade": 0.04,
                        "Aceleração": 0.0,
                        "Temperatura": 34,
                    }
                },
                scheduled_at=slot,
                received_at=slot,
                asset_tag=settings.asset_tag,
            )
        )
    return repo, settings, samples


def test_history_is_filtered_projected_and_never_exposes_audit_fields(tmp_path):
    repo, settings, samples = api_setup(tmp_path)
    for sample in samples:
        repo.insert_sample(sample)

    response = TestClient(create_app(repo, settings)).get(
        "/api/v1/twin/assets/MTR-BMB-042/history?sensorId=s1&limit=10"
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["sensorId"] == "s1"
    assert body["items"][0]["sourceMode"] == "live"
    assert not {
        "raw",
        "payloadHash",
        "provenance",
        "scheduledAt",
    } & body["items"][0].keys()


def test_snapshot_is_contract_valid_with_missing_sensor_marked_unavailable(tmp_path):
    repo, settings, samples = api_setup(tmp_path)
    repo.insert_sample(samples[0])

    response = TestClient(create_app(repo, settings)).get(
        "/api/v1/twin/assets/MTR-BMB-042/snapshot"
    )

    assert response.status_code == 200
    snapshot = DigitalTwinSnapshot.model_validate(response.json())
    assert [channel.sensor_id for channel in snapshot.channels] == ["s1", "s2"]
    missing = snapshot.channels[1]
    assert missing.received_at is None
    assert missing.measurements.temperature is None
    assert missing.quality_flags == ["unavailable"]
    assert all("raw" not in channel.model_dump() for channel in snapshot.channels)


def test_invalid_limit_is_422_and_does_not_leak_upstream(tmp_path):
    repo, settings, _ = api_setup(tmp_path)
    response = TestClient(create_app(repo, settings)).get(
        "/api/v1/twin/assets/MTR-BMB-042/history?limit=1001"
    )
    assert response.status_code == 422
    assert settings.upstream_base_url not in response.text


def test_unexpected_repository_error_is_closed_and_sanitized(tmp_path):
    _, settings, _ = api_setup(tmp_path)

    class BrokenRepository:
        def history(self, query):
            raise RuntimeError(f"database failure via {settings.upstream_base_url}")

    response = TestClient(
        create_app(BrokenRepository(), settings), raise_server_exceptions=False
    ).get("/api/v1/twin/assets/MTR-BMB-042/history")

    assert response.status_code == 500
    assert response.json() == {"detail": "internal_error"}
    assert settings.upstream_base_url not in response.text
