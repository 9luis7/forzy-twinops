from datetime import datetime, timezone

import httpx
import pytest

from twinops.config import Settings
from twinops.ingestion.collector import Collector
from twinops.ingestion.upstream import UpstreamClient, UpstreamFailure
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository


async def _completed_sleep(_: float):
    return None


@pytest.mark.parametrize("failure", ["timeout", "invalid_json"])
@pytest.mark.asyncio
async def test_upstream_timeout_and_invalid_json_are_bounded_and_sanitized(failure):
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        if failure == "timeout":
            raise httpx.ReadTimeout("secret endpoint timed out", request=request)
        return httpx.Response(200, content=b"{", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = UpstreamClient(
            http, "https://secret-upstream.invalid", 2.0, sleep=_completed_sleep
        )
        with pytest.raises(UpstreamFailure) as caught:
            await client.fetch("s1")

    assert calls == 2
    assert str(caught.value) == "upstream_unavailable"
    assert "secret-upstream" not in str(caught.value)


@pytest.mark.asyncio
async def test_s1_failure_does_not_block_s2_and_retry_is_limited(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path)
    repo.initialize()
    calls = {"s1": 0, "s2": 0}

    def handler(request: httpx.Request):
        sensor = request.url.path[-2:]
        calls[sensor] += 1
        if sensor == "s1":
            return httpx.Response(500, json={"detail": "internal"})
        return httpx.Response(
            200,
            json={
                "dados2": {
                    "Velocidade": 0.05,
                    "Aceleração": 0.0,
                    "Temperatura": 35,
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = UpstreamClient(
            http, settings.upstream_base_url, 2.0, sleep=_completed_sleep
        )
        result = await Collector(client, repo, settings.asset_tag).collect_slot(
            datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
        )

    assert result == {"s1": "failed", "s2": "stored"}
    assert calls == {"s1": 2, "s2": 1}
    assert [item.sensor_id for item in repo.latest(settings.asset_tag)] == ["s2"]
    assert repo.health("s1").error_code == "upstream_unavailable"


@pytest.mark.asyncio
async def test_duplicate_slot_keeps_both_raw_payloads_but_one_canonical(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path)
    repo.initialize()

    def handler(request: httpx.Request):
        sensor = request.url.path[-2:]
        return httpx.Response(
            200,
            json={
                f"dados{sensor[-1]}": {
                    "Velocidade": 0.05,
                    "Aceleração": 0.0,
                    "Temperatura": 35,
                }
            },
        )

    slot = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = UpstreamClient(
            http, settings.upstream_base_url, 2.0, sleep=_completed_sleep
        )
        collector = Collector(client, repo, settings.asset_tag)
        assert (await collector.collect_slot(slot))["s2"] == "stored"
        assert (await collector.collect_slot(slot))["s2"] == "duplicate"

    with repo._connect() as conn:
        assert (
            conn.execute(
                "select count(*) from raw_readings where sensor_id='s2'"
            ).fetchone()[0]
            == 2
        )
        assert (
            conn.execute(
                "select count(*) from telemetry_samples where sensor_id='s2'"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.asyncio
async def test_invalid_s1_payload_is_preserved_and_does_not_block_s2(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path)
    repo.initialize()

    def handler(request: httpx.Request):
        sensor = request.url.path[-2:]
        value = "not-a-number" if sensor == "s1" else 0.05
        return httpx.Response(
            200,
            json={
                f"dados{sensor[-1]}": {
                    "Velocidade": value,
                    "Aceleração": 0.0,
                    "Temperatura": 35,
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await Collector(
            UpstreamClient(
                http, settings.upstream_base_url, 2.0, sleep=_completed_sleep
            ),
            repo,
            settings.asset_tag,
        ).collect_slot(datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc))

    assert result == {"s1": "failed", "s2": "stored"}
    assert repo.health("s1").error_code == "invalid_payload"
    with repo._connect() as conn:
        assert conn.execute("select count(*) from raw_readings").fetchone()[0] == 2


@pytest.mark.asyncio
async def test_tick_does_not_write_outside_collection_window(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path)
    repo.initialize()
    calls = 0

    def handler(_: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        state = await Collector(
            UpstreamClient(http, settings.upstream_base_url, 2.0),
            repo,
            settings.asset_tag,
        ).tick(datetime(2026, 8, 13, 15, 0, tzinfo=timezone.utc))

    assert state == "expected_idle"
    assert calls == 0


@pytest.mark.asyncio
async def test_gigantic_s1_integer_becomes_invalid_payload_without_blocking_s2(tmp_path):
    settings = Settings("https://upstream.invalid", tmp_path / "telemetry.db")
    repo = SQLiteTelemetryRepository(settings.database_path)
    repo.initialize()

    def handler(request: httpx.Request):
        sensor = request.url.path[-2:]
        return httpx.Response(
            200,
            json={
                f"dados{sensor[-1]}": {
                    "Velocidade": 10**400 if sensor == "s1" else 0.05,
                    "Aceleração": 0.0,
                    "Temperatura": 35,
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await Collector(
            UpstreamClient(
                http, settings.upstream_base_url, 2.0, sleep=_completed_sleep
            ),
            repo,
            settings.asset_tag,
        ).collect_slot(datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc))

    assert result == {"s1": "failed", "s2": "stored"}
    assert repo.health("s1").error_code == "invalid_payload"
    assert [item.sensor_id for item in repo.latest(settings.asset_tag)] == ["s2"]
