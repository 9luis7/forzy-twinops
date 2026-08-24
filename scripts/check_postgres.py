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
    INITIAL_COLLECTION_POLICY_ID,
    read_collection_policy,
)
from twinops.storage.schema_migrations import (
    DeploymentIdentityV1,
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
        choices=("002", "003"),
    )
    parser.add_argument("--initial-policy-effective-from", required=True)
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


def _target_fingerprint(connection, env: Mapping[str, str]) -> str:
    project_id = env.get("TWINOPS_TARGET_PROJECT_ID")
    branch_id = env.get("TWINOPS_TARGET_BRANCH_ID")
    if not project_id or not branch_id:
        raise ValueError("target project and branch identity are required")
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


def _preflight_schema_version(connection, expected_version: str) -> None:
    verification = verify_schema_version(connection, expected_version)
    if verification.is_current:
        return
    if (
        expected_version == "002"
        and verification.current_version is None
        and postgres_v2_schema_is_current(connection)
    ):
        return
    raise PostgresCheckError("schema_version")


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


def _verify_database(
    database_url: str,
    args,
    env: Mapping[str, str],
    connect,
) -> tuple[int, int, int, str, str]:
    specs = registered_migration_specs()
    with connect(database_url) as connection:
        if connection.pgconn.ssl_in_use is not True:
            raise PostgresCheckError("tls")
        fingerprint = _target_fingerprint(connection, env)
        if fingerprint != args.expected_target_fingerprint:
            raise PostgresCheckError("target_identity")
        _preflight_schema_version(connection, args.expected_current_version)
        if args.expected_current_version == "003":
            existing_identity = read_deployment_identity(connection)
            expected_identity = DeploymentIdentityV1(
                environment=args.environment,
                label=args.expected_target_label,
                target_fingerprint=fingerprint,
                schema_version="003",
            )
            if existing_identity != expected_identity:
                raise PostgresCheckError("target_identity")

        apply_postgres_migrations(
            connection,
            specs,
            initial_policy_effective_from=args.initial_policy_effective_from,
        )
        identity = DeploymentIdentityV1(
            environment=args.environment,
            label=args.expected_target_label,
            target_fingerprint=fingerprint,
            schema_version="003",
        )
        ensure_deployment_identity(connection, identity)
        if read_deployment_identity(connection) != identity:
            raise PostgresCheckError("target_identity")
        if not verify_schema_version(connection, "003").is_current:
            raise PostgresCheckError("schema_version")

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
        policy = read_collection_policy(connection, INITIAL_COLLECTION_POLICY_ID)
        if policy is None:
            raise PostgresCheckError("policy")
        policy_count_row = connection.execute(
            "SELECT COUNT(*) FROM collection_policies_v1"
        ).fetchone()
        policy_count = policy_count_row[0]
        if policy_count != 1:
            raise PostgresCheckError("policy")
        return (
            len(tables),
            len(indexes),
            policy_count,
            policy.collection_policy_id,
            policy.configuration_hash,
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    connect: Callable[..., object] = psycopg.connect,
) -> int:
    try:
        source_env = os.environ if env is None else env
        database_url = source_env.get("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        args = _parse_args(argv)
        tables, indexes, policies, policy_id, policy_hash = _verify_database(
            database_url,
            args,
            source_env,
            connect,
        )
        print(
            "postgres_check_ok schema_version=003 "
            f"tables={tables} indexes={indexes} policies={policies} "
            f"policy_id={policy_id} policy_hash={policy_hash}"
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
