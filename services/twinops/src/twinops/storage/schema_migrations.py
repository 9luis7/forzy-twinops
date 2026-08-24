"""Explicit, hash-pinned schema migration state for SQLite and PostgreSQL."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sqlite3
from types import MappingProxyType
from typing import Literal

from twinops.contracts.timeline_v1_models import Sha256V1
from twinops.storage.collection_policy_v1 import ensure_initial_collection_policy


EnvironmentV1 = Literal["local", "preview", "production"]
EXPECTED_SCHEMA_VERSION = "003"
POSTGRES_SCHEMA_MIGRATION_LOCK_KEY = 0x5457494E4F505332
_MIGRATIONS_DIR = Path(__file__).parents[3] / "migrations"
_MIGRATION_002 = _MIGRATIONS_DIR / "002_real_twin_v2.sql"
_MIGRATION_003_SQLITE = (
    _MIGRATIONS_DIR / "003_unified_history_timeline_sqlite.sql"
)
_MIGRATION_003_POSTGRES = (
    _MIGRATIONS_DIR / "003_unified_history_timeline_postgres.sql"
)
_MIGRATION_002_SHA256 = (
    "sha256:79506e293ca563e907d453ee0ae3a36779b9a23be0550eb84320900ddbab93d9"
)
_MIGRATION_003_SQLITE_SHA256 = (
    "sha256:55971c74d02b815cb4713a7b8052850a20708fb190d56bd4486a5066dde22c69"
)
_MIGRATION_003_POSTGRES_SHA256 = (
    "sha256:87baa67ae5f2396f49a70e9b3c348cb84a235dcc103991d394894bd86da9e173"
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^[0-9]{3}$")
_V2_TABLES = frozenset(
    {
        "collection_attempts_v2",
        "latest_readings_v2",
        "raw_readings_v2",
        "refresh_cycles_v2",
        "telemetry_samples_v2",
    }
)
_V2_INDEXES = frozenset(
    {
        "ix_raw_readings_v2_slot",
        "ix_telemetry_samples_v2_history",
    }
)
_SQLITE_V2_COLUMNS = {
    "telemetry_samples_v2": {
        "reading_id",
        "asset_id",
        "sensor_id",
        "observed_at",
        "received_at",
        "payload_hash",
        "canonical_json",
    },
    "latest_readings_v2": {
        "asset_id",
        "sensor_id",
        "reading_id",
        "received_at",
        "canonical_json",
    },
    "raw_readings_v2": {
        "raw_id",
        "sensor_id",
        "scheduled_at",
        "received_at",
        "payload_hash",
        "payload_json",
    },
    "collection_attempts_v2": {
        "attempt_id",
        "sensor_id",
        "scheduled_at",
        "attempted_at",
        "succeeded",
        "latency_ms",
        "error_code",
    },
    "refresh_cycles_v2": {
        "asset_id",
        "scheduled_at",
        "owner_token",
        "claimed_at",
        "completed_at",
        "outcomes_json",
        "status",
    },
}
_POSTGRES_V2_CURRENT_SQL = (
    "SELECT "
    "(SELECT COUNT(*) FROM pg_catalog.pg_tables "
    "WHERE schemaname='public' AND tablename = ANY(%s)) = %s AS tables_current, "
    "(SELECT COUNT(*) FROM pg_catalog.pg_indexes "
    "WHERE schemaname='public' AND indexname = ANY(%s)) = %s AS indexes_current"
)
_POSTGRES_LOCK_SQL = "SELECT pg_advisory_xact_lock(%s)"
_SQLITE_MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations_v1 (
  migration_version TEXT PRIMARY KEY,
  sql_sha256 TEXT NOT NULL CHECK (
    length(sql_sha256) = 71
    AND substr(sql_sha256, 1, 7) = 'sha256:'
    AND substr(sql_sha256, 8) NOT GLOB '*[^0-9a-f]*'
  ),
  applied_at TEXT NOT NULL CHECK (
    length(applied_at) = 24 AND substr(applied_at, -1) = 'Z'
  )
)
"""
_POSTGRES_MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations_v1 (
  migration_version TEXT PRIMARY KEY,
  sql_sha256 TEXT NOT NULL CHECK (sql_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  applied_at TIMESTAMPTZ NOT NULL
)
"""


class MigrationStateError(RuntimeError):
    """Raised when migration identity or ordering cannot be trusted."""


@dataclass(frozen=True)
class MigrationSpec:
    version: str
    sqlite_path: Path
    postgres_path: Path
    sqlite_sha256: Sha256V1
    postgres_sha256: Sha256V1

    def __post_init__(self) -> None:
        if not _VERSION_RE.fullmatch(self.version):
            raise ValueError("migration version must be three decimal digits")
        for digest in (self.sqlite_sha256, self.postgres_sha256):
            if not _SHA256_RE.fullmatch(digest):
                raise ValueError("migration hash must be canonical sha256")


@dataclass(frozen=True)
class SchemaVerification:
    expected_version: str
    current_version: str | None
    applied_migration_hashes: Mapping[str, Sha256V1]
    is_current: bool


@dataclass(frozen=True)
class DeploymentIdentityV1:
    environment: EnvironmentV1
    label: str
    target_fingerprint: Sha256V1
    schema_version: str


def registered_migration_specs() -> tuple[MigrationSpec, ...]:
    return (
        MigrationSpec(
            version="002",
            sqlite_path=_MIGRATION_002,
            postgres_path=_MIGRATION_002,
            sqlite_sha256=_MIGRATION_002_SHA256,
            postgres_sha256=_MIGRATION_002_SHA256,
        ),
        MigrationSpec(
            version="003",
            sqlite_path=_MIGRATION_003_SQLITE,
            postgres_path=_MIGRATION_003_POSTGRES,
            sqlite_sha256=_MIGRATION_003_SQLITE_SHA256,
            postgres_sha256=_MIGRATION_003_POSTGRES_SHA256,
        ),
    )


def _canonical_sql(path: Path) -> tuple[bytes, str]:
    sql_bytes = path.read_bytes()
    try:
        sql = sql_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MigrationStateError("migration SQL is not strict UTF-8") from exc
    if sql.startswith("\ufeff"):
        raise MigrationStateError("migration SQL must not contain a BOM")
    without_crlf = sql.replace("\r\n", "")
    if "\r" in without_crlf:
        raise MigrationStateError("migration SQL contains a lone carriage return")
    canonical_sql = sql.replace("\r\n", "\n")
    return canonical_sql.encode("utf-8"), canonical_sql


def _validate_specs(
    specs: Sequence[MigrationSpec],
    dialect: Literal["sqlite", "postgres"],
) -> list[tuple[MigrationSpec, str, str]]:
    if not specs:
        raise ValueError("at least one migration spec is required")
    versions = [spec.version for spec in specs]
    if versions != sorted(set(versions)):
        raise ValueError("migration specs must be unique and ordered")
    loaded = []
    for spec in specs:
        path = spec.sqlite_path if dialect == "sqlite" else spec.postgres_path
        expected_hash = (
            spec.sqlite_sha256 if dialect == "sqlite" else spec.postgres_sha256
        )
        canonical_bytes, sql = _canonical_sql(path)
        actual_hash = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
        if actual_hash != expected_hash:
            raise MigrationStateError(
                f"migration {spec.version} checked-in SQL hash mismatch"
            )
        loaded.append((spec, expected_hash, sql))
    return loaded


def _is_sqlite(connection) -> bool:
    return isinstance(connection, sqlite3.Connection)


def _mapping_value(row, key: str, position: int):
    if isinstance(row, Mapping):
        return row[key]
    if hasattr(row, "keys"):
        return row[key]
    return row[position]


def _migration_table_exists(connection) -> bool:
    if _is_sqlite(connection):
        row = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='schema_migrations_v1'"
        ).fetchone()
        return row is not None
    row = connection.execute(
        "SELECT to_regclass('public.schema_migrations_v1') AS relation"
    ).fetchone()
    return row is not None and _mapping_value(row, "relation", 0) is not None


def _recorded_migrations(connection) -> dict[str, str]:
    if not _migration_table_exists(connection):
        return {}
    rows = connection.execute(
        "SELECT migration_version, sql_sha256 "
        "FROM schema_migrations_v1 ORDER BY migration_version"
    ).fetchall()
    recorded: dict[str, str] = {}
    for row in rows:
        version = _mapping_value(row, "migration_version", 0)
        digest = _mapping_value(row, "sql_sha256", 1)
        if (
            not isinstance(version, str)
            or not _VERSION_RE.fullmatch(version)
            or not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
            or version in recorded
        ):
            raise MigrationStateError("stored migration state is malformed")
        recorded[version] = digest
    return recorded


def _expected_hashes(
    specs: Sequence[MigrationSpec],
    dialect: Literal["sqlite", "postgres"],
) -> dict[str, str]:
    return {
        spec.version: (
            spec.sqlite_sha256 if dialect == "sqlite" else spec.postgres_sha256
        )
        for spec in specs
    }


def _verify_against_specs(
    connection,
    specs: Sequence[MigrationSpec],
    dialect: Literal["sqlite", "postgres"],
    expected_version: str,
) -> SchemaVerification:
    recorded = _recorded_migrations(connection)
    expected = {
        version: digest
        for version, digest in _expected_hashes(specs, dialect).items()
        if version <= expected_version
    }
    current_version = max(recorded) if recorded else None
    return SchemaVerification(
        expected_version=expected_version,
        current_version=current_version,
        applied_migration_hashes=MappingProxyType(dict(recorded)),
        is_current=(
            bool(expected)
            and expected_version in expected
            and current_version == expected_version
            and recorded == expected
        ),
    )


def verify_schema_version(
    connection,
    expected_version: str,
) -> SchemaVerification:
    dialect = "sqlite" if _is_sqlite(connection) else "postgres"
    return _verify_against_specs(
        connection,
        registered_migration_specs(),
        dialect,
        expected_version,
    )


def _assert_recorded_hashes(
    recorded: Mapping[str, str],
    expected: Mapping[str, str],
) -> None:
    unknown = set(recorded) - set(expected)
    if unknown:
        raise MigrationStateError("database contains an unknown migration version")
    for version, digest in recorded.items():
        if digest != expected[version]:
            raise MigrationStateError(
                f"recorded migration {version} SQL hash mismatch"
            )


def _sqlite_v2_schema_is_current(connection: sqlite3.Connection) -> bool:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    if not _V2_TABLES <= tables or not _V2_INDEXES <= indexes:
        return False
    for table, expected_columns in _SQLITE_V2_COLUMNS.items():
        actual = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if actual != expected_columns:
            return False
    return True


def _postgres_v2_schema_is_current(connection) -> bool:
    row = connection.execute(
        _POSTGRES_V2_CURRENT_SQL,
        (
            sorted(_V2_TABLES),
            len(_V2_TABLES),
            sorted(_V2_INDEXES),
            len(_V2_INDEXES),
        ),
    ).fetchone()
    if row is None:
        return False
    return bool(
        _mapping_value(row, "tables_current", 0)
        and _mapping_value(row, "indexes_current", 1)
    )


def postgres_v2_schema_is_current(connection) -> bool:
    """Read-only preflight for an unregistered database matching migration 002."""

    return _postgres_v2_schema_is_current(connection)


def read_deployment_identity(connection) -> DeploymentIdentityV1 | None:
    marker = "?" if _is_sqlite(connection) else "%s"
    row = connection.execute(
        "SELECT environment,label,target_fingerprint,schema_version "
        f"FROM deployment_identity_v1 WHERE identity_key={marker}",
        ("primary",),
    ).fetchone()
    if row is None:
        return None
    environment = _mapping_value(row, "environment", 0)
    label = _mapping_value(row, "label", 1)
    fingerprint = _mapping_value(row, "target_fingerprint", 2)
    schema_version = _mapping_value(row, "schema_version", 3)
    if environment not in {"local", "preview", "production"}:
        raise MigrationStateError("stored deployment environment is invalid")
    if not isinstance(label, str) or not label:
        raise MigrationStateError("stored deployment label is invalid")
    if not isinstance(fingerprint, str) or not _SHA256_RE.fullmatch(fingerprint):
        raise MigrationStateError("stored target fingerprint is invalid")
    if not isinstance(schema_version, str) or not _VERSION_RE.fullmatch(
        schema_version
    ):
        raise MigrationStateError("stored deployment schema version is invalid")
    return DeploymentIdentityV1(
        environment=environment,
        label=label,
        target_fingerprint=fingerprint,
        schema_version=schema_version,
    )


def ensure_deployment_identity(
    connection,
    identity: DeploymentIdentityV1,
) -> bool:
    if identity.environment not in {"local", "preview", "production"}:
        raise ValueError("deployment environment is invalid")
    if not identity.label:
        raise ValueError("deployment label is required")
    if not _SHA256_RE.fullmatch(identity.target_fingerprint):
        raise ValueError("target fingerprint must be canonical sha256")
    if not _VERSION_RE.fullmatch(identity.schema_version):
        raise ValueError("deployment schema version is invalid")
    existing = read_deployment_identity(connection)
    if existing is not None:
        if existing == identity:
            return False
        raise MigrationStateError("deployment identity conflict")
    marker = "?" if _is_sqlite(connection) else "%s"
    markers = ",".join([marker] * 5)
    connection.execute(
        "INSERT INTO deployment_identity_v1 "
        "(identity_key,environment,label,target_fingerprint,schema_version) "
        f"VALUES ({markers})",
        (
            "primary",
            identity.environment,
            identity.label,
            identity.target_fingerprint,
            identity.schema_version,
        ),
    )
    if read_deployment_identity(connection) != identity:
        raise MigrationStateError("deployment identity reread failed")
    return True


def _execute_sqlite_script(connection: sqlite3.Connection, sql: str) -> None:
    pending = ""
    for line in sql.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            statement = pending.strip()
            pending = ""
            if statement:
                connection.execute(statement)
    if pending.strip():
        raise MigrationStateError("SQLite migration contains incomplete SQL")


def _applied_at_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _record_sqlite_migration(
    connection: sqlite3.Connection,
    version: str,
    digest: str,
) -> None:
    connection.execute(
        "INSERT INTO schema_migrations_v1 "
        "(migration_version,sql_sha256,applied_at) VALUES (?,?,?)",
        (version, digest, _applied_at_text()),
    )


def _record_postgres_migration(connection, version: str, digest: str) -> None:
    connection.execute(
        "INSERT INTO schema_migrations_v1 "
        "(migration_version,sql_sha256,applied_at) VALUES (%s,%s,%s)",
        (version, digest, datetime.now(timezone.utc)),
    )


def apply_sqlite_migrations(
    connection: sqlite3.Connection,
    specs: Sequence[MigrationSpec],
    *,
    initial_policy_effective_from: datetime,
    deployment_identity: DeploymentIdentityV1 | None = None,
    before_begin: Callable[[sqlite3.Connection], None] | None = None,
) -> None:
    loaded = _validate_specs(specs, "sqlite")
    expected = _expected_hashes(specs, "sqlite")
    if connection.in_transaction:
        raise ValueError("SQLite migrator requires transaction ownership")
    if before_begin is not None:
        before_begin(connection)
    connection.execute("BEGIN IMMEDIATE")
    try:
        had_v2_baseline = _sqlite_v2_schema_is_current(connection)
        connection.execute(_SQLITE_MIGRATION_TABLE_SQL)
        recorded = _recorded_migrations(connection)
        _assert_recorded_hashes(recorded, expected)
        for spec, digest, sql in loaded:
            if spec.version in recorded:
                continue
            if spec.version == "002" and had_v2_baseline:
                _record_sqlite_migration(connection, spec.version, digest)
            else:
                _execute_sqlite_script(connection, sql)
                _record_sqlite_migration(connection, spec.version, digest)
            recorded[spec.version] = digest
        if "003" in expected:
            ensure_initial_collection_policy(
                connection,
                effective_from=initial_policy_effective_from,
            )
        if deployment_identity is not None:
            ensure_deployment_identity(connection, deployment_identity)
        verification = _verify_against_specs(
            connection,
            specs,
            "sqlite",
            specs[-1].version,
        )
        if not verification.is_current:
            raise MigrationStateError("SQLite migration verification failed")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def apply_postgres_migrations(
    connection,
    specs: Sequence[MigrationSpec],
    *,
    initial_policy_effective_from: datetime,
) -> None:
    loaded = _validate_specs(specs, "postgres")
    expected = _expected_hashes(specs, "postgres")
    expected_version = specs[-1].version
    recorded = _recorded_migrations(connection)
    _assert_recorded_hashes(recorded, expected)
    current = _verify_against_specs(
        connection,
        specs,
        "postgres",
        expected_version,
    )
    if not current.is_current:
        connection.execute(
            _POSTGRES_LOCK_SQL,
            (POSTGRES_SCHEMA_MIGRATION_LOCK_KEY,),
        )
        recorded = _recorded_migrations(connection)
        _assert_recorded_hashes(recorded, expected)
        current = _verify_against_specs(
            connection,
            specs,
            "postgres",
            expected_version,
        )
        if not current.is_current:
            had_v2_baseline = (
                "002" not in recorded and _postgres_v2_schema_is_current(connection)
            )
            connection.execute(_POSTGRES_MIGRATION_TABLE_SQL)
            recorded = _recorded_migrations(connection)
            _assert_recorded_hashes(recorded, expected)
            for spec, digest, sql in loaded:
                if spec.version in recorded:
                    continue
                if spec.version == "002" and had_v2_baseline:
                    _record_postgres_migration(connection, spec.version, digest)
                else:
                    connection.execute(sql, prepare=False)
                    _record_postgres_migration(connection, spec.version, digest)
                recorded[spec.version] = digest
    ensure_initial_collection_policy(
        connection,
        effective_from=initial_policy_effective_from,
    )
    verification = _verify_against_specs(
        connection,
        specs,
        "postgres",
        expected_version,
    )
    if not verification.is_current:
        raise MigrationStateError("PostgreSQL migration verification failed")
