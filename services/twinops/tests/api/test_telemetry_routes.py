from datetime import datetime, timezone
from pathlib import Path
import warnings

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
)
from fastapi.testclient import TestClient
import httpx
import pytest

from twinops.config import Settings
from twinops.contracts.models import AssetConditionAssessment, DigitalTwinSnapshot
from twinops.ingestion.collector import Collector
from twinops.ingestion.live_adapter import adapt_live_payload
from twinops.ingestion.upstream import UpstreamClient
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


def test_snapshot_freshness_respects_poll_age_and_collection_window(tmp_path):
    repo, settings, samples = api_setup(tmp_path)
    repo.insert_sample(samples[0])

    delayed = TestClient(
        create_app(
            repo,
            settings,
            clock=lambda: datetime(2026, 8, 12, 15, 0, 30, tzinfo=timezone.utc),
        )
    ).get("/api/v1/twin/assets/MTR-BMB-042/snapshot")
    expected_idle = TestClient(
        create_app(
            repo,
            settings,
            clock=lambda: datetime(2026, 8, 13, 15, 0, tzinfo=timezone.utc),
        )
    ).get("/api/v1/twin/assets/MTR-BMB-042/snapshot")

    assert delayed.json()["freshness"] == "delayed"
    assert expected_idle.json()["freshness"] == "expected_idle"


def test_snapshot_exposes_worst_available_ml_assessment(tmp_path):
    repo, settings, samples = api_setup(tmp_path)
    for sample in samples:
        repo.insert_sample(sample)

    assessment = AssetConditionAssessment.model_validate(
        __import__("json").loads(
            Path(
                "contracts/v1/fixtures/asset-condition-assessment-evidence.valid.json"
            ).read_text(encoding="utf-8")
        )
    )

    class StubScorer:
        def __init__(self):
            self.sensor_ids = []

        def assess(self, readings, *, now):
            self.sensor_ids.append(readings[-1].sensor_id)
            return assessment.model_copy(
                update={"sensor_id": readings[-1].sensor_id}
            )

    scorer = StubScorer()
    response = TestClient(
        create_app(repo, settings, assessment_scorer=scorer)
    ).get("/api/v1/twin/assets/MTR-BMB-042/snapshot")

    assert response.status_code == 200
    body = DigitalTwinSnapshot.model_validate(response.json())
    assert body.status == "watch"
    assert body.assessment is not None
    assert body.assessment.assessment.status == "watch"
    assert body.capabilities.copilot is True
    assert scorer.sensor_ids == ["s1", "s2"]


def test_insufficient_sensor_takes_precedence_over_normal_assessment(tmp_path):
    repo, settings, samples = api_setup(tmp_path)
    for sample in samples:
        repo.insert_sample(sample)
    fixture = AssetConditionAssessment.model_validate(
        __import__("json").loads(
            Path(
                "contracts/v1/fixtures/asset-condition-assessment-evidence.valid.json"
            ).read_text(encoding="utf-8")
        )
    )

    class MixedScorer:
        def assess(self, readings, *, now):
            sensor_id = readings[-1].sensor_id
            status = "normal" if sensor_id == "s1" else "insufficient_data"
            return fixture.model_copy(
                update={
                    "sensor_id": sensor_id,
                    "assessment": fixture.assessment.model_copy(
                        update={"status": status}
                    ),
                }
            )

    body = TestClient(
        create_app(repo, settings, assessment_scorer=MixedScorer())
    ).get("/api/v1/twin/assets/MTR-BMB-042/snapshot").json()

    assert body["status"] == "insufficient_data"
    assert body["assessment"]["sensorId"] == "s2"


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


@pytest.mark.asyncio
async def test_simulated_window_reaches_snapshot_and_history_within_two_cycles(tmp_path):
    repo, settings, _ = api_setup(tmp_path)

    def handler(request: httpx.Request):
        sensor_id = request.url.path[-2:]
        return httpx.Response(
            200,
            json={
                f"dados{sensor_id[-1]}": {
                    "Velocidade": 0.04 if sensor_id == "s1" else 0.05,
                    "Aceleração": 0.0,
                    "Temperatura": 34 if sensor_id == "s1" else 35,
                }
            },
        )

    async def no_sleep(_: float):
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        collector = Collector(
            UpstreamClient(
                http, settings.upstream_base_url, 2.0, sleep=no_sleep
            ),
            repo,
            settings.asset_tag,
        )
        assert await collector.tick(
            datetime(2026, 8, 12, 15, 0, 7, tzinfo=timezone.utc)
        ) == "collected"
        assert await collector.tick(
            datetime(2026, 8, 12, 15, 0, 12, tzinfo=timezone.utc)
        ) == "collected"

    client = TestClient(create_app(repo, settings))
    snapshot = client.get(
        "/api/v1/twin/assets/MTR-BMB-042/snapshot"
    ).json()
    history = client.get(
        "/api/v1/twin/assets/MTR-BMB-042/history?limit=10"
    ).json()

    assert {channel["sensorId"] for channel in snapshot["channels"]} == {
        "s1",
        "s2",
    }
    assert all(
        channel["measurements"]["temperature"] is not None
        for channel in snapshot["channels"]
    )
    assert len(history["items"]) == 4
    assert not any("raw" in item for item in history["items"])
