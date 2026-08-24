from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.util import find_spec
import json
import os
from threading import Barrier, Event, Lock
from time import monotonic
from types import SimpleNamespace
from typing import Iterable

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row, tuple_row
import pytest

from historical_repository_contract import _assessment, synthetic_prepared_batch
from twinops.contracts.timeline_v1_models import CollectionPolicyV1
from twinops.storage.historical_repository_v1 import HistoricalBatchConflict
from twinops.storage.schema_migrations import (
    apply_postgres_migrations,
    registered_migration_specs,
)


pytestmark = pytest.mark.postgres

_POSTGRES_MODULE = "twinops.storage.postgres_historical_repository_v1"
_REPOSITORY_AVAILABLE = find_spec(_POSTGRES_MODULE) is not None
_V3_CLEANUP_TABLES = (
    "refresh_cycle_policies_v1",
    "historical_assessments_v1",
    "historical_samples_v1",
    "historical_raw_rows_v1",
    "historical_import_batches_v1",
    "collection_policies_v1",
    "deployment_identity_v1",
    "schema_migrations_v1",
)
_HISTORICAL_TABLES = _V3_CLEANUP_TABLES[1:5]
_LIVE_TABLES = (
    "telemetry_samples_v2",
    "latest_readings_v2",
    "raw_readings_v2",
    "collection_attempts_v2",
    "refresh_cycles_v2",
)
_POLICY_COLUMNS = (
    "schema_version", "policy_id", "asset_id", "timezone_name",
    "active_weekdays_json", "window_start_local", "window_end_local",
    "poll_interval_seconds", "gap_threshold_seconds", "effective_from",
    "effective_to", "configuration_hash",
)
_RACE_COORDINATION_TIMEOUT_SECONDS = 30
_RACE_BLOCKED_OBSERVATION_SECONDS = 0.5


@dataclass(frozen=True)
class _PostgresTestTarget:
    database_url: str

    def __repr__(self) -> str:
        return "<authorized disposable PostgreSQL test target>"


def _cleanup_v3(connection) -> None:
    for table in _V3_CLEANUP_TABLES:
        connection.execute(f"DELETE FROM {table}")


@pytest.fixture
def postgres_test_target() -> _PostgresTestTarget:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Task A5 requires an authorized disposable TEST_DATABASE_URL; absence is not a skip/pass"
        )
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        apply_postgres_migrations(
            connection,
            registered_migration_specs(),
            initial_policy_effective_from=datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
        )
        _cleanup_v3(connection)
        apply_postgres_migrations(
            connection,
            registered_migration_specs(),
            initial_policy_effective_from=datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
        )
    try:
        yield _PostgresTestTarget(database_url)
    finally:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            _cleanup_v3(connection)


def test_postgres_historical_repository_surface_exists(
    postgres_test_target: _PostgresTestTarget,
) -> None:
    assert postgres_test_target.database_url
    assert _REPOSITORY_AVAILABLE, "RED:A5:postgres-history-repository-missing"


