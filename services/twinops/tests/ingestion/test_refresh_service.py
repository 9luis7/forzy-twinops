import asyncio
from datetime import datetime, timezone
import sqlite3
from unittest.mock import AsyncMock, Mock

import pytest

from twinops.ingestion.refresh_service import RefreshService
from twinops.ingestion.upstream import FetchResult, UpstreamFailure
from twinops.storage.sqlite_v2_repository import SQLiteTelemetryRepositoryV2


WEDNESDAY_WINDOW = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)


@pytest.fixture
def upstream():
    return Mock(fetch=AsyncMock())


@pytest.fixture
def repo(tmp_path):
    repository = SQLiteTelemetryRepositoryV2(tmp_path / "telemetry-v2.db")
    repository.initialize()
    return repository


@pytest.fixture
def service(upstream, repo):
    return RefreshService(upstream, repo)


@pytest.mark.asyncio
async def test_outside_window_does_not_call_upstream(service, upstream, repo):
    result = await service.refresh(
        datetime(2026, 8, 13, 16, tzinfo=timezone.utc)
    )

    assert result.refresh_attempted is False
    assert result.outcomes == {}
    upstream.fetch.assert_not_called()
    assert repo.health("s1") is None
    assert repo.health("s2") is None


@pytest.mark.asyncio
async def test_refresh_starts_both_sensor_requests_concurrently(service, upstream):
    started = 0
    both_started = asyncio.Event()

    async def fetch(sensor_id):
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.5)
        suffix = sensor_id[-1]
        return FetchResult(
            payload={
                f"dados{suffix}": {
                    "Velocidade": 0.04,
                    "Acelera\u00e7\u00e3o": 0.0,
                    "Temperatura": 34,
                }
            },
            latency_ms=12,
        )

    upstream.fetch.side_effect = fetch

    result = await service.refresh(WEDNESDAY_WINDOW)

    assert result.refresh_attempted is True
    assert result.outcomes == {"s1": "stored", "s2": "stored"}


@pytest.mark.asyncio
async def test_s1_failure_does_not_discard_s2(service, upstream, repo):
    async def fetch(sensor_id):
        if sensor_id == "s1":
            raise UpstreamFailure("upstream_unavailable", latency_ms=17)
        return FetchResult(
            payload={
                "dados2": {
                    "Velocidade": 0.05,
                    "Acelera\u00e7\u00e3o": 0.0,
                    "Temperatura": 35,
                }
            },
            latency_ms=11,
        )

    upstream.fetch.side_effect = fetch

    result = await service.refresh(WEDNESDAY_WINDOW)

    assert result.outcomes == {"s1": "failed", "s2": "stored"}
    assert [item.sensor_id for item in repo.latest("forzy-motor-01")] == ["s2"]
    assert repo.health("s1").error_code == "upstream_unavailable"
    assert repo.health("s1").latency_ms == 17
    assert repo.health("s2").error_code is None


@pytest.mark.asyncio
async def test_repeated_payload_is_unchanged_but_keeps_raw_and_attempt_audit(
    service, upstream, repo
):
    async def fetch(sensor_id):
        suffix = sensor_id[-1]
        return FetchResult(
            payload={
                f"dados{suffix}": {
                    "Velocidade": 0.04,
                    "Acelera\u00e7\u00e3o": 0.0,
                    "Temperatura": 34,
                }
            },
            latency_ms=9,
        )

    upstream.fetch.side_effect = fetch

    first = await service.refresh(WEDNESDAY_WINDOW)
    second = await service.refresh(WEDNESDAY_WINDOW)

    assert first.outcomes == {"s1": "stored", "s2": "stored"}
    assert second.outcomes == {"s1": "unchanged", "s2": "unchanged"}
    latest = repo.latest("forzy-motor-01")
    assert len(latest) == 2
    assert all(item.scheduled_at == "2026-08-12T15:00:00Z" for item in latest)
    assert all(item.observed_at == item.received_at for item in latest)
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_readings_v2"
        ).fetchone()[0] == 4
        attempts = connection.execute(
            "SELECT scheduled_at, succeeded, error_code "
            "FROM collection_attempts_v2 ORDER BY sensor_id, attempted_at"
        ).fetchall()
    assert len(attempts) == 4
    assert all(row[0] == "2026-08-12T15:00:00.000000Z" for row in attempts)
    assert all(row[1:] == (1, None) for row in attempts)


@pytest.mark.asyncio
async def test_invalid_sensor_payload_is_audited_without_blocking_peer(
    service, upstream, repo
):
    async def fetch(sensor_id):
        suffix = sensor_id[-1]
        return FetchResult(
            payload={
                f"dados{suffix}": {
                    "Velocidade": "invalid" if sensor_id == "s1" else 0.05,
                    "Acelera\u00e7\u00e3o": 0.0,
                    "Temperatura": 35,
                }
            },
            latency_ms=13,
        )

    upstream.fetch.side_effect = fetch

    result = await service.refresh(WEDNESDAY_WINDOW)

    assert result.outcomes == {"s1": "failed", "s2": "stored"}
    assert repo.health("s1").error_code == "invalid_payload"
    assert [item.sensor_id for item in repo.latest("forzy-motor-01")] == ["s2"]
    with sqlite3.connect(repo.path) as connection:
        raw_sensors = connection.execute(
            "SELECT sensor_id FROM raw_readings_v2 ORDER BY sensor_id"
        ).fetchall()
    assert raw_sensors == [("s1",), ("s2",)]


@pytest.mark.asyncio
async def test_non_object_payload_is_failed_without_raw_leak(service, upstream, repo):
    async def fetch(sensor_id):
        if sensor_id == "s1":
            return FetchResult(payload=["unsafe"], latency_ms=7)
        return FetchResult(
            payload={
                "dados2": {
                    "Velocidade": 0.05,
                    "Acelera\u00e7\u00e3o": 0.0,
                    "Temperatura": 35,
                }
            },
            latency_ms=8,
        )

    upstream.fetch.side_effect = fetch

    result = await service.refresh(WEDNESDAY_WINDOW)

    assert result.outcomes == {"s1": "failed", "s2": "stored"}
    assert repo.health("s1").error_code == "invalid_payload"
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute(
            "SELECT sensor_id FROM raw_readings_v2"
        ).fetchall() == [("s2",)]
        error_codes = connection.execute(
            "SELECT error_code FROM collection_attempts_v2 "
            "WHERE sensor_id='s1'"
        ).fetchall()
    assert error_codes == [("invalid_payload",)]


@pytest.mark.asyncio
async def test_non_json_object_is_failed_before_raw_storage(service, upstream, repo):
    async def fetch(sensor_id):
        if sensor_id == "s1":
            return FetchResult(
                payload={"dados1": {"Velocidade": {"secret-host"}}},
                latency_ms=7,
            )
        return FetchResult(
            payload={
                "dados2": {
                    "Velocidade": 0.05,
                    "Acelera\u00e7\u00e3o": 0.0,
                    "Temperatura": 35,
                }
            },
            latency_ms=8,
        )

    upstream.fetch.side_effect = fetch

    result = await service.refresh(WEDNESDAY_WINDOW)

    assert result.outcomes == {"s1": "failed", "s2": "stored"}
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute(
            "SELECT sensor_id FROM raw_readings_v2"
        ).fetchall() == [("s2",)]
        assert connection.execute(
            "SELECT error_code FROM collection_attempts_v2 WHERE sensor_id='s1'"
        ).fetchall() == [("invalid_payload",)]
