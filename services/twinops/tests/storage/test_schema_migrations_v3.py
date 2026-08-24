from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest


SERVICE_ROOT = Path(__file__).parents[2]
SQLITE_MIGRATION = (
    SERVICE_ROOT / "migrations" / "003_unified_history_timeline_sqlite.sql"
)
POSTGRES_MIGRATION = (
    SERVICE_ROOT / "migrations" / "003_unified_history_timeline_postgres.sql"
)
SCHEMA_MODULE = (
    SERVICE_ROOT / "src" / "twinops" / "storage" / "schema_migrations.py"
)
POLICY_MODULE = (
    SERVICE_ROOT / "src" / "twinops" / "storage" / "collection_policy_v1.py"
)
MIGRATION_002 = SERVICE_ROOT / "migrations" / "002_real_twin_v2.sql"
INITIAL_EFFECTIVE_FROM = datetime(2026, 8, 22, tzinfo=timezone.utc)

V3_TABLES = {
    "schema_migrations_v1",
    "deployment_identity_v1",
    "historical_import_batches_v1",
    "historical_raw_rows_v1",
    "historical_samples_v1",
    "historical_assessments_v1",
    "collection_policies_v1",
    "refresh_cycle_policies_v1",
}
V3_INDEXES = {
    "uq_historical_import_batches_v1_active_asset",
    "uq_historical_samples_v1_source_sensor",
    "ix_historical_samples_v1_timeline",
    "ix_historical_assessments_v1_anchor",
    "ix_telemetry_samples_v2_timeline",
}
SURFACE_PATHS = (
    SQLITE_MIGRATION,
    POSTGRES_MIGRATION,
    SCHEMA_MODULE,
    POLICY_MODULE,
)
SURFACE_READY = all(path.is_file() for path in SURFACE_PATHS)
requires_surface = pytest.mark.skipif(
    not SURFACE_READY,
    reason="migration surface has not been implemented",
)


def test_migration_surface_exists_before_behavior_tests_run() -> None:
    if not SURFACE_READY:
        pytest.fail("RED:A2:migration-surface-missing")


@pytest.fixture
def connection():
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys=ON")
    try:
        yield database
    finally:
        database.close()


def _migration_api():
    from twinops.storage import schema_migrations

    return schema_migrations


def _apply_sqlite(connection: sqlite3.Connection):
    migrations = _migration_api()
    migrations.apply_sqlite_migrations(
        connection,
        migrations.registered_migration_specs(),
        initial_policy_effective_from=INITIAL_EFFECTIVE_FROM,
    )
    return migrations


@requires_surface
def test_registered_migration_hashes_are_literal_git_canonical_pins():
    specs = _migration_api().registered_migration_specs()

    assert [
        (
            spec.version,
            spec.sqlite_sha256,
            spec.postgres_sha256,
        )
        for spec in specs
    ] == [
        (
            "002",
            "sha256:79506e293ca563e907d453ee0ae3a367"
            "79b9a23be0550eb84320900ddbab93d9",
            "sha256:79506e293ca563e907d453ee0ae3a367"
            "79b9a23be0550eb84320900ddbab93d9",
        ),
        (
            "003",
            "sha256:55971c74d02b815cb4713a7b8052850"
            "a20708fb190d56bd4486a5066dde22c69",
            "sha256:87baa67ae5f2396f49a70e9b3c348cb"
            "84a235dcc103991d394894bd86da9e173",
        ),
    ]


@requires_surface
def test_sqlite_migration_hashes_accept_git_equivalent_crlf_checkout(
    connection,
    tmp_path,
):
    migrations = _migration_api()
    registered = migrations.registered_migration_specs()
    crlf_paths = []
    for source in (MIGRATION_002, SQLITE_MIGRATION):
        canonical = source.read_bytes().replace(b"\r\n", b"\n")
        assert b"\r" not in canonical
        destination = tmp_path / source.name
        destination.write_bytes(canonical.replace(b"\n", b"\r\n"))
        crlf_paths.append(destination)
    portable_specs = (
        replace(registered[0], sqlite_path=crlf_paths[0]),
        replace(registered[1], sqlite_path=crlf_paths[1]),
    )

    migrations.apply_sqlite_migrations(
        connection,
        portable_specs,
        initial_policy_effective_from=INITIAL_EFFECTIVE_FROM,
    )

    assert migrations.verify_schema_version(connection, "003").is_current is True


@requires_surface
def test_content_tampering_cannot_become_the_registered_hash_or_write_database(
    connection,
    monkeypatch,
    tmp_path,
):
    migrations = _migration_api()
    tampered = tmp_path / SQLITE_MIGRATION.name
    canonical = SQLITE_MIGRATION.read_bytes().replace(b"\r\n", b"\n")
    tampered.write_bytes(
        canonical + b"\nCREATE TABLE controller_tampering_was_executed (id INTEGER);\n"
    )
    monkeypatch.setattr(migrations, "_MIGRATION_003_SQLITE", tampered)
    statements = []
    connection.set_trace_callback(statements.append)

    with pytest.raises(migrations.MigrationStateError, match="hash mismatch"):
        migrations.apply_sqlite_migrations(
            connection,
            migrations.registered_migration_specs(),
            initial_policy_effective_from=INITIAL_EFFECTIVE_FROM,
        )

    assert statements == []
    assert connection.total_changes == 0


