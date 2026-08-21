from pathlib import Path
from types import SimpleNamespace

from scripts import check_postgres


MIGRATION_PATH = (
    Path(__file__).parents[1] / "migrations" / "002_real_twin_v2.sql"
)


class _Rows:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _SuccessfulConnection:
    def __init__(self, migration, *, indexes=None, schema_checks=(False, False)):
        self.migration = migration
        self.calls = []
        self.probe_id = None
        self.pgconn = SimpleNamespace(ssl_in_use=True)
        self.schema_checks = iter(schema_checks)
        self.indexes = indexes or (
            "ix_raw_readings_v2_slot",
            "ix_telemetry_samples_v2_history",
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None, **kwargs):
        self.calls.append((query, params, kwargs))
        if "AS tables_current" in query:
            current = next(self.schema_checks)
            return _Rows([(current, current)])
        if "pg_advisory_xact_lock" in query:
            return _Rows()
        if query == self.migration:
            return _Rows()
        if "FROM pg_catalog.pg_tables" in query:
            return _Rows(
                (name,)
                for name in (
                    "collection_attempts_v2",
                    "latest_readings_v2",
                    "raw_readings_v2",
                    "refresh_cycles_v2",
                    "telemetry_samples_v2",
                )
            )
        if "FROM pg_catalog.pg_indexes" in query:
            return _Rows((name,) for name in self.indexes)
        if query.startswith("INSERT INTO telemetry_samples_v2"):
            self.probe_id = params[0]
            return _Rows()
        if query.startswith("SELECT reading_id FROM telemetry_samples_v2"):
            return _Rows([(self.probe_id,)])
        if query.startswith("DELETE FROM telemetry_samples_v2"):
            self.probe_id = None
            return _Rows()
        if query.startswith("SELECT COUNT(*) FROM telemetry_samples_v2"):
            return _Rows([(0,)])
        raise AssertionError(f"unexpected query boundary: {query}")


def test_check_postgres_requires_database_url_without_connecting(capsys):
    def forbidden_connect(*args, **kwargs):
        raise AssertionError("database connect must not run without DATABASE_URL")

    result = check_postgres.main(
        ["--migrate", str(MIGRATION_PATH)],
        env={},
        connect=forbidden_connect,
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.strip() == "postgres_check_failed error_type=ValueError"


def test_check_postgres_applies_exact_migration_and_verifies_runtime_contract(capsys):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    connection = _SuccessfulConnection(migration)
    database_url = "postgresql://user:secret@database.invalid/twinops"
    connected_with = []

    def connect(dsn):
        connected_with.append(dsn)
        return connection

    result = check_postgres.main(
        ["--migrate", str(MIGRATION_PATH)],
        env={"DATABASE_URL": database_url},
        connect=connect,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert connected_with == [database_url]
    assert [
        "schema" if "AS tables_current" in query else "lock"
        if "pg_advisory_xact_lock" in query
        else "migration"
        if query == migration
        else "probe"
        for query, _, _ in connection.calls[:4]
    ] == ["schema", "lock", "schema", "migration"]
    assert connection.calls[1][1] == (
        check_postgres.POSTGRES_SCHEMA_MIGRATION_LOCK_KEY,
    )
    assert connection.calls[3] == (migration, None, {"prepare": False})
    assert captured.out.strip() == (
        "postgres_check_ok tables=5 indexes=2 ssl=true probe=passed"
    )
    assert captured.err == ""
    assert database_url not in captured.out + captured.err


def test_check_postgres_skips_migration_and_lock_for_current_schema(capsys):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    connection = _SuccessfulConnection(migration, schema_checks=(True,))

    result = check_postgres.main(
        ["--migrate", str(MIGRATION_PATH)],
        env={"DATABASE_URL": "postgresql://redacted.invalid/twinops"},
        connect=lambda dsn: connection,
    )

    assert result == 0
    assert not any(query == migration for query, _, _ in connection.calls)
    assert not any(
        "pg_advisory_xact_lock" in query for query, _, _ in connection.calls
    )
    assert capsys.readouterr().err == ""


def test_check_postgres_skips_ddl_after_recheck_under_shared_lock(capsys):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    connection = _SuccessfulConnection(migration, schema_checks=(False, True))

    result = check_postgres.main(
        ["--migrate", str(MIGRATION_PATH)],
        env={"DATABASE_URL": "postgresql://redacted.invalid/twinops"},
        connect=lambda dsn: connection,
    )

    assert result == 0
    assert not any(query == migration for query, _, _ in connection.calls)
    lock_calls = [
        call for call in connection.calls if "pg_advisory_xact_lock" in call[0]
    ]
    assert len(lock_calls) == 1
    assert lock_calls[0][1] == (
        check_postgres.POSTGRES_SCHEMA_MIGRATION_LOCK_KEY,
    )
    assert capsys.readouterr().err == ""


def test_check_postgres_reports_safe_validation_stage_without_dsn(capsys):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    database_url = "postgresql://user:secret@database.invalid/twinops"
    connection = _SuccessfulConnection(
        migration,
        indexes=("ix_raw_readings_v2_slot",),
    )

    result = check_postgres.main(
        ["--migrate", str(MIGRATION_PATH)],
        env={"DATABASE_URL": database_url},
        connect=lambda dsn: connection,
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.strip() == (
        "postgres_check_failed error_type=PostgresCheckError stage=indexes"
    )
    assert database_url not in captured.err
