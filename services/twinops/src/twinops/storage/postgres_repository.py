"""PostgreSQL implementation of the TwinOps telemetry v2 boundary."""

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from twinops.contracts.v2_models import CanonicalSensorReadingV2
from twinops.storage.v2_repository import (
    CollectionAttemptV2,
    HistoryQueryV2,
    InsertResult,
    RawReadingV2,
    RefreshCycleClaimV2,
    RefreshCycleV2,
    RepositorySensorHealthV2,
    SensorRefreshOutcomeV2,
    SensorRefreshWriteV2,
)


_MIGRATION_PATH = Path(__file__).parents[3] / "migrations" / "002_real_twin_v2.sql"
_OUTCOMES = {"stored", "unchanged", "failed"}
POSTGRES_V2_REQUIRED_TABLES = frozenset(
    {
        "collection_attempts_v2",
        "latest_readings_v2",
        "raw_readings_v2",
        "refresh_cycles_v2",
        "telemetry_samples_v2",
    }
)
POSTGRES_V2_REQUIRED_INDEXES = frozenset(
    {
        "ix_raw_readings_v2_slot",
        "ix_telemetry_samples_v2_history",
    }
)
POSTGRES_SCHEMA_MIGRATION_LOCK_KEY = 0x5457494E4F505332
_POSTGRES_SCHEMA_CURRENT_SQL = (
    "SELECT "
    "(SELECT COUNT(*) FROM pg_catalog.pg_tables "
    "WHERE schemaname='public' AND tablename = ANY(%s)) = %s "
    "AS tables_current, "
    "(SELECT COUNT(*) FROM pg_catalog.pg_indexes "
    "WHERE schemaname='public' AND indexname = ANY(%s)) = %s "
    "AS indexes_current"
)
_POSTGRES_SCHEMA_MIGRATION_LOCK_SQL = "SELECT pg_advisory_xact_lock(%s)"


def postgres_schema_is_current(connection) -> bool:
    """Check the v2 schema using only the PostgreSQL catalogs."""

    row = connection.execute(
        _POSTGRES_SCHEMA_CURRENT_SQL,
        (
            sorted(POSTGRES_V2_REQUIRED_TABLES),
            len(POSTGRES_V2_REQUIRED_TABLES),
            sorted(POSTGRES_V2_REQUIRED_INDEXES),
            len(POSTGRES_V2_REQUIRED_INDEXES),
        ),
    ).fetchone()
    if row is None:
        return False
    if isinstance(row, Mapping):
        return bool(row["tables_current"] and row["indexes_current"])
    return bool(row[0] and row[1])


def ensure_postgres_schema(
    connection,
    migration_loader: Callable[[], str],
) -> bool:
    """Apply migration 002 once while the caller owns a DB transaction."""

    if postgres_schema_is_current(connection):
        return False
    connection.execute(
        _POSTGRES_SCHEMA_MIGRATION_LOCK_SQL,
        (POSTGRES_SCHEMA_MIGRATION_LOCK_KEY,),
    )
    if postgres_schema_is_current(connection):
        return False
    connection.execute(migration_loader(), prepare=False)
    return True


