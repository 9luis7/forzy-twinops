import json
import os
from contextlib import contextmanager
import threading

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
