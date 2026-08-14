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


@pytest.fixture
def repo(tmp_path):
    repository = SQLiteTelemetryRepositoryV2(tmp_path / "telemetry-v2.db")
    repository.initialize()
    return repository


@pytest.fixture
def sample_factory():
    def make(
        *,
        reading_id: str,
        seconds: int = 0,
        microseconds: int = 0,
        velocity: float = 0.04,
        sensor_id: str = "s1",
    ):
        instant = datetime(2026, 8, 12, 15, tzinfo=timezone.utc) + timedelta(
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

    return make


def test_identical_payload_is_audited_but_not_a_second_sample(
    repo, sample_factory
):
    first = sample_factory(reading_id="11111111-1111-4111-8111-111111111111")
    second = sample_factory(
        reading_id="22222222-2222-4222-8222-222222222222", seconds=5
    )

    assert repo.insert_distinct_sample(first).stored is True
    result = repo.insert_distinct_sample(second)

    assert result.stored is False
    assert result.duplicate_of == first.reading_id
    assert (
        len(
            repo.history(
                HistoryQueryV2(asset_id="forzy-motor-01", sensor_id="s1")
            )
        )
        == 1
    )


def test_value_that_changes_and_returns_is_stored_as_three_points(
    repo, sample_factory
):
    samples = [
        sample_factory(
            reading_id="11111111-1111-4111-8111-111111111111",
            seconds=0,
            velocity=0.04,
        ),
        sample_factory(
            reading_id="22222222-2222-4222-8222-222222222222",
            seconds=5,
            velocity=0.08,
        ),
        sample_factory(
            reading_id="33333333-3333-4333-8333-333333333333",
            seconds=10,
            velocity=0.04,
        ),
    ]

    results = [repo.insert_distinct_sample(sample) for sample in samples]

    assert [result.stored for result in results] == [True, True, True]
    assert [
        item.measurements.vibration_velocity_rms.value
        for item in repo.history(
            HistoryQueryV2(asset_id="forzy-motor-01", sensor_id="s1")
        )
    ] == [0.04, 0.08, 0.04]


def test_repeated_raw_payloads_remain_in_audit_storage(repo, sample_factory):
    sample = sample_factory(
        reading_id="11111111-1111-4111-8111-111111111111"
    )
    payload = {
        "dados1": {
            "Velocidade": 0.04,
            "Aceleração": 0.0,
            "Temperatura": 34,
        }
    }
    instant = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    for raw_id, seconds in (
        ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 0),
        ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", 5),
    ):
        repo.append_raw(
            RawReadingV2(
                raw_id=raw_id,
                sensor_id="s1",
                scheduled_at=instant + timedelta(seconds=seconds),
                received_at=instant + timedelta(seconds=seconds),
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


def test_health_reports_latest_attempt_success_and_distinct_sample_count(
    repo, sample_factory
):
    instant = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    first = sample_factory(reading_id="11111111-1111-4111-8111-111111111111")
    duplicate = sample_factory(
        reading_id="22222222-2222-4222-8222-222222222222", seconds=5
    )
    repo.insert_distinct_sample(first)
    repo.insert_distinct_sample(duplicate)
    repo.record_attempt(
        CollectionAttemptV2("s1", instant, instant, True, 12, None)
    )
    repo.record_attempt(
        CollectionAttemptV2(
            "s1",
            instant + timedelta(seconds=5),
            instant + timedelta(seconds=6),
            False,
            17,
            "invalid_payload",
        )
    )

    health = repo.health("s1")

    assert health is not None
    assert health.last_attempt_at == instant + timedelta(seconds=6)
    assert health.last_success_at == instant
    assert health.latency_ms == 17
    assert health.error_code == "invalid_payload"
    assert health.sample_count == 1
    assert repo.health("s2") is None


def test_latest_returns_newest_distinct_reading_for_each_sensor(
    repo, sample_factory
):
    samples = [
        sample_factory(
            reading_id="11111111-1111-4111-8111-111111111111",
            sensor_id="s1",
        ),
        sample_factory(
            reading_id="22222222-2222-4222-8222-222222222222",
            sensor_id="s1",
            seconds=5,
            velocity=0.08,
        ),
        sample_factory(
            reading_id="33333333-3333-4333-8333-333333333333",
            sensor_id="s2",
            seconds=3,
        ),
    ]
    for sample in samples:
        repo.insert_distinct_sample(sample)

    latest = repo.latest("forzy-motor-01")

    assert [(item.sensor_id, item.reading_id) for item in latest] == [
        ("s1", "22222222-2222-4222-8222-222222222222"),
        ("s2", "33333333-3333-4333-8333-333333333333"),
    ]


def test_history_filters_orders_limits_and_validates_limit(repo, sample_factory):
    for seconds, reading_id in (
        (0, "11111111-1111-4111-8111-111111111111"),
        (5, "22222222-2222-4222-8222-222222222222"),
        (10, "33333333-3333-4333-8333-333333333333"),
    ):
        repo.insert_distinct_sample(
            sample_factory(
                reading_id=reading_id,
                seconds=seconds,
                velocity=0.04 + seconds,
            )
        )
    start = datetime(2026, 8, 12, 15, 0, 1, tzinfo=timezone.utc)

    result = repo.history(
        HistoryQueryV2(
            asset_id="forzy-motor-01",
            sensor_id="s1",
            from_at=start,
            limit=2,
        )
    )

    assert [item.observed_at for item in result] == [
        "2026-08-12T15:00:10Z",
        "2026-08-12T15:00:05Z",
    ]
    with pytest.raises(ValueError, match="between 1 and 1000"):
        repo.history(HistoryQueryV2(asset_id="forzy-motor-01", limit=0))


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


def test_concurrent_identical_insertions_store_only_one_sample(
    repo, sample_factory
):
    samples = [
        sample_factory(
            reading_id="11111111-1111-4111-8111-111111111111", seconds=0
        ),
        sample_factory(
            reading_id="22222222-2222-4222-8222-222222222222", seconds=5
        ),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(repo.insert_distinct_sample, samples))

    assert sorted(result.stored for result in results) == [False, True]
    assert len(repo.history(HistoryQueryV2(asset_id="forzy-motor-01"))) == 1


def test_consecutive_dedupe_is_independent_per_sensor(repo, sample_factory):
    readings = [
        sample_factory(
            reading_id="11111111-1111-4111-8111-111111111111",
            sensor_id="s1",
        ),
        sample_factory(
            reading_id="22222222-2222-4222-8222-222222222222",
            sensor_id="s2",
        ),
        sample_factory(
            reading_id="33333333-3333-4333-8333-333333333333",
            sensor_id="s1",
            seconds=5,
        ),
        sample_factory(
            reading_id="44444444-4444-4444-8444-444444444444",
            sensor_id="s2",
            seconds=5,
        ),
    ]

    results = [repo.insert_distinct_sample(reading) for reading in readings]

    assert [result.stored for result in results] == [True, True, False, False]
    assert len(repo.history(HistoryQueryV2(asset_id="forzy-motor-01"))) == 2


def test_same_second_fractional_instants_keep_temporal_order_for_dedupe(
    repo, sample_factory
):
    readings = [
        sample_factory(
            reading_id="11111111-1111-4111-8111-111111111111",
            microseconds=0,
            velocity=0.04,
        ),
        sample_factory(
            reading_id="22222222-2222-4222-8222-222222222222",
            microseconds=500_000,
            velocity=0.08,
        ),
        sample_factory(
            reading_id="33333333-3333-4333-8333-333333333333",
            microseconds=750_000,
            velocity=0.04,
        ),
    ]

    results = [repo.insert_distinct_sample(reading) for reading in readings]
    history = repo.history(HistoryQueryV2(asset_id="forzy-motor-01"))

    assert [result.stored for result in results] == [True, True, True]
    assert [reading.reading_id for reading in history] == [
        "33333333-3333-4333-8333-333333333333",
        "22222222-2222-4222-8222-222222222222",
        "11111111-1111-4111-8111-111111111111",
    ]
    assert repo.latest("forzy-motor-01")[0].reading_id == history[0].reading_id


def test_same_second_fractional_attempts_keep_latest_and_last_success(repo):
    instant = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    attempts = [
        CollectionAttemptV2("s1", instant, instant, True, 10, None),
        CollectionAttemptV2(
            "s1",
            instant + timedelta(microseconds=500_000),
            instant + timedelta(microseconds=500_000),
            True,
            12,
            None,
        ),
        CollectionAttemptV2(
            "s1",
            instant + timedelta(microseconds=750_000),
            instant + timedelta(microseconds=750_000),
            False,
            17,
            "invalid_payload",
        ),
    ]
    for attempt in attempts:
        repo.record_attempt(attempt)

    health = repo.health("s1")

    assert health is not None
    assert health.last_attempt_at == instant + timedelta(microseconds=750_000)
    assert health.last_success_at == instant + timedelta(microseconds=500_000)
    assert health.latency_ms == 17
    assert health.error_code == "invalid_payload"
