"""Append-only SQLite repository using parameterized SQL and canonical JSON."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from twinops.contracts.models import CanonicalSensorReading
from twinops.storage.repository import (
    CollectionAttempt,
    HistoryQuery,
    RawReading,
    SensorHealth,
)


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS telemetry_samples (
  reading_id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, source TEXT NOT NULL,
  asset_tag TEXT NOT NULL, sensor_id TEXT NOT NULL, scheduled_at TEXT,
  received_at TEXT NOT NULL, observed_at TEXT, velocity REAL NOT NULL,
  acceleration REAL NOT NULL, temperature REAL NOT NULL,
  velocity_unit TEXT NOT NULL, acceleration_unit TEXT NOT NULL,
  temperature_unit TEXT NOT NULL, velocity_confidence TEXT NOT NULL,
  acceleration_statistic TEXT NOT NULL, acceleration_confidence TEXT NOT NULL,
  temperature_confidence TEXT NOT NULL, quality_flags_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL, raw_json TEXT NOT NULL, canonical_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_live_slot
ON telemetry_samples(source, sensor_id, scheduled_at)
WHERE source = 'forzy-live' AND scheduled_at IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_csv_row
ON telemetry_samples(source, sensor_id, payload_hash)
WHERE source = 'forzy-csv';
CREATE INDEX IF NOT EXISTS ix_history
ON telemetry_samples(asset_tag, sensor_id, received_at DESC);
CREATE TABLE IF NOT EXISTS raw_readings (
  raw_id TEXT PRIMARY KEY, sensor_id TEXT NOT NULL, scheduled_at TEXT NOT NULL,
  received_at TEXT NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_raw_slot
ON raw_readings(sensor_id, scheduled_at);
CREATE TABLE IF NOT EXISTS collection_attempts (
  attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, sensor_id TEXT NOT NULL,
  scheduled_at TEXT NOT NULL, attempted_at TEXT NOT NULL, succeeded INTEGER NOT NULL,
  latency_ms INTEGER, error_code TEXT
);
"""


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SQLiteTelemetryRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript(SCHEMA_SQL)

    def append_raw(self, reading: RawReading) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO raw_readings "
                "(raw_id,sensor_id,scheduled_at,received_at,payload_hash,payload_json) "
                "VALUES (?,?,?,?,?,?)",
                (
                    reading.raw_id,
                    reading.sensor_id,
                    _timestamp(reading.scheduled_at),
                    _timestamp(reading.received_at),
                    reading.payload_hash,
                    json.dumps(
                        reading.payload, ensure_ascii=False, sort_keys=True
                    ),
                ),
            )

    def insert_sample(self, sample: CanonicalSensorReading) -> bool:
        body = sample.model_dump(mode="json", by_alias=True)
        measurements = body["measurements"]
        values = (
            body["readingId"],
            body["schemaVersion"],
            body["source"],
            body["assetTag"],
            body["sensorId"],
            body["scheduledAt"],
            body["receivedAt"],
            body["observedAt"],
            measurements["vibrationVelocityRms"]["value"],
            measurements["vibrationAcceleration"]["value"],
            measurements["temperature"]["value"],
            measurements["vibrationVelocityRms"]["unit"],
            measurements["vibrationAcceleration"]["unit"],
            measurements["temperature"]["unit"],
            measurements["vibrationVelocityRms"]["semanticConfidence"],
            measurements["vibrationAcceleration"]["statistic"],
            measurements["vibrationAcceleration"]["semanticConfidence"],
            measurements["temperature"]["semanticConfidence"],
            json.dumps(body["qualityFlags"]),
            body["payloadHash"],
            json.dumps(body["raw"], ensure_ascii=False, sort_keys=True),
            json.dumps(body, ensure_ascii=False, sort_keys=True),
        )
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO telemetry_samples VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT DO NOTHING",
                values,
            )
            return cursor.rowcount == 1

    def record_attempt(self, attempt: CollectionAttempt) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO collection_attempts "
                "(sensor_id,scheduled_at,attempted_at,succeeded,latency_ms,error_code) "
                "VALUES (?,?,?,?,?,?)",
                (
                    attempt.sensor_id,
                    _timestamp(attempt.scheduled_at),
                    _timestamp(attempt.attempted_at),
                    int(attempt.succeeded),
                    attempt.latency_ms,
                    attempt.error_code,
                ),
            )

    def history(self, query: HistoryQuery) -> list[CanonicalSensorReading]:
        if not 1 <= query.limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        where = ["asset_tag = ?"]
        params: list[object] = [query.asset_tag]
        optional = (
            (query.sensor_id, "sensor_id = ?"),
            (query.source, "source = ?"),
            (
                _timestamp(query.from_at) if query.from_at else None,
                "COALESCE(observed_at, received_at) >= ?",
            ),
            (
                _timestamp(query.to_at) if query.to_at else None,
                "COALESCE(observed_at, received_at) <= ?",
            ),
        )
        for value, clause in optional:
            if value is not None:
                where.append(clause)
                params.append(value)
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT canonical_json FROM telemetry_samples WHERE "
                + " AND ".join(where)
                + " ORDER BY COALESCE(observed_at, received_at) DESC, "
                "received_at DESC, reading_id DESC LIMIT ?",
                (*params, query.limit),
            ).fetchall()
        return [
            CanonicalSensorReading.model_validate(json.loads(row[0])) for row in rows
        ]

    def latest(self, asset_tag: str) -> list[CanonicalSensorReading]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT canonical_json FROM ("
                "SELECT canonical_json, sensor_id, ROW_NUMBER() OVER ("
                "PARTITION BY sensor_id ORDER BY "
                "COALESCE(observed_at, received_at) DESC, "
                "received_at DESC, reading_id DESC) AS position "
                "FROM telemetry_samples WHERE asset_tag=?"
                ") WHERE position=1 ORDER BY sensor_id",
                (asset_tag,),
            ).fetchall()
        return [
            CanonicalSensorReading.model_validate(json.loads(row[0])) for row in rows
        ]

    def health(self, sensor_id: str) -> SensorHealth | None:
        with self._connection() as conn:
            latest = conn.execute(
                "SELECT attempted_at, latency_ms, error_code FROM collection_attempts "
                "WHERE sensor_id=? ORDER BY attempted_at DESC, attempt_id DESC LIMIT 1",
                (sensor_id,),
            ).fetchone()
            success = conn.execute(
                "SELECT MAX(attempted_at) FROM collection_attempts "
                "WHERE sensor_id=? AND succeeded=1",
                (sensor_id,),
            ).fetchone()[0]
            count = conn.execute(
                "SELECT COUNT(*) FROM telemetry_samples WHERE sensor_id=?",
                (sensor_id,),
            ).fetchone()[0]
        if latest is None and count == 0:
            return None
        return SensorHealth(
            sensor_id=sensor_id,
            last_attempt_at=_parse_timestamp(latest["attempted_at"])
            if latest
            else None,
            last_success_at=_parse_timestamp(success),
            latency_ms=latest["latency_ms"] if latest else None,
            error_code=latest["error_code"] if latest else None,
            sample_count=count,
        )