@requires_surface
def test_fresh_sqlite_applies_registered_versions_and_all_v3_tables(connection):
    migrations = _apply_sqlite(connection)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    recorded = connection.execute(
        "SELECT migration_version, sql_sha256 "
        "FROM schema_migrations_v1 ORDER BY migration_version"
    ).fetchall()
    verification = migrations.verify_schema_version(connection, "003")

    assert V3_TABLES <= tables
    assert [row[0] for row in recorded] == ["002", "003"]
    assert dict(recorded) == dict(verification.applied_migration_hashes)
    assert verification.expected_version == "003"
    assert verification.current_version == "003"
    assert verification.is_current is True
    assert connection.execute(
        "SELECT COUNT(*) FROM refresh_cycle_policies_v1"
    ).fetchone()[0] == 0


@requires_surface
def test_sqlite_upgrades_an_existing_002_database_inside_explicit_migrator(
    connection,
):
    connection.executescript(MIGRATION_002.read_text(encoding="utf-8"))
    assert connection.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type='table' AND name='schema_migrations_v1'"
    ).fetchone()[0] == 0

    migrations = _apply_sqlite(connection)

    assert migrations.verify_schema_version(connection, "003").is_current is True
    assert [
        row[0]
        for row in connection.execute(
            "SELECT migration_version FROM schema_migrations_v1 "
            "ORDER BY migration_version"
        ).fetchall()
    ] == ["002", "003"]


@requires_surface
def test_sqlite_second_migration_run_is_an_exact_noop(connection):
    _apply_sqlite(connection)
    before_changes = connection.total_changes
    before_policy = connection.execute(
        "SELECT effective_from, effective_to FROM collection_policies_v1 "
        "WHERE policy_id='forzy-live-window-v1'"
    ).fetchone()

    _apply_sqlite(connection)

    after_policy = connection.execute(
        "SELECT effective_from, effective_to FROM collection_policies_v1 "
        "WHERE policy_id='forzy-live-window-v1'"
    ).fetchone()
    assert connection.total_changes == before_changes
    assert tuple(after_policy) == tuple(before_policy)


@requires_surface
def test_recorded_migration_hash_drift_fails_closed_without_writes(connection):
    migrations = _apply_sqlite(connection)
    connection.execute(
        "UPDATE schema_migrations_v1 SET sql_sha256=? "
        "WHERE migration_version='003'",
        ("sha256:" + "0" * 64,),
    )
    connection.commit()
    before_changes = connection.total_changes

    with pytest.raises(migrations.MigrationStateError, match="hash"):
        migrations.apply_sqlite_migrations(
            connection,
            migrations.registered_migration_specs(),
            initial_policy_effective_from=INITIAL_EFFECTIVE_FROM,
        )

    assert connection.total_changes == before_changes


@requires_surface
def test_migrations_use_dialect_specific_binary_and_timestamp_types():
    sqlite_sql = SQLITE_MIGRATION.read_text(encoding="utf-8").upper()
    postgres_sql = POSTGRES_MIGRATION.read_text(encoding="utf-8").upper()

    assert "SOURCE_BYTES BLOB" in sqlite_sql
    assert "SOURCE_BYTES BYTEA" not in sqlite_sql
    assert "TIMESTAMPTZ" not in sqlite_sql
    assert "SOURCE_BYTES BYTEA" in postgres_sql
    assert "TIMESTAMPTZ" in postgres_sql
    assert "SOURCE_BYTES BLOB" not in postgres_sql