if _REPOSITORY_AVAILABLE:
    from historical_repository_contract import HistoricalRepositoryContract
    from twinops.storage.postgres_historical_repository_v1 import (
        PostgresHistoricalRepositoryV1,
    )

    class PostgresRepositoryControl:
        def __init__(self, database_url: str) -> None:
            self.database_url = database_url

        @contextmanager
        def connection(self):
            with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
                yield connection

        def _counts(self, tables: Iterable[str]) -> dict[str, int]:
            with self.connection() as connection:
                return {
                    table: connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
                    for table in tables
                }

        def historical_counts(self) -> dict[str, int]:
            return self._counts(_HISTORICAL_TABLES)

        def live_counts(self) -> dict[str, int]:
            return self._counts(_LIVE_TABLES)

        def snapshot(self) -> object:
            order_by = {
                "schema_migrations_v1": "migration_version",
                "deployment_identity_v1": "identity_key",
                "historical_import_batches_v1": "batch_id",
                "historical_raw_rows_v1": "batch_id,record_ordinal",
                "historical_samples_v1": "batch_id,record_ordinal,sensor_id,reading_id",
                "historical_assessments_v1": "batch_id,assessment_id",
                "collection_policies_v1": "policy_id",
                "refresh_cycle_policies_v1": "asset_id,scheduled_at",
            }
            with self.connection() as connection:
                return tuple(
                    (table, tuple(tuple(row.values()) for row in connection.execute(
                        f"SELECT * FROM {table} ORDER BY {order_by[table]}"
                    ).fetchall()))
                    for table in _V3_CLEANUP_TABLES
                )

        def statuses(self, asset_id: str) -> dict[str, str]:
            with self.connection() as connection:
                rows = connection.execute(
                    "SELECT batch_id,status FROM historical_import_batches_v1 "
                    "WHERE asset_id=%s ORDER BY batch_id", (asset_id,)
                ).fetchall()
            return {row["batch_id"]: row["status"] for row in rows}

        def count_active(self, asset_id: str) -> int:
            with self.connection() as connection:
                return connection.execute(
                    "SELECT COUNT(*) AS count FROM historical_import_batches_v1 "
                    "WHERE asset_id=%s AND status='active'", (asset_id,)
                ).fetchone()["count"]

        def tamper_batch_manifest(self, batch_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE historical_import_batches_v1 SET manifest_json=manifest_json || ' ' "
                    "WHERE batch_id=%s", (batch_id,)
                )

        def tamper_batch_count(self, batch_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE historical_import_batches_v1 SET raw_row_count=raw_row_count + 1 "
                    "WHERE batch_id=%s", (batch_id,)
                )

        def tamper_raw_hash(self, batch_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE historical_raw_rows_v1 SET row_sha256=%s "
                    "WHERE batch_id=%s AND record_ordinal=1", ("sha256:" + "0" * 64, batch_id)
                )

        def tamper_raw_offset(self, batch_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE historical_raw_rows_v1 SET byte_start=byte_start + 1 "
                    "WHERE batch_id=%s AND record_ordinal=1", (batch_id,)
                )

        def tamper_sample_payload(self, batch_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE historical_samples_v1 SET canonical_json=canonical_json || ' ' "
                    "WHERE reading_id=(SELECT reading_id FROM historical_samples_v1 "
                    "WHERE batch_id=%s ORDER BY reading_id LIMIT 1)", (batch_id,)
                )

        def delete_policy(self, policy_id: str) -> None:
            with self.connection() as connection:
                connection.execute("DELETE FROM collection_policies_v1 WHERE policy_id=%s", (policy_id,))

        def insert_policy(self, policy: CollectionPolicyV1) -> None:
            body = policy.model_dump_public()
            with self.connection() as connection:
                connection.execute(
                    "INSERT INTO collection_policies_v1 (" + ",".join(_POLICY_COLUMNS)
                    + ") VALUES (" + ",".join(["%s"] * len(_POLICY_COLUMNS)) + ")",
                    (
                        body["schemaVersion"], body["collectionPolicyId"], body["assetId"], body["timezone"],
                        json.dumps(body["activeWeekdays"], separators=(",", ":")),
                        body["windowStartLocal"], body["windowEndLocal"], body["pollIntervalSeconds"],
                        body["gapThresholdSeconds"], body["effectiveFrom"], body["effectiveTo"],
                        body["configurationHash"],
                    ),
                )

        def tamper_policy_hash(self, policy_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE collection_policies_v1 SET configuration_hash=%s WHERE policy_id=%s",
                    ("sha256:" + "0" * 64, policy_id),
                )

        def tamper_policy_field(self, policy_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE collection_policies_v1 SET poll_interval_seconds=6 WHERE policy_id=%s",
                    (policy_id,),
                )

        def interrupting_repository(self, operation: str, exception_type: type[BaseException]):
            trigger = {
                "stage": "INSERT INTO historical_samples_v1",
                "assessment": "INSERT INTO historical_assessments_v1",
                "activation": "UPDATE historical_import_batches_v1 SET status='superseded'",
            }[operation]

            class InterruptingConnection:
                fired = False

                def __init__(self, connection) -> None:
                    self.connection = connection

                def __getattr__(self, name):
                    return getattr(self.connection, name)

                def execute(self, query, params=None, **kwargs):
                    cursor = self.connection.execute(query, params, **kwargs)
                    if not self.fired and " ".join(query.split()).startswith(trigger):
                        self.fired = True
                        raise exception_type(f"injected {operation} interruption")
                    return cursor

            def factory(database_url: str):
                return InterruptingConnection(psycopg.connect(database_url, row_factory=dict_row))

            return PostgresHistoricalRepositoryV1(self.database_url, connection_factory=factory)

    @pytest.fixture
    def historical_repository(postgres_test_target: _PostgresTestTarget):
        return PostgresHistoricalRepositoryV1(postgres_test_target.database_url)

    @pytest.fixture
    def prepared_batch_factory():
        return synthetic_prepared_batch

    @pytest.fixture
    def repository_control(postgres_test_target: _PostgresTestTarget):
        return PostgresRepositoryControl(postgres_test_target.database_url)

    class TestPostgresHistoricalRepositoryContract(HistoricalRepositoryContract):
        pass


    @pytest.mark.parametrize(
        ("initially_closed", "transaction_status", "row_factory", "error"),
        [
            pytest.param(
                True,
                TransactionStatus.IDLE,
                dict_row,
                "open connection",
                id="closed",
            ),
            pytest.param(
                False,
                TransactionStatus.INTRANS,
                dict_row,
                "idle connection",
                id="non-idle",
            ),
            pytest.param(
                False,
                TransactionStatus.IDLE,
                tuple_row,
                "dict_row",
                id="wrong-row-factory",
            ),
        ],
    )
    def test_connection_factory_guard_rejects_before_sql_and_closes(
        initially_closed: bool,
        transaction_status: TransactionStatus,
        row_factory,
        error: str,
    ) -> None:
        class GuardConnection:
            def __init__(self) -> None:
                self.closed = initially_closed
                self.autocommit = False
                self.info = SimpleNamespace(transaction_status=transaction_status)
                self.row_factory = row_factory
                self.statements: list[str] = []
                self.close_calls = 0

            def execute(self, query, params=None, **kwargs):
                self.statements.append(" ".join(query.split()))
                raise AssertionError("repository SQL executed on a rejected connection")

            def close(self) -> None:
                self.close_calls += 1
                self.closed = True

        connection = GuardConnection()
        repository = PostgresHistoricalRepositoryV1(
            "unused-local-test-target",
            connection_factory=lambda database_url: connection,
        )

        with pytest.raises(RuntimeError, match=error):
            repository.stage_batch(synthetic_prepared_batch(0))

        assert connection.statements == []
        assert connection.close_calls == 1
        assert connection.closed is True


    def test_postgres_normalizes_timestamptz_rows_from_non_utc_session(
        historical_repository,
        postgres_test_target: _PostgresTestTarget,
    ) -> None:
        batch = synthetic_prepared_batch(0)
        first = historical_repository.stage_batch(batch)

        def non_utc_factory(database_url: str):
            return psycopg.connect(
                database_url,
                row_factory=dict_row,
                options="-c timezone=America/Sao_Paulo",
            )

        non_utc_repository = PostgresHistoricalRepositoryV1(
            postgres_test_target.database_url,
            connection_factory=non_utc_factory,
        )

        replay = non_utc_repository.stage_batch(batch)

        assert replay.inserted is False
        assert replay.writes_performed == 0
        assert replay.batch == first.batch


    @pytest.mark.parametrize("operation", ["stage", "store", "activate"])
    def test_autocommit_connection_factory_is_rejected_before_dml(
        operation: str,
        historical_repository,
        repository_control: PostgresRepositoryControl,
        postgres_test_target: _PostgresTestTarget,
    ) -> None:
        batch = synthetic_prepared_batch(0)
        assessment = _assessment(batch)
        if operation != "stage":
            historical_repository.stage_batch(batch)
        before = repository_control.snapshot()
        statements: list[str] = []

        class RecordingAutocommitConnection:
            def __init__(self, connection) -> None:
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, query, params=None, **kwargs):
                statements.append(" ".join(query.split()))
                return self.connection.execute(query, params, **kwargs)

        rejected_connections: list[RecordingAutocommitConnection] = []

        def autocommit_factory(database_url: str):
            connection = RecordingAutocommitConnection(
                psycopg.connect(
                    database_url,
                    autocommit=True,
                    row_factory=dict_row,
                )
            )
            rejected_connections.append(connection)
            return connection

        repository = PostgresHistoricalRepositoryV1(
            postgres_test_target.database_url,
            connection_factory=autocommit_factory,
        )
        actions = {
            "stage": lambda: repository.stage_batch(batch),
            "store": lambda: repository.store_assessments(
                batch.batch_id,
                [assessment],
            ),
            "activate": lambda: repository.activate_batch(
                asset_id=batch.asset_id,
                batch_id=batch.batch_id,
                expected_active_batch_id=None,
            ),
        }

        with pytest.raises(RuntimeError, match="autocommit"):
            actions[operation]()

        assert statements == []
        assert len(rejected_connections) == 1
        assert rejected_connections[0].closed is True
        assert repository_control.snapshot() == before


    def test_postgres_activation_race_leaves_exactly_one_active_batch(
        historical_repository,
        repository_control: PostgresRepositoryControl,
        postgres_test_target: _PostgresTestTarget,
    ) -> None:
        candidates = (synthetic_prepared_batch(0), synthetic_prepared_batch(1))
        for candidate in candidates:
            historical_repository.stage_batch(candidate)

        ready_to_lock = Barrier(2)
        holder_has_lock = Event()
        contender_attempting_lock = Event()
        contender_returned_from_lock = Event()
        release_holder = Event()
        factory_lock = Lock()
        controlled_connections = []
        next_connection_index = 0

        class LockControlledConnection:
            def __init__(self, connection, index: int) -> None:
                self.connection = connection
                self.index = index

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, query, params=None, **kwargs):
                normalized = " ".join(query.split())
                is_asset_lock = (
                    "pg_advisory_xact_lock" in normalized
                    and params == ("forzy-motor-01",)
                )
                if not is_asset_lock:
                    return self.connection.execute(query, params, **kwargs)

                self.connection.execute("SET LOCAL lock_timeout = '20s'")
                ready_to_lock.wait(timeout=_RACE_COORDINATION_TIMEOUT_SECONDS)
                if self.index == 0:
                    cursor = self.connection.execute(query, params, **kwargs)
                    holder_has_lock.set()
                    if not contender_attempting_lock.wait(
                        timeout=_RACE_COORDINATION_TIMEOUT_SECONDS
                    ):
                        raise TimeoutError("contender did not attempt the asset lock")
                    if not release_holder.wait(
                        timeout=_RACE_COORDINATION_TIMEOUT_SECONDS
                    ):
                        raise TimeoutError("controller did not release the asset-lock holder")
                    return cursor

                if not holder_has_lock.wait(
                    timeout=_RACE_COORDINATION_TIMEOUT_SECONDS
                ):
                    raise TimeoutError("holder did not acquire the asset lock")
                contender_attempting_lock.set()
                cursor = self.connection.execute(query, params, **kwargs)
                contender_returned_from_lock.set()
                return cursor

        def lock_controlled_factory(database_url: str):
            nonlocal next_connection_index
            with factory_lock:
                index = next_connection_index
                next_connection_index += 1
            assert index < 2, "race must open exactly two instrumented connections"
            connection = psycopg.connect(
                database_url,
                row_factory=dict_row,
                connect_timeout=30,
            )
            with factory_lock:
                controlled_connections.append(connection)
            return LockControlledConnection(connection, index)

        racing_repository = PostgresHistoricalRepositoryV1(
            postgres_test_target.database_url,
            connection_factory=lock_controlled_factory,
        )

        def activate(candidate):
            try:
                return racing_repository.activate_batch(
                    asset_id=candidate.asset_id,
                    batch_id=candidate.batch_id,
                    expected_active_batch_id=None,
                )
            except HistoricalBatchConflict as exc:
                assert str(exc) == "expected active historical batch mismatch"
                return None

        def wait_for_event_or_worker_failure(
            event: Event,
            futures,
            label: str,
        ) -> None:
            deadline = monotonic() + _RACE_COORDINATION_TIMEOUT_SECONDS
            while True:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    pytest.fail(f"timed out waiting for {label}")
                if event.wait(timeout=min(0.1, remaining)):
                    return
                for future in futures:
                    if not future.done():
                        continue
                    exception = future.exception()
                    if exception is not None:
                        raise AssertionError(
                            f"race worker failed before {label}"
                        ) from exception
                    raise AssertionError(f"race worker completed before {label}")

        def abort_race(futures) -> None:
            release_holder.set()
            with suppress(Exception):
                ready_to_lock.abort()
            with factory_lock:
                connections = tuple(controlled_connections)
            for connection in connections:
                with suppress(Exception):
                    connection.cancel_safe(timeout=5.0)
                with suppress(Exception):
                    connection.close()
            for future in futures:
                future.cancel()

        pool = ThreadPoolExecutor(max_workers=2)
        futures = []
        try:
            futures = [pool.submit(activate, candidate) for candidate in candidates]
            wait_for_event_or_worker_failure(
                holder_has_lock,
                futures,
                "holder asset-lock acquisition",
            )
            wait_for_event_or_worker_failure(
                contender_attempting_lock,
                futures,
                "contender asset-lock attempt",
            )
            assert (
                contender_returned_from_lock.wait(
                    timeout=_RACE_BLOCKED_OBSERVATION_SECONDS
                )
                is False
            )
            with factory_lock:
                assert len(controlled_connections) == 2
            release_holder.set()
            results = [
                future.result(timeout=_RACE_COORDINATION_TIMEOUT_SECONDS)
                for future in futures
            ]
        except BaseException:
            abort_race(futures)
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            pool.shutdown(wait=True)

        assert sum(result is not None and result.activated for result in results) == 1
        assert sum(result is None for result in results) == 1
        assert contender_returned_from_lock.is_set()
        active = historical_repository.active_batch("forzy-motor-01")
        assert active is not None
        assert active.batch_id == next(
            result.batch_id for result in results if result is not None
        )
        assert repository_control.count_active("forzy-motor-01") == 1
