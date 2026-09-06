import json
import os
from contextlib import contextmanager
import threading
from unittest.mock import Mock

import psycopg
import pytest

from test_sqlite_v2_repository import repository_contract as assert_repository_contract
from twinops.storage import postgres_repository


@pytest.fixture
def repository_contract():
    return assert_repository_contract


@pytest.fixture
def postgres_repo():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not configured")

    from twinops.storage.postgres_repository import PostgresTelemetryRepository

    repository = PostgresTelemetryRepository(database_url)
    repository.initialize()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "TRUNCATE TABLE refresh_cycles_v2, collection_attempts_v2, "
            "raw_readings_v2, latest_readings_v2, telemetry_samples_v2"
        )
    try:
        yield repository
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "TRUNCATE TABLE refresh_cycles_v2, collection_attempts_v2, "
                "raw_readings_v2, latest_readings_v2, telemetry_samples_v2"
            )


@pytest.mark.postgres
def test_postgres_repository_satisfies_shared_contract(
    postgres_repo, repository_contract
):
    repository_contract(postgres_repo)

    with psycopg.connect(postgres_repo.database_url) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM raw_readings_v2 ORDER BY scheduled_at"
        ).fetchall()

    expected_payload = {
        "dados1": {
            "Velocidade": 0.12,
            "Aceleração": 0.0,
            "Temperatura": 34,
        }
    }
    assert len(rows) == 2
    assert [json.loads(row[0]) for row in rows] == [
        expected_payload,
        expected_payload,
    ]


class _OneRow:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _SchemaConnection:
    def __init__(self, schema_states):
        self.schema_states = iter(schema_states)
        self.calls = []

    def execute(self, query, params=None, **kwargs):
        self.calls.append((query, params, kwargs))
        if "AS tables_current" in query:
            current = next(self.schema_states)
            return _OneRow(
                {"tables_current": current, "indexes_current": current}
            )
        return _OneRow(None)


class _TimeoutCursor:
    def __init__(self, calls, *, fail_on_data=False):
        self.calls = calls
        self.fail_on_data = fail_on_data
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.closed = True
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if self.fail_on_data and "latest_readings_v2" in query:
            raise psycopg.errors.QueryCanceled("statement timeout")
        return self

    def fetchall(self):
        return []


class _TimeoutConnection:
    def __init__(self):
        self.calls = []
        self.cursors = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.closed = True
        return False

    def cursor(self):
        cursor = _TimeoutCursor(
            self.calls,
            fail_on_data=bool(self.cursors),
        )
        self.cursors.append(cursor)
        return cursor


def test_snapshot_read_statement_timeout_closes_cursor_and_connection():
    connection = _TimeoutConnection()
    repository = postgres_repository.PostgresTelemetryRepository(
        "redacted",
        connection_factory=lambda: connection,
        connect_timeout_seconds=1,
        statement_timeout_ms=250,
    )

    with pytest.raises(psycopg.errors.QueryCanceled):
        repository.latest("forzy-motor-01")

    assert "set_config('statement_timeout'" in connection.calls[0][0]
    assert connection.calls[0][1] == ("250",)
    assert connection.closed is True
    assert len(connection.cursors) == 2
    assert all(cursor.closed for cursor in connection.cursors)


def test_postgres_connect_uses_bounded_connect_timeout(monkeypatch):
    connection = _TimeoutConnection()
    connect = Mock(return_value=connection)
    monkeypatch.setattr(postgres_repository.psycopg, "connect", connect)
    repository = postgres_repository.PostgresTelemetryRepository(
        "redacted",
        connect_timeout_seconds=3,
        statement_timeout_ms=3_000,
    )

    with repository._connection():
        pass

    connect.assert_called_once_with(
        "redacted",
        row_factory=postgres_repository.dict_row,
        connect_timeout=3,
    )
    assert connection.closed is True


