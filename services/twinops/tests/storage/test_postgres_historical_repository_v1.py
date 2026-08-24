from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.util import find_spec
import json
import os
from typing import Iterable

import psycopg
from psycopg.rows import dict_row
import pytest

from historical_repository_contract import run_activation_race, synthetic_prepared_batch
from twinops.contracts.timeline_v1_models import CollectionPolicyV1
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

    def test_postgres_activation_race_leaves_exactly_one_active_batch(
        historical_repository, repository_control: PostgresRepositoryControl
    ) -> None:
        candidates = (synthetic_prepared_batch(0), synthetic_prepared_batch(1))
        for candidate in candidates:
            historical_repository.stage_batch(candidate)

        results = run_activation_race(historical_repository, candidates)

        assert sum(result is not None and result.activated for result in results) == 1
        assert repository_control.count_active("forzy-motor-01") == 1
