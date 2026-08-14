from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from twinops.ingestion.live_adapter_v2 import adapt_live_payload_v2
from twinops.storage.sqlite_v2_repository import SQLiteTelemetryRepositoryV2
from twinops.storage.v2_repository import (
    CollectionAttemptV2,
    HistoryQueryV2,
    RawReadingV2,
)


_BASE_INSTANT = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_path):
    repository = SQLiteTelemetryRepositoryV2(tmp_path / "telemetry-v2.db")
    repository.initialize()
    return repository


def _make_sample(
    *,
    reading_id: str,
    seconds: int = 0,
    microseconds: int = 0,
    velocity: float = 0.04,
    sensor_id: str = "s1",
):
    instant = _BASE_INSTANT + timedelta(
        seconds=seconds, microseconds=microseconds
    )
    root = "dados1" if sensor_id == "s1" else "dados2"
    reading = adapt_live_payload_v2(
        sensor_id=sensor_id,
        payload={
            root: {
                "Velocidade": velocity,
                "Aceleração": 0.0,
                "Temperatura": 34,
            }
        },
        scheduled_at=instant,
        received_at=instant,
    )
    body = reading.model_dump(mode="json", by_alias=True)
    body["readingId"] = reading_id
    return type(reading).model_validate(body)


def repository_contract(repo):
    first = _make_sample(
        reading_id="11111111-1111-4111-8111-111111111111"
    )
    duplicate = _make_sample(
        reading_id="22222222-2222-4222-8222-222222222222", seconds=5
    )

    assert repo.insert_distinct_sample(first).stored is True
    result = repo.insert_distinct_sample(duplicate)

    assert result.stored is False
    assert result.duplicate_of == first.reading_id
    assert len(
        repo.history(HistoryQueryV2(asset_id="forzy-motor-01", sensor_id="s1"))
    ) == 1

    changed = _make_sample(
        reading_id="33333333-3333-4333-8333-333333333333",
        seconds=10,
        velocity=0.08,
    )
    returned = _make_sample(
        reading_id="44444444-4444-4444-8444-444444444444",
        seconds=15,
        velocity=0.04,
    )
    results = [
        repo.insert_distinct_sample(changed),
        repo.insert_distinct_sample(returned),
    ]

    assert [item.stored for item in results] == [True, True]
    assert [
        item.measurements.vibration_velocity_rms.value
        for item in repo.history(
            HistoryQueryV2(asset_id="forzy-motor-01", sensor_id="s1")
        )
    ] == [0.04, 0.08, 0.04]

    raw_sample = _make_sample(
        reading_id="55555555-5555-4555-8555-555555555555",
        seconds=20,
        velocity=0.12,
    )
    payload = {
        "dados1": {
            "Velocidade": 0.12,
            "Aceleração": 0.0,
            "Temperatura": 34,
        }
    }
    for raw_id, seconds in (
        ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 20),
        ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", 25),
    ):
        instant = _BASE_INSTANT + timedelta(seconds=seconds)
        repo.append_raw(
            RawReadingV2(
                raw_id=raw_id,
                sensor_id="s1",
                scheduled_at=instant,
                received_at=instant,
                payload_hash=raw_sample.payload_hash,
                payload=payload,
            )
        )
    assert repo.insert_distinct_sample(raw_sample).stored is True
    assert repo.history(
        HistoryQueryV2(
            asset_id="forzy-motor-01",
            sensor_id="s1",
            from_at=_BASE_INSTANT + timedelta(seconds=20),
        )
    )[0].raw.model_dump() == {}

    repo.record_attempt(
        CollectionAttemptV2("s1", _BASE_INSTANT, _BASE_INSTANT, True, 12, None)
    )
    repo.record_attempt(
        CollectionAttemptV2(
            "s1",
            _BASE_INSTANT + timedelta(seconds=5),
            _BASE_INSTANT + timedelta(seconds=6),
            False,
            17,
            "invalid_payload",
        )
    )

    health = repo.health("s1")
    assert health is not None
    assert health.last_attempt_at == _BASE_INSTANT + timedelta(seconds=6)
    assert health.last_success_at == _BASE_INSTANT
    assert health.latency_ms == 17
    assert health.error_code == "invalid_payload"
    assert health.sample_count == 4
    assert repo.health("s2") is None

    sensor_two = _make_sample(
        reading_id="66666666-6666-4666-8666-666666666666",
        sensor_id="s2",
        seconds=3,
    )
    repo.insert_distinct_sample(sensor_two)

    latest = repo.latest("forzy-motor-01")
    assert [(item.sensor_id, item.reading_id) for item in latest] == [
        ("s1", raw_sample.reading_id),
        ("s2", sensor_two.reading_id),
    ]

    for seconds, reading_id in (
        (30, "77777777-7777-4777-8777-777777777777"),
        (35, "88888888-8888-4888-8888-888888888888"),
        (40, "99999999-9999-4999-8999-999999999999"),
    ):
        repo.insert_distinct_sample(
            _make_sample(
                reading_id=reading_id,
                seconds=seconds,
                velocity=0.04 + seconds,
            )
        )
    history = repo.history(
        HistoryQueryV2(
            asset_id="forzy-motor-01",
            sensor_id="s1",
            from_at=_BASE_INSTANT + timedelta(seconds=31),
            limit=2,
        )
    )

    assert [item.observed_at for item in history] == [
        "2026-08-12T15:00:40Z",
        "2026-08-12T15:00:35Z",
    ]
    with pytest.raises(ValueError, match="between 1 and 1000"):
        repo.history(HistoryQueryV2(asset_id="forzy-motor-01", limit=0))

    concurrent_samples = [
        _make_sample(
            reading_id="aaaaaaaa-1111-4111-8111-111111111111",
            sensor_id="s2",
            seconds=50,
            velocity=0.16,
        ),
        _make_sample(
            reading_id="bbbbbbbb-2222-4222-8222-222222222222",
            sensor_id="s2",
            seconds=55,
            velocity=0.16,
        ),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent_results = list(
            executor.map(repo.insert_distinct_sample, concurrent_samples)
        )

    assert sorted(item.stored for item in concurrent_results) == [False, True]
    assert len(
        repo.history(HistoryQueryV2(asset_id="forzy-motor-01", sensor_id="s2"))
    ) == 2

    independent_readings = [
        _make_sample(
            reading_id="cccccccc-3333-4333-8333-333333333333",
            sensor_id="s1",
            seconds=60,
            velocity=0.20,
        ),
        _make_sample(
            reading_id="dddddddd-4444-4444-8444-444444444444",
            sensor_id="s2",
            seconds=60,
            velocity=0.20,
        ),
        _make_sample(
            reading_id="eeeeeeee-5555-4555-8555-555555555555",
            sensor_id="s1",
            seconds=65,
            velocity=0.20,
        ),
        _make_sample(
            reading_id="ffffffff-6666-4666-8666-666666666666",
            sensor_id="s2",
            seconds=65,
            velocity=0.20,
        ),
    ]
    independent_results = [
        repo.insert_distinct_sample(reading) for reading in independent_readings
    ]

    assert [item.stored for item in independent_results] == [
        True,
        True,
        False,
        False,
    ]

    fractional_readings = [
        _make_sample(
            reading_id="12345678-1111-4111-8111-111111111111",
            seconds=70,
            velocity=0.24,
        ),
        _make_sample(
            reading_id="12345678-2222-4222-8222-222222222222",
            seconds=70,
            microseconds=500_000,
            velocity=0.28,
        ),
        _make_sample(
            reading_id="12345678-3333-4333-8333-333333333333",
            seconds=70,
            microseconds=750_000,
            velocity=0.24,
        ),
    ]
    fractional_results = [
        repo.insert_distinct_sample(reading) for reading in fractional_readings
    ]
    fractional_history = repo.history(
        HistoryQueryV2(
            asset_id="forzy-motor-01",
            sensor_id="s1",
            from_at=_BASE_INSTANT + timedelta(seconds=70),
        )
    )

    assert [item.stored for item in fractional_results] == [True, True, True]
    assert [item.reading_id for item in fractional_history] == [
        "12345678-3333-4333-8333-333333333333",
        "12345678-2222-4222-8222-222222222222",
        "12345678-1111-4111-8111-111111111111",
    ]
    assert repo.latest("forzy-motor-01")[0].reading_id == fractional_history[0].reading_id

    attempts = [
        CollectionAttemptV2(
            "s1",
            _BASE_INSTANT + timedelta(seconds=80),
            _BASE_INSTANT + timedelta(seconds=80),
            True,
            10,
            None,
        ),
        CollectionAttemptV2(
            "s1",
            _BASE_INSTANT + timedelta(seconds=80, microseconds=500_000),
            _BASE_INSTANT + timedelta(seconds=80, microseconds=500_000),
            True,
            12,
            None,
        ),
        CollectionAttemptV2(
            "s1",
            _BASE_INSTANT + timedelta(seconds=80, microseconds=750_000),
            _BASE_INSTANT + timedelta(seconds=80, microseconds=750_000),
            False,
            17,
            "invalid_payload",
        ),
    ]
    for attempt in attempts:
        repo.record_attempt(attempt)

    health = repo.health("s1")
    assert health is not None
    assert health.last_attempt_at == _BASE_INSTANT + timedelta(
        seconds=80, microseconds=750_000
    )
    assert health.last_success_at == _BASE_INSTANT + timedelta(
        seconds=80, microseconds=500_000
    )
    assert health.latency_ms == 17
    assert health.error_code == "invalid_payload"


def test_sqlite_repository_satisfies_shared_contract(repo):
    repository_contract(repo)


def test_repeated_raw_payloads_remain_in_sqlite_audit_storage(repo):
    sample = _make_sample(
        reading_id="11111111-1111-4111-8111-111111111111"
    )
    payload = {
        "dados1": {
            "Velocidade": 0.04,
            "Aceleração": 0.0,
            "Temperatura": 34,
        }
    }
    for raw_id, seconds in (
        ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 0),
        ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", 5),
    ):
        instant = _BASE_INSTANT + timedelta(seconds=seconds)
        repo.append_raw(
            RawReadingV2(
                raw_id=raw_id,
                sensor_id="s1",
                scheduled_at=instant,
                received_at=instant,
                payload_hash=sample.payload_hash,
                payload=payload,
            )
        )
    repo.insert_distinct_sample(sample)

    with sqlite3.connect(repo.path) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM raw_readings_v2 ORDER BY scheduled_at"
        ).fetchall()
        canonical = json.loads(
            connection.execute(
                "SELECT canonical_json FROM telemetry_samples_v2"
            ).fetchone()[0]
        )

    assert len(rows) == 2
    assert [json.loads(row[0]) for row in rows] == [payload, payload]
    assert canonical["raw"] == {}
    assert "dados1" not in canonical


def test_initialize_creates_wal_v2_schema_and_history_index(repo):
    with sqlite3.connect(repo.path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert {
        "telemetry_samples_v2",
        "raw_readings_v2",
        "collection_attempts_v2",
    } <= tables
    assert "ix_telemetry_samples_v2_history" in indexes
    assert journal_mode == "wal"
