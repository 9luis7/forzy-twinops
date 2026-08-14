"""SQLite reference implementation of the TwinOps telemetry v2 boundary."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from twinops.contracts.v2_models import CanonicalSensorReadingV2
from twinops.storage.v2_repository import (
    CollectionAttemptV2,
    HistoryQueryV2,
    InsertResult,
    RawReadingV2,
    RepositorySensorHealthV2,
)


_MIGRATION_PATH = Path(__file__).parents[3] / "migrations" / "002_real_twin_v2.sql"


def _timestamp(value: datetime | str) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SQLiteTelemetryRepositoryV2:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        migration = _MIGRATION_PATH.read_text(encoding="utf-8")
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(migration)

    def insert_distinct_sample(
        self, sample: CanonicalSensorReadingV2
    ) -> InsertResult:
        body = sample.model_dump(mode="json", by_alias=True)
        canonical_json = json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                "SELECT reading_id, payload_hash FROM telemetry_samples_v2 "
                "WHERE asset_id=? AND sensor_id=? "
                "ORDER BY observed_at DESC, received_at DESC, reading_id DESC LIMIT 1",
                (sample.asset_id, sample.sensor_id),
            ).fetchone()
            if latest is not None and latest["payload_hash"] == sample.payload_hash:
                return InsertResult(stored=False, duplicate_of=latest["reading_id"])
            connection.execute(
                "INSERT INTO telemetry_samples_v2 "
                "(reading_id,asset_id,sensor_id,observed_at,received_at,"
                "payload_hash,canonical_json) VALUES (?,?,?,?,?,?,?)",
                (
                    sample.reading_id,
                    sample.asset_id,
                    sample.sensor_id,
                    _timestamp(sample.observed_at),
                    _timestamp(sample.received_at),
                    sample.payload_hash,
                    canonical_json,
                ),
            )
            return InsertResult(stored=True, duplicate_of=None)

    def history(self, query: HistoryQueryV2) -> list[CanonicalSensorReadingV2]:
        if not 1 <= query.limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        where = ["asset_id = ?"]
        parameters: list[object] = [query.asset_id]
        optional = (
            (query.sensor_id, "sensor_id = ?"),
            (
                _timestamp(query.from_at) if query.from_at else None,
                "observed_at >= ?",
            ),
            (
                _timestamp(query.to_at) if query.to_at else None,
                "observed_at <= ?",
            ),
        )
        for value, clause in optional:
            if value is not None:
                where.append(clause)
                parameters.append(value)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT canonical_json FROM telemetry_samples_v2 WHERE "
                + " AND ".join(where)
                + " ORDER BY observed_at DESC, received_at DESC, reading_id DESC "
                "LIMIT ?",
                (*parameters, query.limit),
            ).fetchall()
        return [
            CanonicalSensorReadingV2.model_validate(json.loads(row[0]))
            for row in rows
        ]

    def append_raw(self, reading: RawReadingV2) -> None:
        payload_json = json.dumps(
            reading.payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO raw_readings_v2 "
                "(raw_id,sensor_id,scheduled_at,received_at,payload_hash,payload_json) "
                "VALUES (?,?,?,?,?,?)",
                (
                    reading.raw_id,
                    reading.sensor_id,
                    _timestamp(reading.scheduled_at),
                    _timestamp(reading.received_at),
                    reading.payload_hash,
                    payload_json,
                ),
            )

    def record_attempt(self, attempt: CollectionAttemptV2) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO collection_attempts_v2 "
                "(attempt_id,sensor_id,scheduled_at,attempted_at,succeeded,"
                "latency_ms,error_code) VALUES (?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    attempt.sensor_id,
                    _timestamp(attempt.scheduled_at),
                    _timestamp(attempt.attempted_at),
                    attempt.succeeded,
                    attempt.latency_ms,
                    attempt.error_code,
                ),
            )

    def latest(self, asset_id: str) -> list[CanonicalSensorReadingV2]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT canonical_json FROM ("
                "SELECT canonical_json, sensor_id, ROW_NUMBER() OVER ("
                "PARTITION BY sensor_id ORDER BY observed_at DESC, "
                "received_at DESC, reading_id DESC) AS position "
                "FROM telemetry_samples_v2 WHERE asset_id=?"
                ") WHERE position=1 ORDER BY sensor_id",
                (asset_id,),
            ).fetchall()
        return [
            CanonicalSensorReadingV2.model_validate(json.loads(row[0]))
            for row in rows
        ]

    def health(self, sensor_id: str) -> RepositorySensorHealthV2 | None:
        with self._connection() as connection:
            latest = connection.execute(
                "SELECT attempted_at, latency_ms, error_code "
                "FROM collection_attempts_v2 WHERE sensor_id=? "
                "ORDER BY attempted_at DESC, attempt_id DESC LIMIT 1",
                (sensor_id,),
            ).fetchone()
            last_success = connection.execute(
                "SELECT MAX(attempted_at) FROM collection_attempts_v2 "
                "WHERE sensor_id=? AND succeeded=1",
                (sensor_id,),
            ).fetchone()[0]
            sample_count = connection.execute(
                "SELECT COUNT(*) FROM telemetry_samples_v2 WHERE sensor_id=?",
                (sensor_id,),
            ).fetchone()[0]
        if latest is None and sample_count == 0:
            return None
        return RepositorySensorHealthV2(
            sensor_id=sensor_id,
            last_attempt_at=_parse_timestamp(latest["attempted_at"])
            if latest
            else None,
            last_success_at=_parse_timestamp(last_success),
            latency_ms=latest["latency_ms"] if latest else None,
            error_code=latest["error_code"] if latest else None,
            sample_count=sample_count,
        )
