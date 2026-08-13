import sqlite3
from datetime import datetime, timedelta, timezone
import json
import uuid

import pytest

from twinops.ingestion.live_adapter import adapt_live_payload
from twinops.storage.repository import CollectionAttempt, HistoryQuery, RawReading
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository
import twinops.storage.sqlite_repository as sqlite_repository_module


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


def csv_sample(*, observed_at, received_at, reading_id=None):
    live = sample()
    body = live.model_dump(mode="json", by_alias=True)
    body.update(
        readingId=reading_id or str(uuid.uuid4()),
        source="forzy-csv",
        scheduledAt=None,
        observedAt=observed_at,
        receivedAt=received_at,
        payloadHash=f"sha256:{uuid.uuid4().hex * 2}",
    )
    body["provenance"] = {
        "sourceSystem": "forzy-csv-import",
        "ingestedAt": received_at,
    }
    return type(live).model_validate(body)


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


def test_history_filters_and_orders_by_effective_timestamp_for_csv(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db")
    repo.initialize()
    repo.insert_sample(
        csv_sample(
            observed_at="2026-08-10T15:00:00Z",
            received_at="2026-08-12T18:00:00Z",
        )
    )
    repo.insert_sample(sample(seconds=5))

    filtered = repo.history(
        HistoryQuery(
            asset_tag="MTR-BMB-042",
            from_at=datetime(2026, 8, 12, 15, 0, 1, tzinfo=timezone.utc),
        )
    )

    assert [(item.source, item.received_at) for item in filtered] == [
        ("forzy-live", "2026-08-12T15:00:05Z")
    ]


def test_latest_uses_effective_timestamp_and_deterministic_tie_breakers(tmp_path):
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db")
    repo.initialize()
    repo.insert_sample(sample(seconds=5))
    repo.insert_sample(
        csv_sample(
            observed_at="2026-08-10T15:00:00Z",
            received_at="2026-08-13T15:00:00Z",
        )
    )
    tied_older_receive = csv_sample(
        observed_at="2026-08-14T15:00:00Z",
        received_at="2026-08-12T15:00:00Z",
        reading_id="00000000-0000-4000-8000-000000000001",
    )
    tied_newer_receive = csv_sample(
        observed_at="2026-08-14T15:00:00Z",
        received_at="2026-08-12T15:00:01Z",
        reading_id="00000000-0000-4000-8000-000000000002",
    )
    repo.insert_sample(tied_older_receive)
    repo.insert_sample(tied_newer_receive)

    latest = repo.latest("MTR-BMB-042")
    history = repo.history(HistoryQuery(asset_tag="MTR-BMB-042"))

    assert latest[0].reading_id == tied_newer_receive.reading_id
    assert [item.reading_id for item in history[:2]] == [
        tied_newer_receive.reading_id,
        tied_older_receive.reading_id,
    ]


def test_repository_explicitly_closes_every_connection(tmp_path, monkeypatch):
    real_connect = sqlite3.connect
    opened = []

    class TrackingConnection:
        def __init__(self, connection):
            object.__setattr__(self, "connection", connection)
            object.__setattr__(self, "closed", False)

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def __setattr__(self, name, value):
            if name in {"connection", "closed"}:
                object.__setattr__(self, name, value)
            else:
                setattr(self.connection, name, value)

        def close(self):
            object.__setattr__(self, "closed", True)
            self.connection.close()

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self.connection.__exit__(exc_type, exc_value, traceback)

    def connect(*args, **kwargs):
        tracked = TrackingConnection(real_connect(*args, **kwargs))
        opened.append(tracked)
        return tracked

    monkeypatch.setattr(sqlite_repository_module.sqlite3, "connect", connect)
    repo = SQLiteTelemetryRepository(tmp_path / "telemetry.db")
    repo.initialize()
    reading = sample()
    repo.insert_sample(reading)
    repo.append_raw(
        RawReading(
            raw_id=str(uuid.uuid4()),
            sensor_id="s1",
            scheduled_at=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
            received_at=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
            payload_hash=reading.payload_hash,
            payload=json.loads(json.dumps(reading.raw)),
        )
    )
    repo.record_attempt(
        CollectionAttempt(
            "s1",
            datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
            True,
            1,
            None,
        )
    )
    repo.history(HistoryQuery(asset_tag="MTR-BMB-042"))
    repo.latest("MTR-BMB-042")
    repo.health("s1")

    assert opened
    assert all(connection.closed for connection in opened)
