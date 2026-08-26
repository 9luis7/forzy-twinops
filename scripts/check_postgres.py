"""Explicitly migrate and safely verify the TwinOps PostgreSQL schema."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import psycopg

from twinops.contracts.timeline_v1_models import parse_public_utc_millis_v1
from twinops.storage.collection_policy_v1 import (
    INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH,
    INITIAL_COLLECTION_POLICY_ID,
    initial_collection_policy,
    read_collection_policy,
)
from twinops.storage.schema_migrations import (
    DeploymentIdentityV1,
    POSTGRES_SCHEMA_MIGRATION_LOCK_KEY,
    apply_postgres_migrations,
    ensure_deployment_identity,
    postgres_v2_schema_is_current,
    read_deployment_identity,
    registered_migration_specs,
    verify_schema_version,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_MIGRATIONS = (
    _REPOSITORY_ROOT / "services" / "twinops" / "migrations" / "002_real_twin_v2.sql",
    _REPOSITORY_ROOT
    / "services"
    / "twinops"
    / "migrations"
    / "003_unified_history_timeline_postgres.sql",
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
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
        "collection_attempts_v2_pkey",
        "latest_readings_v2_pkey",
        "raw_readings_v2_pkey",
        "refresh_cycles_v2_pkey",
        "telemetry_samples_v2_pkey",
        "ix_raw_readings_v2_slot",
        "ix_telemetry_samples_v2_history",
    }
)
POSTGRES_V2_REQUIRED_RELATIONS = frozenset(
    {(name, "r") for name in POSTGRES_V2_REQUIRED_TABLES}
    | {(name, "i") for name in POSTGRES_V2_REQUIRED_INDEXES}
)
POSTGRES_V3_REQUIRED_TABLES = frozenset(
    {
        "collection_attempts_v2",
        "latest_readings_v2",
        "raw_readings_v2",
        "refresh_cycles_v2",
        "telemetry_samples_v2",
        "schema_migrations_v1",
        "deployment_identity_v1",
        "historical_import_batches_v1",
        "historical_raw_rows_v1",
        "historical_samples_v1",
        "historical_assessments_v1",
        "collection_policies_v1",
        "refresh_cycle_policies_v1",
    }
)
POSTGRES_V3_REQUIRED_INDEXES = frozenset(
    {
        "ix_raw_readings_v2_slot",
        "ix_telemetry_samples_v2_history",
        "uq_historical_import_batches_v1_active_asset",
        "uq_historical_samples_v1_source_sensor",
        "ix_historical_samples_v1_timeline",
        "ix_historical_assessments_v1_anchor",
        "ix_collection_policies_v1_effective",
        "ix_telemetry_samples_v2_timeline",
    }
)


class PostgresCheckError(RuntimeError):
    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid checker arguments")


def _parse_args(argv: Sequence[str] | None):
    parser = _SafeArgumentParser(description=__doc__)
    parser.add_argument("--migrate", action="append", required=True, type=Path)
    parser.add_argument(
        "--environment",
        required=True,
        choices=("preview", "production"),
    )
    parser.add_argument("--expected-target-label", required=True)
    parser.add_argument("--expected-target-fingerprint", required=True)
    parser.add_argument(
        "--expected-current-version",
        required=True,
        choices=("empty", "002", "003"),
    )
    parser.add_argument("--initial-policy-effective-from", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-plan-sha256")
    parsed = parser.parse_args(argv)
    resolved = tuple(path.resolve() for path in parsed.migrate)
    expected = tuple(path.resolve() for path in _EXPECTED_MIGRATIONS)
    if resolved != expected:
        raise ValueError("unexpected migration path set")
    if not parsed.expected_target_label:
        raise ValueError("expected target label is required")
    if not _SHA256_RE.fullmatch(parsed.expected_target_fingerprint):
        raise ValueError("expected target fingerprint must be canonical sha256")
    try:
        parsed.initial_policy_effective_from = parse_public_utc_millis_v1(
            parsed.initial_policy_effective_from
        )
    except Exception as exc:
        raise ValueError("initial policy effective time must be RFC3339 UTC") from exc
    parsed.mode = "apply" if parsed.apply else "dry-run"
    if parsed.expected_plan_sha256 is not None and not _SHA256_RE.fullmatch(
        parsed.expected_plan_sha256
    ):
        raise ValueError("expected plan hash must be canonical sha256")
    if (
        parsed.expected_current_version in {"empty", "002"}
        and parsed.mode == "apply"
        and parsed.expected_plan_sha256 is None
    ):
        raise ValueError("schema-changing apply requires approved dry-run plan hash")
    if parsed.mode == "dry-run" and parsed.expected_plan_sha256 is not None:
        raise ValueError("dry-run rejects expected plan hash")
    return parsed


def compute_postgres_target_fingerprint(
    *,
    project_id: str,
    branch_id: str,
    database: str,
    schema: str,
) -> str:
    if not all((project_id, branch_id, database, schema)):
        raise ValueError("target identity components are required")
    payload = {
        "branchId": branch_id,
        "database": database,
        "kind": "remote-postgres",
        "projectId": project_id,
        "schema": schema,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _target_identity_parts(env: Mapping[str, str]) -> tuple[str, str]:
    project_id = env.get("TWINOPS_TARGET_PROJECT_ID")
    branch_id = env.get("TWINOPS_TARGET_BRANCH_ID")
    if not project_id or not branch_id:
        raise ValueError("target project and branch identity are required")
    return project_id, branch_id


def _target_fingerprint(connection, env: Mapping[str, str]) -> str:
    project_id, branch_id = _target_identity_parts(env)
    row = connection.execute(
        "SELECT current_database(), current_schema()"
    ).fetchone()
    if row is None:
        raise PostgresCheckError("target_identity")
    if isinstance(row, Mapping):
        database = row["current_database"]
        schema = row["current_schema"]
    else:
        database, schema = row
    return compute_postgres_target_fingerprint(
        project_id=project_id,
        branch_id=branch_id,
        database=database,
        schema=schema,
    )


def _preflight_schema_version(connection, expected_version: str):
    if expected_version == "empty":
        verification = verify_schema_version(connection, "003")
        if (
            verification.current_version is not None
            or verification.applied_migration_hashes
            or _public_user_relations(connection)
            or _catalog_names(
                connection,
                kind="tables",
                expected=POSTGRES_V3_REQUIRED_TABLES,
            )
            or _catalog_names(
                connection,
                kind="indexes",
                expected=POSTGRES_V3_REQUIRED_INDEXES,
            )
        ):
            raise PostgresCheckError("schema_version")
        return verification
    verification = verify_schema_version(connection, expected_version)
    if verification.is_current:
        return verification
    if (
        expected_version == "002"
        and verification.current_version is None
        and postgres_v2_schema_is_current(connection)
    ):
        if _public_user_relations(connection) != POSTGRES_V2_REQUIRED_RELATIONS:
            raise PostgresCheckError("schema_version")
        return verification
    raise PostgresCheckError("schema_version")


def _deployment_identity_table_exists(connection) -> bool:
    row = connection.execute(
        "SELECT to_regclass('public.deployment_identity_v1') AS relation"
    ).fetchone()
    if row is None:
        raise PostgresCheckError("target_identity")
    relation = row["relation"] if isinstance(row, Mapping) else row[0]
    return relation is not None


def _preflight_deployment_identity(connection, args, fingerprint: str):
    expected = DeploymentIdentityV1(
        environment=args.environment,
        label=args.expected_target_label,
        target_fingerprint=fingerprint,
        schema_version="003",
    )
    table_exists = _deployment_identity_table_exists(connection)
    if args.expected_current_version in {"empty", "002"}:
        if table_exists:
            raise PostgresCheckError("target_identity")
        return expected
    if not table_exists:
        raise PostgresCheckError("target_identity")
    try:
        existing = read_deployment_identity(connection)
    except Exception as exc:
        raise PostgresCheckError("target_identity") from exc
    if existing != expected:
        raise PostgresCheckError("target_identity")
    return expected


def _catalog_names(connection, *, kind: str, expected: frozenset[str]) -> set[str]:
    if kind == "tables":
        query = (
            "SELECT tablename FROM pg_catalog.pg_tables "
            "WHERE schemaname='public' AND tablename = ANY(%s)"
        )
    else:
        query = (
            "SELECT indexname FROM pg_catalog.pg_indexes "
            "WHERE schemaname='public' AND indexname = ANY(%s)"
        )
    return {
        row[0] if not isinstance(row, Mapping) else next(iter(row.values()))
        for row in connection.execute(query, (sorted(expected),)).fetchall()
    }


def _public_user_relations(connection) -> set[tuple[str, str]]:
    rows = connection.execute(
        "SELECT c.relname,c.relkind FROM pg_catalog.pg_class AS c "
        "JOIN pg_catalog.pg_namespace AS n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' "
        "ORDER BY c.relkind,c.relname"
    ).fetchall()
    return {
        (
            row[0] if not isinstance(row, Mapping) else row["relname"],
            row[1] if not isinstance(row, Mapping) else row["relkind"],
        )
        for row in rows
    }


def _migration_hashes(specs) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for spec in specs:
        try:
            sql = spec.postgres_path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise PostgresCheckError("migration_identity") from exc
        if sql.startswith("\ufeff") or "\r" in sql.replace("\r\n", ""):
            raise PostgresCheckError("migration_identity")
        canonical = sql.replace("\r\n", "\n").encode("utf-8")
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        if digest != spec.postgres_sha256:
            raise PostgresCheckError("migration_identity")
        hashes[spec.version] = digest
    return hashes


def _pending_migration_versions(expected_current_version: str) -> list[str]:
    if expected_current_version == "empty":
        return ["002", "003"]
    if expected_current_version == "002":
        return ["003"]
    return []


def _operation(expected_current_version: str) -> str:
    if expected_current_version == "empty":
        return "bootstrap-empty"
    if expected_current_version == "002":
        return "upgrade-002"
    return "verify-003"


def _planned_administrative_write_count(*, args, before, specs) -> int:
    missing_registry_rows = sum(
        spec.version not in before.applied_migration_hashes for spec in specs
    )
    return missing_registry_rows + (
        0 if args.expected_current_version == "003" else 2
    )


def _plan_sha256(
    *,
    args,
    before,
    fingerprint: str,
    migration_hashes: Mapping[str, str],
    planned_writes: int,
) -> str:
    policy = initial_collection_policy(args.initial_policy_effective_from)
    payload = {
        "beforeSchemaVersion": before.current_version,
        "environment": args.environment,
        "expectedCurrentVersion": args.expected_current_version,
        "indexes": sorted(POSTGRES_V3_REQUIRED_INDEXES),
        "migrationSha256s": dict(migration_hashes),
        "operation": _operation(args.expected_current_version),
        "plannedAdministrativeWriteCount": planned_writes,
        "policy": policy.model_dump_public(),
        "recordedMigrationSha256s": dict(before.applied_migration_hashes),
        "tables": sorted(POSTGRES_V3_REQUIRED_TABLES),
        "targetFingerprint": fingerprint,
        "targetLabel": args.expected_target_label,
        "targetSchemaVersion": "003",
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _verify_current_database(connection, args):
    tables = _catalog_names(
        connection,
        kind="tables",
        expected=POSTGRES_V3_REQUIRED_TABLES,
    )
    if tables != POSTGRES_V3_REQUIRED_TABLES:
        raise PostgresCheckError("tables")
    indexes = _catalog_names(
        connection,
        kind="indexes",
        expected=POSTGRES_V3_REQUIRED_INDEXES,
    )
    if indexes != POSTGRES_V3_REQUIRED_INDEXES:
        raise PostgresCheckError("indexes")
    expected_policy = initial_collection_policy(args.initial_policy_effective_from)
    policy = read_collection_policy(connection, INITIAL_COLLECTION_POLICY_ID)
    if (
        policy is None
        or policy.model_dump_public() != expected_policy.model_dump_public()
    ):
        raise PostgresCheckError("policy")
    policy_count_row = connection.execute(
        "SELECT COUNT(*) FROM collection_policies_v1"
    ).fetchone()
    if policy_count_row is None or policy_count_row[0] != 1:
        raise PostgresCheckError("policy")
    return len(tables), len(indexes), 1


def _result(
    *,
    args,
    fingerprint: str,
    migration_hashes: Mapping[str, str],
    pending_versions: list[str],
    planned_writes: int,
    plan_sha256: str,
    writes_performed: int,
) -> dict[str, object]:
    policy = initial_collection_policy(args.initial_policy_effective_from)
    public_policy = policy.model_dump_public()
    before_schema = (
        None
        if args.expected_current_version == "empty"
        else args.expected_current_version
    )
    return {
        "beforeSchemaVersion": before_schema,
        "command": "migrate-postgres",
        "environment": args.environment,
        "expectedCurrentVersion": args.expected_current_version,
        "initialPolicyEffectiveFrom": public_policy["effectiveFrom"],
        "migrationSha256s": dict(migration_hashes),
        "mode": args.mode,
        "operation": _operation(args.expected_current_version),
        "pendingMigrationVersions": pending_versions,
        "planSha256": plan_sha256,
        "plannedAdministrativeWriteCount": planned_writes,
        "policyConfigurationHash": INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH,
        "policyId": INITIAL_COLLECTION_POLICY_ID,
        "schemaVersion": "003" if args.mode == "apply" else before_schema,
        "targetFingerprint": fingerprint,
        "targetIndexCount": len(POSTGRES_V3_REQUIRED_INDEXES),
        "targetSchemaVersion": "003",
        "targetTableCount": len(POSTGRES_V3_REQUIRED_TABLES),
        "verified": True,
        "writesPerformed": writes_performed,
    }


def _verify_database(
    database_url: str,
    args,
    env: Mapping[str, str],
    connect,
) -> dict[str, object]:
    specs = registered_migration_specs()
    migration_hashes = _migration_hashes(specs)
    with connect(database_url) as connection:
        if connection.pgconn.ssl_in_use is not True:
            raise PostgresCheckError("tls")
        if args.mode == "dry-run":
            connection.execute("SET TRANSACTION READ ONLY")
        fingerprint = _target_fingerprint(connection, env)
        if fingerprint != args.expected_target_fingerprint:
            raise PostgresCheckError("target_identity")
        before = _preflight_schema_version(
            connection, args.expected_current_version
        )
        identity = _preflight_deployment_identity(connection, args, fingerprint)
        pending_versions = _pending_migration_versions(
            args.expected_current_version
        )
        planned_writes = _planned_administrative_write_count(
            args=args,
            before=before,
            specs=specs,
        )
        plan_sha256 = _plan_sha256(
            args=args,
            before=before,
            fingerprint=fingerprint,
            migration_hashes=migration_hashes,
            planned_writes=planned_writes,
        )
        if (
            args.expected_current_version in {"empty", "002"}
            and args.mode == "apply"
            and args.expected_plan_sha256 != plan_sha256
        ):
            raise PostgresCheckError("plan_identity")

        if args.mode == "dry-run":
            if args.expected_current_version == "003":
                _verify_current_database(connection, args)
            return _result(
                args=args,
                fingerprint=fingerprint,
                migration_hashes=migration_hashes,
                pending_versions=pending_versions,
                planned_writes=planned_writes,
                plan_sha256=plan_sha256,
                writes_performed=0,
            )

        if args.expected_current_version in {"empty", "002"}:
            connection.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (POSTGRES_SCHEMA_MIGRATION_LOCK_KEY,),
            )
            if _target_fingerprint(connection, env) != fingerprint:
                raise PostgresCheckError("target_identity")
            locked_before = _preflight_schema_version(
                connection, args.expected_current_version
            )
            _preflight_deployment_identity(connection, args, fingerprint)
            locked_planned_writes = _planned_administrative_write_count(
                args=args,
                before=locked_before,
                specs=specs,
            )
            locked_plan_sha256 = _plan_sha256(
                args=args,
                before=locked_before,
                fingerprint=fingerprint,
                migration_hashes=migration_hashes,
                planned_writes=locked_planned_writes,
            )
            if (
                locked_plan_sha256 != plan_sha256
                or args.expected_plan_sha256 != locked_plan_sha256
            ):
                raise PostgresCheckError("plan_identity")

        apply_postgres_migrations(
            connection,
            specs,
            initial_policy_effective_from=args.initial_policy_effective_from,
        )
        ensure_deployment_identity(connection, identity)
        if read_deployment_identity(connection) != identity:
            raise PostgresCheckError("target_identity")
        if not verify_schema_version(connection, "003").is_current:
            raise PostgresCheckError("schema_version")
        _verify_current_database(connection, args)
        return _result(
            args=args,
            fingerprint=fingerprint,
            migration_hashes=migration_hashes,
            pending_versions=pending_versions,
            planned_writes=planned_writes,
            plan_sha256=plan_sha256,
            writes_performed=planned_writes,
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    connect: Callable[..., object] = psycopg.connect,
) -> int:
    try:
        source_env = os.environ if env is None else env
        database_url = source_env.get("POSTGRES_URL_NON_POOLING") or source_env.get(
            "DATABASE_URL"
        )
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        args = _parse_args(argv)
        project_id, branch_id = _target_identity_parts(source_env)
        if args.expected_target_label != f"{project_id}/{branch_id}":
            raise PostgresCheckError("target_identity")
        result = _verify_database(
            database_url,
            args,
            source_env,
            connect,
        )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
        return 0
    except Exception as exc:
        stage = f" stage={exc.stage}" if isinstance(exc, PostgresCheckError) else ""
        print(
            f"postgres_check_failed error_type={type(exc).__name__}{stage}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