def test_snapshot_read_reuses_one_bounded_postgres_connection():
    connection = _TimeoutConnection()
    connection.execute = Mock(
        side_effect=[_Rows([]), _Rows([]), _Rows([])]
    )
    connection_factory = Mock(return_value=connection)
    repository = postgres_repository.PostgresTelemetryRepository(
        "redacted",
        connection_factory=connection_factory,
        connect_timeout_seconds=1,
        statement_timeout_ms=250,
    )

    reader = getattr(repository, "snapshot_read", None)
    assert reader is not None, "atomic PostgreSQL snapshot read is missing"
    result = reader(
        "forzy-motor-01",
        sensor_ids=("s1", "s2"),
        history_limit_per_sensor=1000,
    )

    assert result.latest == ()
    assert result.history == ()
    assert result.health == ()
    connection_factory.assert_called_once_with()
    assert connection.closed is True
    assert len(connection.cursors) == 1
    assert connection.execute.call_count == 3


def test_initialize_skips_migration_file_and_lock_when_schema_is_current(monkeypatch):
    connection = _SchemaConnection([True])
    repository = postgres_repository.PostgresTelemetryRepository("redacted")

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(repository, "_connection", fake_connection)

    repository.initialize()

    assert len(connection.calls) == 1
    assert "AS tables_current" in connection.calls[0][0]


def test_schema_migration_rechecks_after_fixed_transaction_lock():
    connection = _SchemaConnection([False, False])
    migration = "SELECT 'exact migration';"

    applied = postgres_repository.ensure_postgres_schema(
        connection,
        lambda: migration,
    )

    assert applied is True
    assert [
        "schema" if "AS tables_current" in query else "lock"
        if "pg_advisory_xact_lock" in query
        else "migration"
        for query, _, _ in connection.calls
    ] == ["schema", "lock", "schema", "migration"]
    assert connection.calls[1][1] == (
        postgres_repository.POSTGRES_SCHEMA_MIGRATION_LOCK_KEY,
    )
    assert connection.calls[-1] == (migration, None, {"prepare": False})


def test_schema_migration_skips_ddl_when_other_cold_start_wins_lock():
    connection = _SchemaConnection([False, True])

    applied = postgres_repository.ensure_postgres_schema(
        connection,
        lambda: (_ for _ in ()).throw(AssertionError("migration read")),
    )

    assert applied is False
    assert [
        "schema" if "AS tables_current" in query else "lock"
        for query, _, _ in connection.calls
    ] == ["schema", "lock", "schema"]


class _ConcurrentSchema:
    def __init__(self):
        self.current = False
        self.migration_count = 0
        self.lock_count = 0
        self.initial_checks = threading.Barrier(2)
        self.migration_lock = threading.Lock()


class _ConcurrentConnection:
    def __init__(self, shared):
        self.shared = shared
        self.holds_lock = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.holds_lock:
            self.shared.migration_lock.release()
        return False

    def execute(self, query, params=None, **kwargs):
        if "AS tables_current" in query:
            current = self.shared.current
            if not self.holds_lock:
                self.shared.initial_checks.wait(timeout=5)
            return _OneRow(
                {"tables_current": current, "indexes_current": current}
            )
        if "pg_advisory_xact_lock" in query:
            self.shared.migration_lock.acquire(timeout=5)
            self.holds_lock = True
            self.shared.lock_count += 1
            return _OneRow(None)
        if query == "SELECT 'exact migration';":
            assert self.holds_lock is True
            self.shared.migration_count += 1
            self.shared.current = True
            return _OneRow(None)
        raise AssertionError(f"unexpected query: {query}")


def test_two_concurrent_cold_starts_apply_migration_once():
    shared = _ConcurrentSchema()
    applied = []
    failures = []

    def initialize():
        try:
            with _ConcurrentConnection(shared) as connection:
                applied.append(
                    postgres_repository.ensure_postgres_schema(
                        connection,
                        lambda: "SELECT 'exact migration';",
                    )
                )
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [threading.Thread(target=initialize) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert failures == []
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(applied) == [False, True]
    assert shared.lock_count == 2
    assert shared.migration_count == 1
