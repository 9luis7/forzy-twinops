import asyncio
from datetime import datetime, timedelta, timezone
import sqlite3
from unittest.mock import AsyncMock, Mock

import pytest

from twinops.ingestion.refresh_service import RefreshService
from twinops.ingestion.upstream import FetchResult, UpstreamFailure
from twinops.storage.sqlite_v2_repository import SQLiteTelemetryRepositoryV2
from twinops.storage.v2_repository import HistoryQueryV2


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
    second = await service.refresh(WEDNESDAY_WINDOW + timedelta(seconds=5))

    assert first.outcomes == {"s1": "stored", "s2": "stored"}
    assert second.outcomes == {"s1": "unchanged", "s2": "unchanged"}
    latest = repo.latest("forzy-motor-01")
    assert len(latest) == 2
    assert all(item.scheduled_at == "2026-08-12T15:00:05Z" for item in latest)
    assert all(item.observed_at == item.received_at for item in latest)
    assert all(item.received_at != item.scheduled_at for item in latest)
    trend = repo.history(
        HistoryQueryV2(asset_id="forzy-motor-01", sensor_id="s1")
    )
    assert len(trend) == 1
    assert trend[0].scheduled_at == "2026-08-12T15:00:00Z"
    assert latest[0].received_at > trend[0].received_at
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_readings_v2"
        ).fetchone()[0] == 4
        attempts = connection.execute(
            "SELECT scheduled_at, succeeded, error_code "
            "FROM collection_attempts_v2 ORDER BY sensor_id, attempted_at"
        ).fetchall()
    assert len(attempts) == 4
    assert [row[0] for row in attempts] == [
        "2026-08-12T15:00:00.000000Z",
        "2026-08-12T15:00:05.000000Z",
        "2026-08-12T15:00:00.000000Z",
        "2026-08-12T15:00:05.000000Z",
    ]
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
    assert repo.health("s1").latency_ms == 13
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
    assert repo.health("s1").latency_ms == 7
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
    assert repo.health("s1").latency_ms == 7
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute(
            "SELECT sensor_id FROM raw_readings_v2"
        ).fetchall() == [("s2",)]
        assert connection.execute(
            "SELECT error_code FROM collection_attempts_v2 WHERE sensor_id='s1'"
        ).fetchall() == [("invalid_payload",)]


@pytest.mark.asyncio
async def test_completed_failed_slot_is_reused_and_next_slot_retries(
    service, upstream, repo
):
    upstream.fetch.side_effect = UpstreamFailure(
        "upstream_unavailable", latency_ms=21
    )

    first = await service.refresh(WEDNESDAY_WINDOW)
    replay = await service.refresh(WEDNESDAY_WINDOW)
    next_slot = await service.refresh(WEDNESDAY_WINDOW + timedelta(seconds=5))

    assert first.outcomes == {"s1": "failed", "s2": "failed"}
    assert replay.outcomes == first.outcomes
    assert replay.completed_at == first.completed_at
    assert next_slot.outcomes == {"s1": "failed", "s2": "failed"}
    assert upstream.fetch.await_count == 4
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_attempts_v2"
        ).fetchone()[0] == 4
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_readings_v2"
        ).fetchone()[0] == 0


@pytest.mark.asyncio
async def test_concurrent_callers_await_the_cycle_owner_without_fetching(repo):
    owner_upstream = Mock(fetch=AsyncMock())
    waiter_upstream = Mock(fetch=AsyncMock())
    both_started = asyncio.Event()
    release = asyncio.Event()
    started = 0

    async def fetch(sensor_id):
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await release.wait()
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

    owner_upstream.fetch.side_effect = fetch
    owner = RefreshService(owner_upstream, repo, claim_poll_seconds=0.001)
    waiter = RefreshService(waiter_upstream, repo, claim_poll_seconds=0.001)

    owner_task = asyncio.create_task(owner.refresh(WEDNESDAY_WINDOW))
    await asyncio.wait_for(both_started.wait(), timeout=0.5)
    waiter_task = asyncio.create_task(waiter.refresh(WEDNESDAY_WINDOW))
    await asyncio.sleep(0.02)
    release.set()
    owner_result, waiter_result = await asyncio.gather(owner_task, waiter_task)

    assert owner_result.outcomes == {"s1": "stored", "s2": "stored"}
    assert waiter_result == owner_result
    assert owner_upstream.fetch.await_count == 2
    waiter_upstream.fetch.assert_not_awaited()
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_readings_v2"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM collection_attempts_v2"
        ).fetchone()[0] == 2


@pytest.mark.asyncio
async def test_completion_clock_is_not_earlier_than_any_received_reading(
    upstream, repo
):
    class IncrementingClock:
        def __init__(self):
            self.value = WEDNESDAY_WINDOW + timedelta(seconds=1)

        def __call__(self):
            self.value += timedelta(milliseconds=1)
            return self.value

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
            latency_ms=5,
        )

    upstream.fetch.side_effect = fetch
    service = RefreshService(upstream, repo, clock=IncrementingClock())

    result = await service.refresh(WEDNESDAY_WINDOW)

    received = [
        datetime.fromisoformat(item.received_at.replace("Z", "+00:00"))
        for item in repo.latest("forzy-motor-01")
    ]
    assert result.completed_at >= max(received)
