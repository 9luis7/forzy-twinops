from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.util import find_spec
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterable

import pytest


_PROTOCOL_MODULE = "twinops.storage.historical_repository_v1"
_SQLITE_MODULE = "twinops.storage.sqlite_historical_repository_v1"
_REPOSITORY_AVAILABLE = (
    find_spec(_PROTOCOL_MODULE) is not None and find_spec(_SQLITE_MODULE) is not None
)


def test_sqlite_historical_repository_surface_exists() -> None:
    assert _REPOSITORY_AVAILABLE, "RED:A4:sqlite-history-repository-missing"


if _REPOSITORY_AVAILABLE:
    from historical_repository_contract import (
        HistoricalRepositoryContract,
        _assessment,
        synthetic_prepared_batch,
    )
    from twinops.contracts.timeline_v1_models import CollectionPolicyV1
    from twinops.storage.schema_migrations import (
        apply_sqlite_migrations,
        registered_migration_specs,
    )
    from twinops.storage.sqlite_historical_repository_v1 import (
        SQLiteHistoricalRepositoryV1,
    )

    _HISTORICAL_TABLES = (
        "historical_import_batches_v1",
        "historical_raw_rows_v1",
        "historical_samples_v1",
        "historical_assessments_v1",
    )
    _LIVE_TABLES = (
        "telemetry_samples_v2",
        "latest_readings_v2",
        "raw_readings_v2",
        "collection_attempts_v2",
        "refresh_cycles_v2",
    )
    _POLICY_COLUMNS = (
        "schema_version",
        "policy_id",
        "asset_id",
        "timezone_name",
        "active_weekdays_json",
        "window_start_local",
        "window_end_local",
        "poll_interval_seconds",
        "gap_threshold_seconds",
        "effective_from",
        "effective_to",
        "configuration_hash",
    )


    def _connect(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


    def _normalized(sql: str) -> str:
        return " ".join(sql.split())


    class SQLiteRepositoryControl:
        def __init__(self, path: Path):
            self.path = path

        @contextmanager
        def connection(self):
            connection = _connect(self.path)
            try:
                with connection:
                    yield connection
            finally:
                connection.close()

        def _counts(self, tables: Iterable[str]) -> dict[str, int]:
            with self.connection() as connection:
                return {
                    table: connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in tables
                }

        def historical_counts(self) -> dict[str, int]:
            return self._counts(_HISTORICAL_TABLES)

        def live_counts(self) -> dict[str, int]:
            return self._counts(_LIVE_TABLES)

        def snapshot(self) -> object:
            with self.connection() as connection:
                tables = [
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                        "ORDER BY name"
                    ).fetchall()
                ]
                return tuple(
                    (
                        table,
                        tuple(
                            tuple(row)
                            for row in connection.execute(
                                f"SELECT * FROM {table} ORDER BY rowid"
                            ).fetchall()
                        ),
                    )
                    for table in tables
                )

        def statuses(self, asset_id: str) -> dict[str, str]:
            with self.connection() as connection:
                rows = connection.execute(
                    "SELECT batch_id,status FROM historical_import_batches_v1 "
                    "WHERE asset_id=? ORDER BY batch_id",
                    (asset_id,),
                ).fetchall()
            return {row["batch_id"]: row["status"] for row in rows}

        def tamper_batch_manifest(self, batch_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE historical_import_batches_v1 "
                    "SET manifest_json=manifest_json || ' ' WHERE batch_id=?",
                    (batch_id,),
                )

        def tamper_batch_count(self, batch_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE historical_import_batches_v1 "
                    "SET raw_row_count=raw_row_count + 1 WHERE batch_id=?",
                    (batch_id,),
                )

        def tamper_raw_hash(self, batch_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE historical_raw_rows_v1 SET row_sha256=? "
                    "WHERE batch_id=? AND record_ordinal=1",
                    ("sha256:" + "0" * 64, batch_id),
                )

        def tamper_raw_offset(self, batch_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE historical_raw_rows_v1 SET byte_start=byte_start + 1 "
                    "WHERE batch_id=? AND record_ordinal=1",
                    (batch_id,),
                )

        def tamper_sample_payload(self, batch_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE historical_samples_v1 "
                    "SET canonical_json=canonical_json || ' ' "
                    "WHERE reading_id=("
                    "SELECT reading_id FROM historical_samples_v1 "
                    "WHERE batch_id=? ORDER BY reading_id LIMIT 1)",
                    (batch_id,),
                )

        def delete_policy(self, policy_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "DELETE FROM collection_policies_v1 WHERE policy_id=?",
                    (policy_id,),
                )

        def insert_policy(self, policy: CollectionPolicyV1) -> None:
            body = policy.model_dump_public()
            values = (
                body["schemaVersion"],
                body["collectionPolicyId"],
                body["assetId"],
                body["timezone"],
                json.dumps(body["activeWeekdays"], separators=(",", ":")),
                body["windowStartLocal"],
                body["windowEndLocal"],
                body["pollIntervalSeconds"],
                body["gapThresholdSeconds"],
                body["effectiveFrom"],
                body["effectiveTo"],
                body["configurationHash"],
            )
            with self.connection() as connection:
                connection.execute(
                    "INSERT INTO collection_policies_v1 ("
                    + ",".join(_POLICY_COLUMNS)
                    + ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    values,
                )

        def tamper_policy_hash(self, policy_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE collection_policies_v1 SET configuration_hash=? "
                    "WHERE policy_id=?",
                    ("sha256:" + "0" * 64, policy_id),
                )

        def tamper_policy_field(self, policy_id: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE collection_policies_v1 SET poll_interval_seconds=6 "
                    "WHERE policy_id=?",
                    (policy_id,),
                )

        def interrupting_repository(
            self,
            operation: str,
            exception_type: type[BaseException],
        ):
            trigger = {
                "stage": "INSERT INTO historical_samples_v1",
                "assessment": "INSERT INTO historical_assessments_v1",
                "activation": (
                    "UPDATE historical_import_batches_v1 SET status='superseded'"
                ),
            }[operation]

            class InterruptingConnection(sqlite3.Connection):
                fired = False

                def _interrupt(self, sql: str) -> None:
                    if not self.fired and _normalized(sql).startswith(trigger):
                        self.fired = True
                        raise exception_type(f"injected {operation} interruption")

                def execute(self, sql, parameters=(), /):
                    cursor = super().execute(sql, parameters)
                    self._interrupt(sql)
                    return cursor

                def executemany(self, sql, parameters, /):
                    cursor = super().executemany(sql, parameters)
                    self._interrupt(sql)
                    return cursor

            def factory(path: Path) -> sqlite3.Connection:
                return sqlite3.connect(
                    path,
                    timeout=5,
                    factory=InterruptingConnection,
                )

            return SQLiteHistoricalRepositoryV1(
                self.path,
                connection_factory=factory,
            )

        def recording_repository(self, statements: list[str]):
            class RecordingConnection(sqlite3.Connection):
                def execute(self, sql, parameters=(), /):
                    statements.append(_normalized(sql))
                    return super().execute(sql, parameters)

                def executemany(self, sql, parameters, /):
                    statements.append(_normalized(sql))
                    return super().executemany(sql, parameters)

            def factory(path: Path) -> sqlite3.Connection:
                return sqlite3.connect(
                    path,
                    timeout=5,
                    factory=RecordingConnection,
                )

            return SQLiteHistoricalRepositoryV1(
                self.path,
                connection_factory=factory,
            )


    @pytest.fixture
    def sqlite_database_path(tmp_path: Path) -> Path:
        path = tmp_path / "task-a4-history.sqlite3"
        assert not path.exists()
        connection = _connect(path)
        try:
            apply_sqlite_migrations(
                connection,
                registered_migration_specs(),
                initial_policy_effective_from=datetime(
                    2026,
                    8,
                    22,
                    12,
                    tzinfo=timezone.utc,
                ),
            )
        finally:
            connection.close()
        assert path.is_file()
        assert path.parent == tmp_path
        return path


    @pytest.fixture
    def historical_repository(sqlite_database_path: Path):
        return SQLiteHistoricalRepositoryV1(sqlite_database_path)


    @pytest.fixture
    def prepared_batch_factory():
        return synthetic_prepared_batch


    @pytest.fixture
    def repository_control(sqlite_database_path: Path):
        return SQLiteRepositoryControl(sqlite_database_path)


    class TestSQLiteHistoricalRepositoryContract(HistoricalRepositoryContract):
        pass


    def test_sqlite_stage_and_activation_lock_before_their_first_write(
        repository_control: SQLiteRepositoryControl,
    ) -> None:
        statements: list[str] = []
        repository = repository_control.recording_repository(statements)
        first = synthetic_prepared_batch(0)
        second = synthetic_prepared_batch(1)

        repository.stage_batch(first)

        begin = statements.index("BEGIN IMMEDIATE")
        first_write = next(
            index
            for index, statement in enumerate(statements)
            if statement.startswith("INSERT INTO historical_import_batches_v1")
        )
        assert begin < first_write
        assert "PRAGMA foreign_keys=ON" in statements[: begin + 1]
        repository.stage_batch(second)
        repository.activate_batch(
            asset_id=first.asset_id,
            batch_id=first.batch_id,
            expected_active_batch_id=None,
        )
        statements.clear()

        repository.activate_batch(
            asset_id=second.asset_id,
            batch_id=second.batch_id,
            expected_active_batch_id=first.batch_id,
        )

        begin = statements.index("BEGIN IMMEDIATE")
        first_write = next(
            index
            for index, statement in enumerate(statements)
            if statement.startswith("UPDATE historical_import_batches_v1")
        )
        assert begin < first_write
        assert "PRAGMA foreign_keys=ON" in statements[: begin + 1]


    def test_pre_begin_callback_runs_immediately_before_every_repository_begin(
        sqlite_database_path: Path,
    ) -> None:
        """Catches a repository write transaction that bypasses the guard callback."""

        events: list[str] = []

        class RecordingConnection(sqlite3.Connection):
            def execute(self, sql, parameters=(), /):
                events.append(_normalized(sql))
                return super().execute(sql, parameters)

            def executemany(self, sql, parameters, /):
                events.append(_normalized(sql))
                return super().executemany(sql, parameters)

        def factory(path: Path) -> sqlite3.Connection:
            return sqlite3.connect(path, timeout=5, factory=RecordingConnection)

        def before_begin(connection: sqlite3.Connection) -> None:
            assert connection.in_transaction is False
            events.append("PRE_BEGIN_CALLBACK")

        repository = SQLiteHistoricalRepositoryV1(
            sqlite_database_path,
            connection_factory=factory,
            before_begin=before_begin,
        )
        first = synthetic_prepared_batch(0)
        second = synthetic_prepared_batch(1)

        repository.stage_batch(first)
        repository.store_assessments(first.batch_id, [_assessment(first)])
        repository.stage_batch(second)
        repository.activate_batch(
            asset_id=first.asset_id,
            batch_id=first.batch_id,
            expected_active_batch_id=None,
        )
        repository.activate_batch(
            asset_id=second.asset_id,
            batch_id=second.batch_id,
            expected_active_batch_id=first.batch_id,
        )

        begin_indexes = [
            index for index, event in enumerate(events) if event == "BEGIN IMMEDIATE"
        ]
        assert len(begin_indexes) == 5
        assert all(events[index - 1] == "PRE_BEGIN_CALLBACK" for index in begin_indexes)


    def test_pre_begin_callback_blocks_connect_begin_aba_before_any_sql_write(
        sqlite_database_path: Path,
        tmp_path: Path,
    ) -> None:
        """Catches an opened-file identity ABA before BEGIN reaches SQLite."""

        replacement = tmp_path / "replacement.sqlite3"
        replacement.write_bytes(sqlite_database_path.read_bytes())
        opened_identity = (
            os.stat(sqlite_database_path).st_dev,
            os.stat(sqlite_database_path).st_ino,
        )
        replacement_before = replacement.read_bytes()
        original_before = sqlite_database_path.read_bytes()
        statements: list[str] = []
        identity_swapped = False

        class AbaConnection(sqlite3.Connection):
            def execute(self, sql, parameters=(), /):
                nonlocal identity_swapped
                normalized = _normalized(sql)
                statements.append(normalized)
                cursor = super().execute(sql, parameters)
                if normalized == "PRAGMA foreign_keys":
                    # SQLite denies renaming its open file on Windows. Substitute
                    # the independently observed pathname identity at the same
                    # connect/BEGIN boundary while retaining a real connection.
                    identity_swapped = True
                return cursor

        def factory(path: Path) -> sqlite3.Connection:
            return sqlite3.connect(path, timeout=5, factory=AbaConnection)

        def verify_opened_identity(connection: sqlite3.Connection) -> None:
            del connection
            current = (
                os.stat(replacement)
                if identity_swapped
                else os.stat(sqlite_database_path)
            )
            if (current.st_dev, current.st_ino) != opened_identity:
                raise RuntimeError("opened SQLite identity changed before BEGIN")

        repository = SQLiteHistoricalRepositoryV1(
            sqlite_database_path,
            connection_factory=factory,
            before_begin=verify_opened_identity,
        )

        with pytest.raises(RuntimeError, match="identity changed before BEGIN"):
            repository.stage_batch(synthetic_prepared_batch(0))

        assert identity_swapped is True
        assert "BEGIN IMMEDIATE" not in statements
        assert not any(
            statement.startswith(("INSERT ", "UPDATE ", "DELETE "))
            for statement in statements
        )
        assert sqlite_database_path.read_bytes() == replacement_before
        assert replacement.read_bytes() == original_before