def _timestamp(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    return _timestamp(value)


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


class PostgresTelemetryRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    @contextmanager
    def _connection(self):
        with psycopg.connect(
            self.database_url,
            row_factory=dict_row,
        ) as connection:
            yield connection

    def initialize(self) -> None:
        with self._connection() as connection:
            ensure_postgres_schema(
                connection,
                lambda: _MIGRATION_PATH.read_text(encoding="utf-8"),
            )

    def _insert_distinct_sample(
        self,
        connection,
        sample: CanonicalSensorReadingV2,
    ) -> InsertResult:
        canonical_json = _canonical_json(sample)
        lock_key = f"{sample.asset_id}\x1f{sample.sensor_id}"
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (lock_key,),
        )
        latest_distinct = connection.execute(
            "SELECT reading_id, payload_hash FROM telemetry_samples_v2 "
            "WHERE asset_id=%s AND sensor_id=%s "
            "ORDER BY observed_at DESC, received_at DESC, reading_id DESC "
            "LIMIT 1 FOR UPDATE",
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
                "payload_hash,canonical_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
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
            "VALUES (%s,%s,%s,%s,%s) "
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
    def _append_raw(connection, reading: RawReadingV2) -> None:
        connection.execute(
            "INSERT INTO raw_readings_v2 "
            "(raw_id,sensor_id,scheduled_at,received_at,payload_hash,payload_json) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
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
    def _record_attempt(connection, attempt: CollectionAttemptV2) -> None:
        connection.execute(
            "INSERT INTO collection_attempts_v2 "
            "(attempt_id,sensor_id,scheduled_at,attempted_at,succeeded,"
            "latency_ms,error_code) VALUES (%s,%s,%s,%s,%s,%s,%s)",
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

    def latest(self, asset_id: str) -> list[CanonicalSensorReadingV2]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT canonical_json FROM latest_readings_v2 "
                "WHERE asset_id=%s ORDER BY sensor_id",
                (asset_id,),
            ).fetchall()
        return [
            CanonicalSensorReadingV2.model_validate(json.loads(row["canonical_json"]))
            for row in rows
        ]

    def history(self, query: HistoryQueryV2) -> list[CanonicalSensorReadingV2]:
        if not 1 <= query.limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        where = ["asset_id = %s"]
        parameters: list[object] = [query.asset_id]
        optional = (
            (query.sensor_id, "sensor_id = %s"),
            (
                _timestamp(query.from_at) if query.from_at else None,
                "observed_at >= %s",
            ),
            (
                _timestamp(query.to_at) if query.to_at else None,
                "observed_at <= %s",
            ),
        )
        for value, clause in optional:
            if value is not None:
                where.append(clause)
                parameters.append(value)
        parameters.append(query.limit)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT canonical_json FROM telemetry_samples_v2 WHERE "
                + " AND ".join(where)
                + " ORDER BY observed_at DESC, received_at DESC, reading_id DESC "
                "LIMIT %s",
                parameters,
            ).fetchall()
        return [
            CanonicalSensorReadingV2.model_validate(json.loads(row["canonical_json"]))
            for row in rows
        ]

    def health(self, sensor_id: str) -> RepositorySensorHealthV2 | None:
        with self._connection() as connection:
            latest = connection.execute(
                "SELECT attempted_at, latency_ms, error_code "
                "FROM collection_attempts_v2 WHERE sensor_id=%s "
                "ORDER BY attempted_at DESC, attempt_id DESC LIMIT 1",
                (sensor_id,),
            ).fetchone()
            last_success = connection.execute(
                "SELECT MAX(attempted_at) AS attempted_at "
                "FROM collection_attempts_v2 "
                "WHERE sensor_id=%s AND succeeded=TRUE",
                (sensor_id,),
            ).fetchone()["attempted_at"]
            sample_count = connection.execute(
                "SELECT COUNT(*) AS sample_count FROM telemetry_samples_v2 "
                "WHERE sensor_id=%s",
                (sensor_id,),
            ).fetchone()["sample_count"]
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
        lock_key = f"{asset_id}\x1f{scheduled.isoformat()}"
        with self._connection() as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (lock_key,),
            )
            row = connection.execute(
                "SELECT * FROM refresh_cycles_v2 "
                "WHERE asset_id=%s AND scheduled_at=%s FOR UPDATE",
                (asset_id, scheduled),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO refresh_cycles_v2 "
                    "(asset_id,scheduled_at,owner_token,claimed_at,status) "
                    "VALUES (%s,%s,%s,%s,'in_progress')",
                    (asset_id, scheduled, owner_token, _timestamp(claimed_at)),
                )
                cycle = RefreshCycleV2(
                    asset_id=asset_id,
                    scheduled_at=scheduled,
                    owner_token=owner_token,
                    claimed_at=_timestamp(claimed_at),
                    completed_at=None,
                    outcomes=None,
                )
                return RefreshCycleClaimV2(owned=True, cycle=cycle)

            cycle = self._cycle_from_row(row)
            if cycle.completed_at is not None:
                return RefreshCycleClaimV2(owned=False, cycle=cycle)
            if cycle.claimed_at <= stale_before:
                connection.execute(
                    "UPDATE refresh_cycles_v2 SET owner_token=%s, claimed_at=%s, "
                    "completed_at=NULL, outcomes_json=NULL, status='in_progress' "
                    "WHERE asset_id=%s AND scheduled_at=%s",
                    (owner_token, _timestamp(claimed_at), asset_id, scheduled),
                )
                return RefreshCycleClaimV2(
                    owned=True,
                    cycle=RefreshCycleV2(
                        asset_id=asset_id,
                        scheduled_at=scheduled,
                        owner_token=owner_token,
                        claimed_at=_timestamp(claimed_at),
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
                "WHERE asset_id=%s AND scheduled_at=%s",
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
            cursor = connection.execute(
                "UPDATE refresh_cycles_v2 SET completed_at=%s, outcomes_json=%s, "
                "status='completed' WHERE asset_id=%s AND scheduled_at=%s "
                "AND owner_token=%s AND status='in_progress'",
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
                "WHERE asset_id=%s AND scheduled_at=%s",
                (asset_id, _timestamp(scheduled_at)),
            ).fetchone()
            assert row is not None
            return self._cycle_from_row(row)

    @staticmethod
    def _cycle_from_row(row) -> RefreshCycleV2:
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