@requires_surface
def test_sqlite_schema_has_required_indexes_restrictive_archive_fks_and_checks(
    connection,
):
    _apply_sqlite(connection)

    indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    source_bytes_type = {
        row[1]: row[2]
        for row in connection.execute(
            "PRAGMA table_info(historical_import_batches_v1)"
        ).fetchall()
    }["source_bytes"]

    assert V3_INDEXES <= indexes
    assert source_bytes_type.upper() == "BLOB"
    for table in (
        "historical_raw_rows_v1",
        "historical_samples_v1",
        "historical_assessments_v1",
    ):
        foreign_keys = connection.execute(
            f"PRAGMA foreign_key_list({table})"
        ).fetchall()
        assert foreign_keys
        assert {row[6].upper() for row in foreign_keys} == {"RESTRICT"}

    batch_id = "sha256:" + "a" * 64
    connection.execute(
        "INSERT INTO historical_import_batches_v1 ("
        "batch_id,asset_id,source_name,source_sha256,source_bytes,"
        "source_size_bytes,raw_row_count,sample_count,operating_cycle_count,"
        "timezone_name,parser_version,contract_version,imported_at,status,"
        "manifest_json,manifest_sha256,assessment_count,staged_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            batch_id,
            "forzy-motor-01",
            "synthetic.csv",
            "sha256:" + "b" * 64,
            b"row\r\n",
            5,
            1,
            2,
            1,
            "America/Sao_Paulo",
            "test-parser-v1",
            "1.0",
            "2026-08-22T00:00:00.000Z",
            "staged",
            "{}",
            "sha256:" + "c" * 64,
            0,
            "2026-08-22T00:00:00.000Z",
        ),
    )
    valid_tail = (
        "2026-05-19 12:00:00",
        "{}",
        "sha256:" + "d" * 64,
    )
    for ordinal, line, byte_start, byte_end in (
        (0, 4, 0, 1),
        (1, 0, 0, 1),
        (1, 4, -1, 1),
        (1, 4, 1, 1),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO historical_raw_rows_v1 ("
                "batch_id,record_ordinal,source_line_number,byte_start,byte_end,"
                "source_timestamp_text,canonical_values_json,row_sha256"
                ") VALUES (?,?,?,?,?,?,?,?)",
                (
                    batch_id,
                    ordinal,
                    line,
                    byte_start,
                    byte_end,
                    *valid_tail,
                ),
            )


class _Rows:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _PostgresMigrationConnection:
    def __init__(self, version: str, migration_hash: str, migration_sql: str):
        self.applied = {version: migration_hash}
        self.migration_sql = migration_sql
        self.calls = []

    def execute(self, query, params=None, **kwargs):
        self.calls.append((query, params, kwargs))
        normalized = " ".join(query.split())
        if "to_regclass" in normalized:
            return _Rows([{"relation": "schema_migrations_v1"}])
        if normalized.startswith("SELECT migration_version, sql_sha256"):
            return _Rows(
                {"migration_version": version, "sql_sha256": digest}
                for version, digest in sorted(self.applied.items())
            )
        if "pg_advisory_xact_lock" in normalized:
            return _Rows()
        if query == self.migration_sql:
            return _Rows()
        if normalized.startswith("CREATE TABLE IF NOT EXISTS schema_migrations_v1"):
            return _Rows()
        if normalized.startswith("INSERT INTO schema_migrations_v1"):
            self.applied[params[0]] = params[1]
            return _Rows()
        raise AssertionError(f"unexpected PostgreSQL migration query: {query}")


@requires_surface
def test_postgres_migrator_uses_fixed_lock_recheck_before_exact_ddl(monkeypatch):
    migrations = _migration_api()
    specs = migrations.registered_migration_specs()
    migration_003 = POSTGRES_MIGRATION.read_text(encoding="utf-8")
    connection = _PostgresMigrationConnection(
        "002",
        specs[0].postgres_sha256,
        migration_003,
    )
    seed_calls = []
    monkeypatch.setattr(
        migrations,
        "ensure_initial_collection_policy",
        lambda connection, *, effective_from: seed_calls.append(effective_from),
    )

    migrations.apply_postgres_migrations(
        connection,
        specs,
        initial_policy_effective_from=INITIAL_EFFECTIVE_FROM,
    )

    queries = [call[0] for call in connection.calls]
    lock_index = next(
        index for index, query in enumerate(queries) if "pg_advisory_xact_lock" in query
    )
    ddl_index = queries.index(migration_003)
    state_reads = [
        index
        for index, query in enumerate(queries)
        if "SELECT migration_version, sql_sha256" in query
    ]
    assert any(index < lock_index for index in state_reads)
    assert any(lock_index < index < ddl_index for index in state_reads)
    assert connection.calls[lock_index][1] == (
        migrations.POSTGRES_SCHEMA_MIGRATION_LOCK_KEY,
    )
    assert connection.calls[ddl_index] == (migration_003, None, {"prepare": False})
    assert seed_calls == [INITIAL_EFFECTIVE_FROM]
    assert migrations.verify_schema_version(connection, "003").is_current is True


@requires_surface
def test_fastapi_import_and_construction_do_not_create_or_migrate_database(
    monkeypatch,
):
    from twinops.storage import collection_policy_v1, schema_migrations

    monkeypatch.setattr(
        schema_migrations,
        "apply_sqlite_migrations",
        lambda *args, **kwargs: pytest.fail("migration ran during app construction"),
    )
    monkeypatch.setattr(
        collection_policy_v1,
        "ensure_initial_collection_policy",
        lambda *args, **kwargs: pytest.fail("policy write ran during app construction"),
    )
    from twinops.main_v2 import create_app_v2_from_env

    database_path = Path.cwd() / "task-2-app-construction-must-not-exist.sqlite3"
    assert database_path.exists() is False
    app = create_app_v2_from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "TWINOPS_DATABASE_PATH": str(database_path),
        }
    )

    assert app.state.repository.path == database_path
    assert database_path.exists() is False
