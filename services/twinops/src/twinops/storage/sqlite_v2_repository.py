"""SQLite reference implementation of the TwinOps telemetry v2 boundary."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from twinops.contracts.v2_models import CanonicalSensorReadingV2
from twinops.storage.v2_repository import (
    CollectionAttemptV2,
    HistoryQueryV2,
    InsertResult,
    RawReadingV2,
    RefreshCycleClaimV2,
    RefreshCycleV2,
    RepositorySensorHealthV2,
    RepositorySnapshotReadV2,
    SensorRefreshOutcomeV2,
    SensorRefreshWriteV2,
)


_MIGRATION_PATH = Path(__file__).parents[3] / "migrations" / "002_real_twin_v2.sql"
_OUTCOMES = {"stored", "unchanged", "failed"}


def _timestamp(value: datetime | str) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
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


def _canonical_json(sample: CanonicalSensorReadingV2) -> str:
    return json.dumps(
        sample.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_json(reading: RawReadingV2) -> str:
    return json.dumps(
        reading.payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _outcomes_json(outcomes: dict[str, SensorRefreshOutcomeV2]) -> str:
    if set(outcomes) != {"s1", "s2"} or any(
        value not in _OUTCOMES for value in outcomes.values()
    ):
        raise ValueError("cycle outcomes must contain valid s1 and s2 results")
    return json.dumps(outcomes, sort_keys=True, separators=(",", ":"))


def _parse_outcomes(value: str | None) -> dict[str, SensorRefreshOutcomeV2] | None:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict) or set(parsed) != {"s1", "s2"} or any(
        outcome not in _OUTCOMES for outcome in parsed.values()
    ):
        raise ValueError("stored refresh cycle has invalid outcomes")
    return {sensor_id: outcome for sensor_id, outcome in parsed.items()}


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

    def _insert_distinct_sample(
        self,
        connection: sqlite3.Connection,
        sample: CanonicalSensorReadingV2,
    ) -> InsertResult:
        canonical_json = _canonical_json(sample)
        latest_distinct = connection.execute(
            "SELECT reading_id, payload_hash FROM telemetry_samples_v2 "
            "WHERE asset_id=? AND sensor_id=? "
            "ORDER BY observed_at DESC, received_at DESC, reading_id DESC LIMIT 1",
            (sample.asset_id, sample.sensor_id),
        ).fetchone()
        if (
            latest_distinct is not None
            and latest_distinct["payload_hash"] == sample.payload_hash
        ):
            result = InsertResult(
                stored=False,
                duplicate_of=latest_distinct["reading_id"],
            )
        else:
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
            result = InsertResult(stored=True, duplicate_of=None)

        connection.execute(
            "INSERT INTO latest_readings_v2 "
            "(asset_id,sensor_id,reading_id,received_at,canonical_json) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(asset_id,sensor_id) DO UPDATE SET "
            "reading_id=excluded.reading_id, "
            "received_at=excluded.received_at, "
            "canonical_json=excluded.canonical_json "
            "WHERE excluded.received_at >= latest_readings_v2.received_at",
            (
                sample.asset_id,
                sample.sensor_id,
                sample.reading_id,
                _timestamp(sample.received_at),
                canonical_json,
            ),
        )
        return result

    @staticmethod
    def _append_raw(
        connection: sqlite3.Connection, reading: RawReadingV2
    ) -> None:
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
                _payload_json(reading),
            ),
        )

    @staticmethod
    def _record_attempt(
        connection: sqlite3.Connection, attempt: CollectionAttemptV2
    ) -> None:
        connection.execute(
            "INSERT INTO collection_attempts_v2 "
            "(attempt_id,sensor_id,scheduled_at,attempted_at,succeeded,"
            "latency_ms,error_code) VALUES (?,?,?,?,?,?,?)",
            (
                attempt.attempt_id,
                attempt.sensor_id,
                _timestamp(attempt.scheduled_at),
                _timestamp(attempt.attempted_at),
                attempt.succeeded,
                attempt.latency_ms,
                attempt.error_code,
            ),
        )

    def insert_distinct_sample(
        self, sample: CanonicalSensorReadingV2
    ) -> InsertResult:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._insert_distinct_sample(connection, sample)

    def append_raw(self, reading: RawReadingV2) -> None:
        with self._connection() as connection:
            self._append_raw(connection, reading)

    def record_attempt(self, attempt: CollectionAttemptV2) -> None:
        with self._connection() as connection:
            self._record_attempt(connection, attempt)

    def persist_sensor_result(
        self, write: SensorRefreshWriteV2
    ) -> InsertResult | None:
        self._validate_sensor_write(write)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if write.raw is not None:
                self._append_raw(connection, write.raw)
            inserted = (
                self._insert_distinct_sample(connection, write.sample)
                if write.sample is not None
                else None
            )
            self._record_attempt(connection, write.attempt)
            return inserted

    @staticmethod
    def _validate_sensor_write(write: SensorRefreshWriteV2) -> None:
        sensor_id = write.attempt.sensor_id
        if write.raw is not None and write.raw.sensor_id != sensor_id:
            raise ValueError("raw and attempt sensor ids must match")
        if write.sample is not None and write.sample.sensor_id != sensor_id:
            raise ValueError("sample and attempt sensor ids must match")

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

    def latest(self, asset_id: str) -> list[CanonicalSensorReadingV2]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT canonical_json FROM latest_readings_v2 "
                "WHERE asset_id=? ORDER BY sensor_id",
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

    def snapshot_read(
        self,
        asset_id: str,
        *,
        sensor_ids: tuple[str, ...],
        history_limit_per_sensor: int,
    ) -> RepositorySnapshotReadV2:
        if (
            not sensor_ids
            or len(set(sensor_ids)) != len(sensor_ids)
            or any(not sensor_id for sensor_id in sensor_ids)
            or not 1 <= history_limit_per_sensor <= 1000
        ):
            raise ValueError("snapshot read parameters are invalid")
        placeholders = ",".join("?" for _ in sensor_ids)
        with self._connection() as connection:
            latest_rows = connection.execute(
                "SELECT canonical_json FROM latest_readings_v2 "
                f"WHERE asset_id=? AND sensor_id IN ({placeholders}) "
                "ORDER BY sensor_id",
                (asset_id, *sensor_ids),
            ).fetchall()
            history_rows = connection.execute(
                "SELECT canonical_json FROM ("
                "SELECT canonical_json, sensor_id, "
                "ROW_NUMBER() OVER (PARTITION BY sensor_id "
                "ORDER BY observed_at DESC, received_at DESC, reading_id DESC) "
                "AS sensor_rank FROM telemetry_samples_v2 "
                f"WHERE asset_id=? AND sensor_id IN ({placeholders})"
                ") AS ranked WHERE sensor_rank <= ? "
                "ORDER BY sensor_id, sensor_rank",
                (asset_id, *sensor_ids, history_limit_per_sensor),
            ).fetchall()
            health_items = []
            for sensor_id in sensor_ids:
                latest_attempt = connection.execute(
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
                if latest_attempt is not None or sample_count > 0:
                    health_items.append(
                        RepositorySensorHealthV2(
                            sensor_id=sensor_id,
                            last_attempt_at=(
                                _parse_timestamp(latest_attempt["attempted_at"])
                                if latest_attempt
                                else None
                            ),
                            last_success_at=_parse_timestamp(last_success),
                            latency_ms=(
                                latest_attempt["latency_ms"]
                                if latest_attempt
                                else None
                            ),
                            error_code=(
                                latest_attempt["error_code"]
                                if latest_attempt
                                else None
                            ),
                            sample_count=sample_count,
                        )
                    )
        return RepositorySnapshotReadV2(
            latest=tuple(
                CanonicalSensorReadingV2.model_validate(
                    json.loads(row["canonical_json"])
                )
                for row in latest_rows
            ),
            history=tuple(
                CanonicalSensorReadingV2.model_validate(
                    json.loads(row["canonical_json"])
                )
                for row in history_rows
            ),
            health=tuple(health_items),
        )

    def claim_refresh_cycle(
        self,
        *,
        asset_id: str,
        scheduled_at: datetime,
        owner_token: str,
        claimed_at: datetime,
        stale_before: datetime,
    ) -> RefreshCycleClaimV2:
        scheduled = _timestamp(scheduled_at)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM refresh_cycles_v2 "
                "WHERE asset_id=? AND scheduled_at=?",
                (asset_id, scheduled),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO refresh_cycles_v2 "
                    "(asset_id,scheduled_at,owner_token,claimed_at,status) "
                    "VALUES (?,?,?,?, 'in_progress')",
                    (asset_id, scheduled, owner_token, _timestamp(claimed_at)),
                )
                cycle = RefreshCycleV2(
                    asset_id=asset_id,
                    scheduled_at=scheduled_at.astimezone(timezone.utc),
                    owner_token=owner_token,
                    claimed_at=claimed_at.astimezone(timezone.utc),
                    completed_at=None,
                    outcomes=None,
                )
                return RefreshCycleClaimV2(owned=True, cycle=cycle)

            cycle = self._cycle_from_row(row)
            if cycle.completed_at is not None:
                return RefreshCycleClaimV2(owned=False, cycle=cycle)
            if cycle.claimed_at <= stale_before:
                connection.execute(
                    "UPDATE refresh_cycles_v2 SET owner_token=?, claimed_at=?, "
                    "completed_at=NULL, outcomes_json=NULL, status='in_progress' "
                    "WHERE asset_id=? AND scheduled_at=?",
                    (
                        owner_token,
                        _timestamp(claimed_at),
                        asset_id,
                        scheduled,
                    ),
                )
                return RefreshCycleClaimV2(
                    owned=True,
                    cycle=RefreshCycleV2(
                        asset_id=asset_id,
                        scheduled_at=cycle.scheduled_at,
                        owner_token=owner_token,
                        claimed_at=claimed_at.astimezone(timezone.utc),
                        completed_at=None,
                        outcomes=None,
                    ),
                )
            return RefreshCycleClaimV2(owned=False, cycle=cycle)

    def get_refresh_cycle(
        self, asset_id: str, scheduled_at: datetime
    ) -> RefreshCycleV2 | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM refresh_cycles_v2 "
                "WHERE asset_id=? AND scheduled_at=?",
                (asset_id, _timestamp(scheduled_at)),
            ).fetchone()
        return None if row is None else self._cycle_from_row(row)

    def complete_refresh_cycle(
        self,
        *,
        asset_id: str,
        scheduled_at: datetime,
        owner_token: str,
        completed_at: datetime,
        outcomes: dict[str, SensorRefreshOutcomeV2],
    ) -> RefreshCycleV2:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE refresh_cycles_v2 SET completed_at=?, outcomes_json=?, "
                "status='completed' WHERE asset_id=? AND scheduled_at=? "
                "AND owner_token=? AND status='in_progress'",
                (
                    _timestamp(completed_at),
                    _outcomes_json(outcomes),
                    asset_id,
                    _timestamp(scheduled_at),
                    owner_token,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("refresh cycle is not owned by caller")
            row = connection.execute(
                "SELECT * FROM refresh_cycles_v2 "
                "WHERE asset_id=? AND scheduled_at=?",
                (asset_id, _timestamp(scheduled_at)),
            ).fetchone()
            assert row is not None
            return self._cycle_from_row(row)

    @staticmethod
    def _cycle_from_row(row: sqlite3.Row) -> RefreshCycleV2:
        scheduled_at = _parse_timestamp(row["scheduled_at"])
        claimed_at = _parse_timestamp(row["claimed_at"])
        assert scheduled_at is not None and claimed_at is not None
        return RefreshCycleV2(
            asset_id=row["asset_id"],
            scheduled_at=scheduled_at,
            owner_token=row["owner_token"],
            claimed_at=claimed_at,
            completed_at=_parse_timestamp(row["completed_at"]),
            outcomes=_parse_outcomes(row["outcomes_json"]),
        )
