import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from twinops.ingestion.live_adapter import adapt_live_payload
from twinops.storage.repository import CollectionAttempt, HistoryQuery
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository


def sample(sensor_id="s1", seconds=0):
    slot = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc) + timedelta(
        seconds=seconds
    )
    root = "dados1" if sensor_id == "s1" else "dados2"
    return adapt_live_payload(
        sensor_id=sensor_id,
        payload={
            root: {
                "Velocidade": 0.04,
                "Aceleração": 0.0,
                "Temperatura": 34,
            }
        },
        scheduled_at=slot,
        received_at=slot,
        asset_tag="MTR-BMB-042",
    )


def test_initializes_wal_indexes_and_live_slot_is_idempotent(tmp_path):
    db = tmp_path / "telemetry.db"
    repo = SQLiteTelemetryRepository(db)
    repo.initialize()

    live_sample = sample()
    assert repo.insert_sample(live_sample) is True
    assert repo.insert_sample(sample()) is False

    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("select count(*) from telemetry_samples").fetchone()[0] == 1
        indexes = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='index'"
            ).fetchall()
        }
        assert {"ux_live_slot", "ux_csv_row", "ix_history"} <= indexes


def test_history_filters_orders_limits_and_validates_limit(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db")
    repo.initialize()
    for reading in [sample(seconds=10), sample(seconds=0), sample(seconds=5)]:
        repo.insert_sample(reading)

    result = repo.history(
        HistoryQuery(asset_tag="MTR-BMB-042", sensor_id="s1", limit=2)
    )

    assert [reading.received_at for reading in result] == sorted(
        [reading.received_at for reading in result], reverse=True
    )
    assert len(result) == 2
    with pytest.raises(ValueError, match="between 1 and 1000"):
        repo.history(HistoryQuery(asset_tag="MTR-BMB-042", limit=0))


def test_latest_and_health_are_independent_per_sensor(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db")
    repo.initialize()
    repo.insert_sample(sample("s1", seconds=0))
    repo.insert_sample(sample("s1", seconds=5))
    repo.insert_sample(sample("s2", seconds=0))
    attempted = datetime(2026, 8, 12, 15, 0, 6, tzinfo=timezone.utc)
    repo.record_attempt(
        CollectionAttempt("s1", attempted, attempted, False, 17, "invalid_payload")
    )

    latest = repo.latest("MTR-BMB-042")
    assert {(item.sensor_id, item.received_at) for item in latest} == {
        ("s1", "2026-08-12T15:00:05Z"),
        ("s2", "2026-08-12T15:00:00Z"),
    }
    assert repo.health("s1").error_code == "invalid_payload"
    assert repo.health("s1").sample_count == 2
    assert repo.health("unknown") is None
