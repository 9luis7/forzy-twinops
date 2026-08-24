"""Fail-closed administrative command surface for historical data."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Protocol, TypeAlias

import psycopg

from twinops.contracts.timeline_v1_models import parse_public_utc_millis_v1
from twinops.ingestion.historical_import_v1 import prepare_historical_batch
from twinops.ingestion.history_profiles_v1 import registered_profile
from twinops.security.admin_result_writer_v1 import (
    AdminResultWriterV1,
    validate_admin_result_v1,
)
from twinops.security.local_write_guard_v1 import (
    AttestedTempDirectoryV1,
    LocalDatabasePermitV1,
    _open_attested_sqlite_connection,
    _retain_new_local_database,
    attest_local_database,
    compute_local_target_fingerprint,
    create_attested_temp_dir,
    reattest_local_database,
    reattest_local_staged_handoff,
    remove_attested_temp_dir,
)
from twinops.storage.collection_policy_v1 import (
    INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH,
    INITIAL_COLLECTION_POLICY_ID,
    ensure_initial_collection_policy,
    initial_collection_policy,
)
from twinops.storage.historical_repository_v1 import HistoricalRepositoryV1
from twinops.storage.postgres_historical_repository_v1 import (
    PostgresHistoricalRepositoryV1,
)
from twinops.storage.schema_migrations import (
    DeploymentIdentityV1,
    apply_sqlite_migrations,
    registered_migration_specs,
    verify_schema_version,
)
from twinops.storage.sqlite_historical_repository_v1 import (
    SQLiteHistoricalRepositoryV1,
)


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPECTED_SCHEMA_VERSION = "003"
_ASSET_ID = "forzy-motor-01"
_PROFILE_ID = "forzy-history-2026-05-19-v1"
_WRITE_COMMANDS = frozenset(
    {
        "migrate-local",
        "seed-collection-policy",
        "stage-history",
        "build-assessments",
        "activate-history",
    }
)
_RESULT_COMMANDS = frozenset(
    {
        "migrate-local",
        "stage-history",
        "build-assessments",
        "activate-history",
        "show-active",
        "verify-active",
    }
)
_RESULT_KEYS = {
    "migrate-local": frozenset(
        {
            "command", "mode", "environment", "targetFingerprint", "schemaVersion",
            "migrationManifestSha256", "initialPolicyId",
            "initialPolicyConfigurationHash", "appliedMigrationCount",
            "policyInserted", "writesPerformed",
        }
    ),
    "stage-history": frozenset(
        {
            "command", "mode", "environment", "targetFingerprint", "schemaVersion",
            "assetId", "batchId", "sourceSha256", "manifestSha256", "rawRowCount",
            "sampleCount", "operatingCycleCount", "inserted", "writesPerformed",
        }
    ),
    "activate-history": frozenset(
        {
            "command", "mode", "environment", "targetFingerprint", "schemaVersion",
            "assetId", "batchId", "previousActiveBatchId", "activeBatchId",
            "sourceSha256", "manifestSha256", "assessmentManifestSha256",
            "rawRowCount", "sampleCount", "operatingCycleCount", "assessmentCount",
            "activated", "writesPerformed",
        }
    ),
    "show-active": frozenset(
        {
            "command", "environment", "targetFingerprint", "schemaVersion", "assetId",
            "activeBatchId", "sourceSha256", "manifestSha256",
            "assessmentManifestSha256", "rawRowCount", "sampleCount",
            "operatingCycleCount", "assessmentCount",
        }
    ),
    "verify-active": frozenset(
        {
            "command", "environment", "targetFingerprint", "schemaVersion", "assetId",
            "activeBatchId", "sourceSha256", "manifestSha256",
            "assessmentManifestSha256", "rawRowCount", "sampleCount",
            "operatingCycleCount", "assessmentCount", "verified",
        }
    ),
}


class HistoryAdminError(RuntimeError):
    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        del message
        raise ValueError("invalid history administration arguments")


@dataclass(frozen=True)
class RepositoryTargetV1:
    environment: str
    expected_target_fingerprint: str
    expected_schema_version: str
    database_path: Path | None
    database_url: str | None
    project_id: str | None
    branch_id: str | None
    local_permit: LocalDatabasePermitV1 | None


class RepositoryFactoryProtocol(Protocol):
    def __call__(self, target: RepositoryTargetV1) -> HistoricalRepositoryV1: ...


RepositoryFactory: TypeAlias = Callable[[RepositoryTargetV1], HistoricalRepositoryV1]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be canonical sha256")
    return value


def _nullable_sha256(value: str, label: str) -> str | None:
    if value == "none":
        return None
    return _canonical_sha256(value, label)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--environment",
        required=True,
        choices=("local", "preview", "production"),
    )
    parser.add_argument("--expected-target-fingerprint", required=True)
    parser.add_argument(
        "--expected-schema-version",
        required=True,
        choices=(_EXPECTED_SCHEMA_VERSION,),
    )
    parser.add_argument("--database-path", type=Path)
    parser.add_argument("--allow-local-write", action="store_true")


def _add_mode(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")


def _add_result(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--result-json", required=True, type=Path)


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(prog="history-admin", add_help=True)
    subcommands = parser.add_subparsers(dest="command", required=True)

    migrate = subcommands.add_parser("migrate-local")
    _add_common(migrate)
    _add_mode(migrate)
    _add_result(migrate)
    migrate.add_argument("--initial-policy-effective-from", required=True)

    seed = subcommands.add_parser("seed-collection-policy")
    _add_common(seed)
    _add_mode(seed)
    seed.add_argument("--effective-from", required=True)

    stage = subcommands.add_parser("stage-history")
    _add_common(stage)
    _add_mode(stage)
    _add_result(stage)
    stage.add_argument("--input", required=True, type=Path)
    stage.add_argument("--expected-sha256", required=True)
    stage.add_argument("--profile", required=True)
    stage.add_argument("--asset-id", required=True)

    assessments = subcommands.add_parser("build-assessments")
    _add_common(assessments)
    _add_mode(assessments)
    _add_result(assessments)
    assessments.add_argument("--batch-id", required=True)

    activate = subcommands.add_parser("activate-history")
    _add_common(activate)
    _add_mode(activate)
    _add_result(activate)
    activate.add_argument("--asset-id", required=True)
    activate.add_argument("--batch-id", required=True)
    activate.add_argument("--expected-source-sha256", required=True)
    activate.add_argument("--expected-manifest-sha256", required=True)
    activate.add_argument("--expected-assessment-manifest-sha256", required=True)
    activate.add_argument("--expected-active-batch", required=True)

    show = subcommands.add_parser("show-active")
    _add_common(show)
    _add_result(show)
    show.add_argument("--asset-id", required=True)

    verify = subcommands.add_parser("verify-active")
    _add_common(verify)
    _add_result(verify)
    verify.add_argument("--asset-id", required=True)
    verify.add_argument("--expected-batch-id", required=True)
    verify.add_argument("--expected-source-sha256", required=True)
    verify.add_argument("--expected-manifest-sha256", required=True)
    verify.add_argument("--expected-assessment-manifest-sha256", required=True)
    return parser


def _parse_args(argv: Sequence[str] | None):
    args = _parser().parse_args(argv)
    _canonical_sha256(args.expected_target_fingerprint, "target fingerprint")
    if args.command in _WRITE_COMMANDS:
        args.mode = "apply" if args.apply else "dry-run"
    if args.command == "migrate-local" and args.environment != "local":
        raise ValueError("migrate-local is local-only")
    if args.environment == "local":
        if args.database_path is None or not args.database_path.is_absolute():
            raise ValueError("local commands require an absolute database path")
        if args.command in _WRITE_COMMANDS and args.mode == "apply" and not args.allow_local_write:
            raise ValueError("local apply requires explicit write authorization")
    else:
        if args.database_path is not None:
            raise ValueError("remote commands reject database paths")
        if args.allow_local_write:
            raise ValueError("remote commands reject local write authorization")
    if args.command in _RESULT_COMMANDS:
        if not args.result_json.is_absolute():
            raise ValueError("result path must be absolute")
    if args.command == "stage-history":
        if not args.input.is_absolute():
            raise ValueError("historical input path must be absolute")
        _canonical_sha256(args.expected_sha256, "source hash")
        if args.profile != _PROFILE_ID or args.asset_id != _ASSET_ID:
            raise ValueError("historical registration mismatch")
    if args.command in {"activate-history", "show-active", "verify-active"}:
        if args.asset_id != _ASSET_ID:
            raise ValueError("historical asset mismatch")
    if args.command == "activate-history":
        for name in (
            "batch_id",
            "expected_source_sha256",
            "expected_manifest_sha256",
        ):
            _canonical_sha256(getattr(args, name), name)
        args.expected_assessment_manifest_sha256 = _nullable_sha256(
            args.expected_assessment_manifest_sha256,
            "assessment manifest",
        )
        args.expected_active_batch = _nullable_sha256(
            args.expected_active_batch,
            "expected active batch",
        )
    if args.command == "verify-active":
        for name in (
            "expected_batch_id",
            "expected_source_sha256",
            "expected_manifest_sha256",
        ):
            _canonical_sha256(getattr(args, name), name)
        args.expected_assessment_manifest_sha256 = _nullable_sha256(
            args.expected_assessment_manifest_sha256,
            "assessment manifest",
        )
    if args.command == "build-assessments":
        _canonical_sha256(args.batch_id, "batch ID")
    return args


def compute_postgres_target_fingerprint(
    *,
    project_id: str,
    branch_id: str,
    database: str,
    schema: str,
) -> str:
    if not all((project_id, branch_id, database, schema)):
        raise ValueError("remote target identity is incomplete")
    payload = {
        "branchId": branch_id,
        "database": database,
        "kind": "remote-postgres",
        "projectId": project_id,
        "schema": schema,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256(canonical).hexdigest()


def repository_from_target(target: RepositoryTargetV1) -> HistoricalRepositoryV1:
    if target.environment == "local":
        if target.database_path is None:
            raise HistoryAdminError("local_target")
        def guarded_connect(path: Path) -> sqlite3.Connection:
            del path
            if target.local_permit is None:
                raise HistoryAdminError("local_target")
            return _open_attested_sqlite_connection(target.local_permit)

        return SQLiteHistoricalRepositoryV1(
            target.database_path,
            connection_factory=guarded_connect,
            before_begin=lambda connection: reattest_local_database(
                target.local_permit,
                opened_connection=connection,
            ),
        )
    if (
        target.database_url is None
        or target.project_id is None
        or target.branch_id is None
    ):
        raise HistoryAdminError("remote_target")
    try:
        with psycopg.connect(target.database_url) as connection:
            row = connection.execute(
                "SELECT current_database(), current_schema()"
            ).fetchone()
            if row is None:
                raise HistoryAdminError("target_identity")
            actual = compute_postgres_target_fingerprint(
                project_id=target.project_id,
                branch_id=target.branch_id,
                database=row[0],
                schema=row[1],
            )
    except HistoryAdminError:
        raise
    except Exception as exc:
        raise HistoryAdminError("remote_connection") from exc
    if actual != target.expected_target_fingerprint:
        raise HistoryAdminError("target_identity")
    return PostgresHistoricalRepositoryV1(target.database_url)


def _target(args, env: Mapping[str, str], *, permit=None) -> RepositoryTargetV1:
    if args.environment == "local":
        return RepositoryTargetV1(
            args.environment,
            args.expected_target_fingerprint,
            args.expected_schema_version,
            args.database_path,
            None,
            None,
            None,
            permit,
        )
    database_url = env.get("DATABASE_URL")
    project_id = env.get("TWINOPS_TARGET_PROJECT_ID")
    branch_id = env.get("TWINOPS_TARGET_BRANCH_ID")
    if not database_url or not project_id or not branch_id:
        raise HistoryAdminError("remote_target")
    return RepositoryTargetV1(
        args.environment,
        args.expected_target_fingerprint,
        args.expected_schema_version,
        None,
        database_url,
        project_id,
        branch_id,
        None,
    )


def _expected_identity(target: RepositoryTargetV1) -> DeploymentIdentityV1:
    label = (
        "local-history-admin"
        if target.environment == "local"
        else f"{target.project_id}/{target.branch_id}"
    )
    return DeploymentIdentityV1(
        environment=target.environment,
        label=label,
        target_fingerprint=target.expected_target_fingerprint,
        schema_version=target.expected_schema_version,
    )


def _preflight_repository(repository, target: RepositoryTargetV1) -> None:
    verification = repository.verify_schema(target.expected_schema_version)
    if not verification.is_current:
        raise HistoryAdminError("schema_version")
    if repository.target_identity() != _expected_identity(target):
        raise HistoryAdminError("target_identity")
    if target.local_permit is not None:
        reattest_local_database(target.local_permit)


def _policy(repository, at: datetime) -> None:
    expected = initial_collection_policy(at)
    stored = repository.collection_policy(INITIAL_COLLECTION_POLICY_ID)
    if stored is None:
        raise HistoryAdminError("policy")
    if (
        stored.collection_policy_id != INITIAL_COLLECTION_POLICY_ID
        or stored.configuration_hash != INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH
    ):
        raise HistoryAdminError("policy")
    effective = repository.effective_collection_policy(_ASSET_ID, at)
    if effective is None or effective.configuration_hash != stored.configuration_hash:
        raise HistoryAdminError("policy")


def _batch_summary(repository, batch_id: str):
    if hasattr(repository, "summary") and repository.summary.batch_id == batch_id:
        return repository.summary
    try:
        with repository._connection() as connection:
            return repository._stored_batch(connection, batch_id).summary
    except Exception as exc:
        raise HistoryAdminError("batch_identity") from exc


def _lookup_existing_batch(repository, batch_id: str):
    """Return fully validated stored evidence, distinguishing only true absence."""

    if isinstance(
        repository,
        (SQLiteHistoricalRepositoryV1, PostgresHistoricalRepositoryV1),
    ):
        placeholder = (
            "?" if isinstance(repository, SQLiteHistoricalRepositoryV1) else "%s"
        )
        try:
            with repository._connection() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM historical_import_batches_v1 "
                    f"WHERE batch_id={placeholder}",
                    (batch_id,),
                ).fetchone()
                if exists is None:
                    return None
                evidence = repository._stored_batch(connection, batch_id)
        except BaseException as exc:
            raise HistoryAdminError("batch_lookup") from exc
    else:
        lookup = getattr(repository, "_lookup_existing_batch_for_admin", None)
        if not callable(lookup):
            raise HistoryAdminError("batch_lookup")
        try:
            evidence = lookup(batch_id=batch_id)
        except BaseException as exc:
            raise HistoryAdminError("batch_lookup") from exc
        if evidence is None:
            return None
    try:
        if (
            evidence.summary.batch_id != batch_id
            or evidence.prepared.batch_id != batch_id
        ):
            raise HistoryAdminError("batch_identity")
    except HistoryAdminError:
        raise
    except BaseException as exc:
        raise HistoryAdminError("batch_lookup") from exc
    return evidence


def _recover_stored_prepared_batch(
    *,
    evidence,
    source_bytes: bytes,
    profile,
    asset_id: str,
):
    try:
        recovered = prepare_historical_batch(
            source_bytes,
            profile=profile,
            asset_id=asset_id,
            ingested_at=evidence.prepared.imported_at,
        )
    except BaseException as exc:
        raise HistoryAdminError("batch_identity") from exc
    if recovered != evidence.prepared:
        raise HistoryAdminError("batch_identity")
    expected = SimpleBatchSummary.from_prepared(recovered)
    _require_same_stage_evidence(evidence.summary, expected)
    if evidence.summary.status != "staged":
        raise HistoryAdminError("batch_identity")
    return recovered


def _migration_hashes() -> dict[str, str]:
    return {
        spec.version: spec.sqlite_sha256 for spec in registered_migration_specs()
    }


def _migration_manifest_sha256() -> str:
    canonical = json.dumps(
        _migration_hashes(), sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + sha256(canonical).hexdigest()


def _require_exact_local_migration_state(
    args,
    permit: LocalDatabasePermitV1,
    *,
    effective_from: datetime,
) -> None:
    target = _target(args, {}, permit=permit)
    repository = repository_from_target(target)
    verification = repository.verify_schema(args.expected_schema_version)
    if (
        not verification.is_current
        or verification.expected_version != args.expected_schema_version
        or verification.current_version != args.expected_schema_version
        or dict(verification.applied_migration_hashes) != _migration_hashes()
    ):
        raise HistoryAdminError("migration_reread")
    if repository.target_identity() != _expected_identity(target):
        raise HistoryAdminError("migration_reread")
    stored_policy = repository.collection_policy(INITIAL_COLLECTION_POLICY_ID)
    expected_policy = initial_collection_policy(effective_from)
    if (
        stored_policy is None
        or stored_policy.model_dump_public()
        != expected_policy.model_dump_public()
    ):
        raise HistoryAdminError("migration_reread")
    reattest_local_database(permit)


def _emit(result: dict[str, object], result_path: Path | None) -> None:
    if result_path is None:
        encoded = json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode() + b"\n"
    else:
        encoded = AdminResultWriterV1(result_path).write(result)
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _validate_result_shape(result: dict[str, object]) -> None:
    command = result.get("command")
    if command == "seed-collection-policy":
        expected = {
            "command",
            "mode",
            "environment",
            "targetFingerprint",
            "schemaVersion",
            "policyId",
            "policyConfigurationHash",
            "policyInserted",
            "writesPerformed",
        }
        valid = (
            set(result) == expected
            and result["mode"] in {"dry-run", "apply"}
            and result["environment"] in {"local", "preview", "production"}
            and result["schemaVersion"] == _EXPECTED_SCHEMA_VERSION
            and result["policyId"] == INITIAL_COLLECTION_POLICY_ID
            and isinstance(result["targetFingerprint"], str)
            and bool(_SHA256_RE.fullmatch(result["targetFingerprint"]))
            and result["policyConfigurationHash"]
            == INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH
            and type(result["policyInserted"]) is bool
            and type(result["writesPerformed"]) is int
            and result["writesPerformed"] >= 0
            and (
                result["mode"] != "dry-run"
                or result["writesPerformed"] == 0
            )
        )
        if not valid:
            raise HistoryAdminError("result_shape")
        return
    try:
        validate_admin_result_v1(result)
    except (TypeError, ValueError):
        raise HistoryAdminError("result_shape")


def _read_attested_source(path: Path) -> bytes:
    if not path.is_absolute() or ".." in path.parts:
        raise HistoryAdminError("source_path")
    try:
        before = os.lstat(path)
        if not os.path.isfile(path) or os.path.islink(path):
            raise HistoryAdminError("source_path")
        if getattr(before, "st_file_attributes", 0) & 0x400:
            raise HistoryAdminError("source_path")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            opened = os.fstat(descriptor)
            chunks = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        current = os.lstat(path)
    except HistoryAdminError:
        raise
    except OSError as exc:
        raise HistoryAdminError("source_read") from exc
    identities = {
        (before.st_dev, before.st_ino),
        (opened.st_dev, opened.st_ino),
        (after.st_dev, after.st_ino),
        (current.st_dev, current.st_ino),
    }
    if len(identities) != 1 or before.st_size != after.st_size:
        raise HistoryAdminError("source_identity")
    return b"".join(chunks)


def _migrate_local(args, clock: Callable[[], datetime]) -> dict[str, object]:
    effective_from = parse_public_utc_millis_v1(args.initial_policy_effective_from)
    path = args.database_path
    exists = path.exists() or path.is_symlink()
    if exists:
        permit = attest_local_database(
            path,
            expected_schema_version=args.expected_schema_version,
            require_existing=True,
        )
        if permit.target_fingerprint != args.expected_target_fingerprint:
            raise HistoryAdminError("target_identity")
        if args.mode == "dry-run":
            _require_exact_local_migration_state(
                args,
                permit,
                effective_from=effective_from,
            )
            inserted = False
            applied_count = 0
            writes = 0
        else:
            connection = _open_attested_sqlite_connection(permit)
            try:
                reattest_local_database(permit, opened_connection=connection)
                before = 0
                policy_before = 0
                identity_before = 0
                try:
                    before = connection.execute(
                        "SELECT COUNT(*) FROM schema_migrations_v1"
                    ).fetchone()[0]
                    policy_before = connection.execute(
                        "SELECT COUNT(*) FROM collection_policies_v1 WHERE policy_id=?",
                        (INITIAL_COLLECTION_POLICY_ID,),
                    ).fetchone()[0]
                    identity_before = connection.execute(
                        "SELECT COUNT(*) FROM deployment_identity_v1 "
                        "WHERE identity_key='primary'"
                    ).fetchone()[0]
                except sqlite3.Error:
                    pass
                apply_sqlite_migrations(
                    connection,
                    registered_migration_specs(),
                    initial_policy_effective_from=effective_from,
                    deployment_identity=_expected_identity(
                        _target(args, {}, permit=permit)
                    ),
                    before_begin=lambda opened: reattest_local_database(
                        permit,
                        opened_connection=opened,
                    ),
                )
                after = connection.execute(
                    "SELECT COUNT(*) FROM schema_migrations_v1"
                ).fetchone()[0]
                policy_count = connection.execute(
                    "SELECT COUNT(*) FROM collection_policies_v1 WHERE policy_id=?",
                    (INITIAL_COLLECTION_POLICY_ID,),
                ).fetchone()[0]
                identity_count = connection.execute(
                    "SELECT COUNT(*) FROM deployment_identity_v1 "
                    "WHERE identity_key='primary'"
                ).fetchone()[0]
                if policy_count != 1 or not verify_schema_version(
                    connection, args.expected_schema_version
                ).is_current:
                    raise HistoryAdminError("migration_reread")
                applied_count = after - before
                inserted = policy_before == 0 and policy_count == 1
                writes = (
                    applied_count
                    + int(inserted)
                    + int(identity_before == 0 and identity_count == 1)
                )
            finally:
                connection.close()
            _require_exact_local_migration_state(
                args,
                permit,
                effective_from=effective_from,
            )
    else:
        absence_permit = attest_local_database(
            path,
            expected_schema_version=args.expected_schema_version,
            require_existing=False,
        )
        fingerprint = absence_permit.target_fingerprint
        if fingerprint != args.expected_target_fingerprint:
            raise HistoryAdminError("target_identity")
        if args.mode == "dry-run":
            applied_count = 0
            inserted = False
            writes = 0
        else:
            retained = _retain_new_local_database(absence_permit)
            descriptor = None
            connection = None
            created_permit = None
            try:
                descriptor = retained.create()
                created_permit = attest_local_database(
                    path,
                    expected_schema_version=args.expected_schema_version,
                    require_existing=True,
                )
                if (
                    created_permit.root_identity != absence_permit.root_identity
                    or created_permit.parent_identity
                    != absence_permit.parent_identity
                    or created_permit.target_identity != retained.created_identity
                ):
                    raise HistoryAdminError("local_target")
                os.close(descriptor)
                descriptor = None
                connection = _open_attested_sqlite_connection(created_permit)
                apply_sqlite_migrations(
                    connection,
                    registered_migration_specs(),
                    initial_policy_effective_from=effective_from,
                    deployment_identity=_expected_identity(
                        _target(args, {}, permit=created_permit)
                    ),
                    before_begin=lambda opened: reattest_local_database(
                        created_permit,
                        opened_connection=opened,
                    ),
                )
                connection.close()
                connection = None
                _require_exact_local_migration_state(
                    args,
                    created_permit,
                    effective_from=effective_from,
                )
                applied_count = len(registered_migration_specs())
                inserted = True
                writes = applied_count + 2
            except BaseException:
                if descriptor is not None:
                    os.close(descriptor)
                    descriptor = None
                if connection is not None:
                    connection.close()
                    connection = None
                retained.cleanup_created()
                raise
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                if connection is not None:
                    connection.close()
                retained.close()
    return {
        "command": "migrate-local",
        "mode": args.mode,
        "environment": "local",
        "targetFingerprint": args.expected_target_fingerprint,
        "schemaVersion": args.expected_schema_version,
        "migrationManifestSha256": _migration_manifest_sha256(),
        "initialPolicyId": INITIAL_COLLECTION_POLICY_ID,
        "initialPolicyConfigurationHash": INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH,
        "appliedMigrationCount": applied_count,
        "policyInserted": inserted,
        "writesPerformed": writes,
    }


def _stage(args, env, clock, repository_factory):
    writer = AdminResultWriterV1(args.result_json)
    writer.preflight()
    source_bytes = _read_attested_source(args.input)
    actual_source = "sha256:" + sha256(source_bytes).hexdigest()
    if actual_source != args.expected_sha256:
        raise HistoryAdminError("source_hash")
    profile = registered_profile(args.profile)
    candidate = prepare_historical_batch(
        source_bytes,
        profile=profile,
        asset_id=args.asset_id,
        ingested_at=clock(),
    )
    if candidate.source_sha256 != args.expected_sha256:
        raise HistoryAdminError("source_identity")
    permit = None
    if args.environment == "local":
        permit = attest_local_database(
            args.database_path,
            expected_schema_version=args.expected_schema_version,
            require_existing=True,
        )
        if permit.target_fingerprint != args.expected_target_fingerprint:
            raise HistoryAdminError("target_identity")
    target = _target(args, env, permit=permit)
    repository = repository_factory(target)
    _preflight_repository(repository, target)
    existing = _lookup_existing_batch(repository, candidate.batch_id)
    prepared = (
        candidate
        if existing is None
        else _recover_stored_prepared_batch(
            evidence=existing,
            source_bytes=source_bytes,
            profile=profile,
            asset_id=args.asset_id,
        )
    )
    _policy(repository, prepared.imported_at)
    expected_summary = SimpleBatchSummary.from_prepared(prepared)
    if args.mode == "apply":
        if existing is None:
            if permit is not None:
                reattest_local_database(permit)
            stored = repository.stage_batch(prepared)
            inserted = stored.inserted
            writes = stored.writes_performed
        else:
            inserted = False
            writes = 0
        _preflight_repository(repository, target)
        _policy(repository, prepared.imported_at)
        fresh = _lookup_existing_batch(repository, prepared.batch_id)
        if fresh is None or fresh.prepared != prepared:
            raise HistoryAdminError("batch_identity")
        summary = fresh.summary
        _require_same_stage_evidence(summary, expected_summary)
        if summary.status != "staged":
            raise HistoryAdminError("batch_identity")
    else:
        summary = expected_summary if existing is None else existing.summary
        inserted = existing is None
        writes = 0
    result = {
        "command": "stage-history",
        "mode": args.mode,
        "environment": args.environment,
        "targetFingerprint": args.expected_target_fingerprint,
        "schemaVersion": args.expected_schema_version,
        "assetId": summary.asset_id,
        "batchId": summary.batch_id,
        "sourceSha256": summary.source_sha256,
        "manifestSha256": summary.manifest_sha256,
        "rawRowCount": summary.raw_row_count,
        "sampleCount": summary.sample_count,
        "operatingCycleCount": summary.operating_cycle_count,
        "inserted": inserted,
        "writesPerformed": writes,
    }
    return result, writer


@dataclass(frozen=True)
class SimpleBatchSummary:
    asset_id: str
    batch_id: str
    source_sha256: str
    manifest_sha256: str
    raw_row_count: int
    sample_count: int
    operating_cycle_count: int
    assessment_count: int = 0
    assessment_manifest_sha256: str | None = None
    status: str = "staged"

    @classmethod
    def from_prepared(cls, prepared):
        manifest = json.loads(prepared.manifest_json)
        return cls(
            prepared.asset_id,
            prepared.batch_id,
            prepared.source_sha256,
            prepared.manifest_sha256,
            len(prepared.raw_rows),
            len(prepared.samples),
            manifest["operatingCycleCount"],
        )


def _batch_evidence(summary) -> tuple[object, ...]:
    return (
        summary.asset_id,
        summary.batch_id,
        summary.source_sha256,
        summary.manifest_sha256,
        summary.raw_row_count,
        summary.sample_count,
        summary.operating_cycle_count,
        summary.assessment_count,
        summary.assessment_manifest_sha256,
    )


def _require_same_stage_evidence(actual, expected) -> None:
    if _batch_evidence(actual)[:7] != _batch_evidence(expected)[:7]:
        raise HistoryAdminError("batch_identity")


def _require_same_batch_evidence(
    actual,
    expected,
    *,
    status: str | None,
) -> None:
    if _batch_evidence(actual) != _batch_evidence(expected):
        raise HistoryAdminError("batch_identity")
    if status is not None and actual.status != status:
        raise HistoryAdminError("batch_identity")


def _repository_for_existing(args, env, repository_factory):
    permit = None
    if args.environment == "local":
        permit = attest_local_database(
            args.database_path,
            expected_schema_version=args.expected_schema_version,
            require_existing=True,
        )
        if permit.target_fingerprint != args.expected_target_fingerprint:
            raise HistoryAdminError("target_identity")
    target = _target(args, env, permit=permit)
    repository = repository_factory(target)
    _preflight_repository(repository, target)
    return repository, permit


def _activation_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise HistoryAdminError("active_batch")
        normalized = value.astimezone(timezone.utc)
        if normalized.microsecond % 1_000 != 0:
            raise HistoryAdminError("active_batch")
        return normalized
    if isinstance(value, str):
        try:
            return parse_public_utc_millis_v1(value)
        except (TypeError, ValueError) as exc:
            raise HistoryAdminError("active_batch") from exc
    raise HistoryAdminError("active_batch")


def _prove_direct_activation_predecessor(
    repository,
    *,
    asset_id: str,
    target_summary,
    expected_predecessor: str | None,
) -> None:
    """Prove the unique immediately preceding activation from fresh state."""

    if not isinstance(
        repository,
        (SQLiteHistoricalRepositoryV1, PostgresHistoricalRepositoryV1),
    ):
        proof = getattr(repository, "_activation_predecessor_for_retry", None)
        if not callable(proof):
            raise HistoryAdminError("active_batch")
        try:
            actual = proof(asset_id=asset_id, batch_id=target_summary.batch_id)
            if actual is not None:
                _canonical_sha256(actual, "activation predecessor")
        except HistoryAdminError:
            raise
        except BaseException as exc:
            raise HistoryAdminError("active_batch") from exc
        if actual != expected_predecessor:
            raise HistoryAdminError("active_batch")
        return

    placeholder = (
        "?" if isinstance(repository, SQLiteHistoricalRepositoryV1) else "%s"
    )
    try:
        with repository._connection() as connection:
            rows = connection.execute(
                "SELECT batch_id,status,activated_at "
                "FROM historical_import_batches_v1 "
                f"WHERE asset_id={placeholder} AND activated_at IS NOT NULL",
                (asset_id,),
            ).fetchall()
    except BaseException as exc:
        raise HistoryAdminError("active_batch") from exc

    activations: list[tuple[datetime, str, str]] = []
    try:
        for row in rows:
            batch_id = _canonical_sha256(row["batch_id"], "activation batch")
            status = row["status"]
            if status not in {"active", "superseded"}:
                raise HistoryAdminError("active_batch")
            activations.append(
                (_activation_timestamp(row["activated_at"]), batch_id, status)
            )
    except HistoryAdminError:
        raise
    except BaseException as exc:
        raise HistoryAdminError("active_batch") from exc

    target_rows = [
        row for row in activations if row[1] == target_summary.batch_id
    ]
    if len(target_rows) != 1 or target_rows[0][2] != "active":
        raise HistoryAdminError("active_batch")
    if target_rows[0][0] != _activation_timestamp(
        getattr(target_summary, "activated_at", None)
    ):
        raise HistoryAdminError("active_batch")
    if any(
        batch_id != target_summary.batch_id and status != "superseded"
        for _, batch_id, status in activations
    ):
        raise HistoryAdminError("active_batch")

    by_timestamp: dict[datetime, list[str]] = {}
    for activated_at, batch_id, _ in activations:
        by_timestamp.setdefault(activated_at, []).append(batch_id)
    if any(len(batch_ids) != 1 for batch_ids in by_timestamp.values()):
        raise HistoryAdminError("active_batch")

    ordered = sorted(activations, key=lambda row: row[0])
    if not ordered or ordered[-1][1] != target_summary.batch_id:
        raise HistoryAdminError("active_batch")
    actual_predecessor = None if len(ordered) == 1 else ordered[-2][1]
    if actual_predecessor != expected_predecessor:
        raise HistoryAdminError("active_batch")


def _activate(args, env, clock, repository_factory):
    writer = AdminResultWriterV1(args.result_json)
    writer.preflight()
    repository, permit = _repository_for_existing(args, env, repository_factory)
    summary = _batch_summary(repository, args.batch_id)
    if (
        summary.asset_id != args.asset_id
        or summary.source_sha256 != args.expected_source_sha256
        or summary.manifest_sha256 != args.expected_manifest_sha256
        or summary.assessment_manifest_sha256
        != args.expected_assessment_manifest_sha256
    ):
        raise HistoryAdminError("activation_identity")
    active = repository.active_batch(args.asset_id)
    current = None if active is None else active.batch_id
    retry_committed = (
        args.mode == "apply"
        and summary.status == "active"
        and current == args.batch_id
        and args.expected_active_batch != args.batch_id
    )
    if not retry_committed:
        if summary.status != "staged":
            raise HistoryAdminError("activation_identity")
        if current != args.expected_active_batch:
            raise HistoryAdminError("active_batch")
    else:
        _prove_direct_activation_predecessor(
            repository,
            asset_id=args.asset_id,
            target_summary=summary,
            expected_predecessor=args.expected_active_batch,
        )
    _policy(repository, clock())
    if args.mode == "apply":
        if retry_committed:
            previous = args.expected_active_batch
            did_activate = True
            writes = 1 + int(previous is not None)
        else:
            if permit is not None:
                reattest_local_database(permit)
            activated = repository.activate_batch(
                asset_id=args.asset_id,
                batch_id=args.batch_id,
                expected_active_batch_id=args.expected_active_batch,
            )
            if (
                activated.previous_active_batch_id
                != args.expected_active_batch
                or activated.active_batch_id != args.batch_id
                or activated.activated is not True
            ):
                raise HistoryAdminError("activation_reread")
            previous = activated.previous_active_batch_id
            did_activate = True
            writes = activated.writes_performed
        _preflight_repository(repository, _target(args, env, permit=permit))
        _policy(repository, clock())
        fresh_active = repository.active_batch(args.asset_id)
        if fresh_active is None:
            raise HistoryAdminError("activation_reread")
        _require_same_batch_evidence(
            fresh_active,
            summary,
            status="active",
        )
        summary = fresh_active
        active_id = fresh_active.batch_id
    else:
        previous = current
        active_id = args.batch_id
        did_activate = current != args.batch_id
        writes = 0
    result = {
        "command": "activate-history",
        "mode": args.mode,
        "environment": args.environment,
        "targetFingerprint": args.expected_target_fingerprint,
        "schemaVersion": args.expected_schema_version,
        "assetId": args.asset_id,
        "batchId": args.batch_id,
        "previousActiveBatchId": previous,
        "activeBatchId": active_id,
        "sourceSha256": summary.source_sha256,
        "manifestSha256": summary.manifest_sha256,
        "assessmentManifestSha256": summary.assessment_manifest_sha256,
        "rawRowCount": summary.raw_row_count,
        "sampleCount": summary.sample_count,
        "operatingCycleCount": summary.operating_cycle_count,
        "assessmentCount": summary.assessment_count,
        "activated": did_activate,
        "writesPerformed": writes,
    }
    return result, writer


def _active_result(args, env, clock, repository_factory, *, verify: bool):
    writer = AdminResultWriterV1(args.result_json)
    writer.preflight()
    repository, _ = _repository_for_existing(args, env, repository_factory)
    active = repository.active_batch(args.asset_id)
    if verify:
        if active is None:
            raise HistoryAdminError("active_batch")
        if (
            active.batch_id != args.expected_batch_id
            or active.source_sha256 != args.expected_source_sha256
            or active.manifest_sha256 != args.expected_manifest_sha256
            or active.assessment_manifest_sha256
            != args.expected_assessment_manifest_sha256
        ):
            raise HistoryAdminError("active_manifest")
        reconstructed = repository.reconstruct_source(active.batch_id)
        if "sha256:" + sha256(reconstructed).hexdigest() != active.source_sha256:
            raise HistoryAdminError("source_reconstruction")
        _policy(repository, clock())
    base = {
        "command": "verify-active" if verify else "show-active",
        "environment": args.environment,
        "targetFingerprint": args.expected_target_fingerprint,
        "schemaVersion": args.expected_schema_version,
        "assetId": args.asset_id,
        "activeBatchId": None if active is None else active.batch_id,
        "sourceSha256": None if active is None else active.source_sha256,
        "manifestSha256": None if active is None else active.manifest_sha256,
        "assessmentManifestSha256": (
            None if active is None else active.assessment_manifest_sha256
        ),
        "rawRowCount": 0 if active is None else active.raw_row_count,
        "sampleCount": 0 if active is None else active.sample_count,
        "operatingCycleCount": 0 if active is None else active.operating_cycle_count,
        "assessmentCount": 0 if active is None else active.assessment_count,
    }
    if verify:
        base["verified"] = True
    return base, writer


def _seed(args, env, repository_factory):
    effective_from = parse_public_utc_millis_v1(args.effective_from)
    repository, permit = _repository_for_existing(args, env, repository_factory)
    expected = initial_collection_policy(effective_from)
    stored = repository.collection_policy(INITIAL_COLLECTION_POLICY_ID)
    if stored is not None and stored.model_dump_public() != expected.model_dump_public():
        raise HistoryAdminError("policy")
    inserted = stored is None
    writes = 0
    if args.mode == "apply" and inserted:
        if permit is not None:
            reattest_local_database(permit)
        with repository._connection() as connection:
            if isinstance(connection, sqlite3.Connection):
                repository._begin_immediate(connection)
            result = ensure_initial_collection_policy(
                connection,
                effective_from=effective_from,
            )
            connection.commit()
        inserted = result.inserted
        writes = result.writes_performed
    return {
        "command": "seed-collection-policy",
        "mode": args.mode,
        "environment": args.environment,
        "targetFingerprint": args.expected_target_fingerprint,
        "schemaVersion": args.expected_schema_version,
        "policyId": INITIAL_COLLECTION_POLICY_ID,
        "policyConfigurationHash": INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH,
        "policyInserted": inserted,
        "writesPerformed": writes,
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    clock: Callable[[], datetime] = utc_now,
    repository_factory: RepositoryFactory = repository_from_target,
) -> int:
    try:
        args = _parse_args(argv)
        source_env = os.environ if env is None else env
        if args.command == "migrate-local":
            writer = AdminResultWriterV1(args.result_json)
            writer.preflight()
            result = _migrate_local(args, clock)
        elif args.command == "stage-history":
            result, writer = _stage(args, source_env, clock, repository_factory)
        elif args.command == "activate-history":
            result, writer = _activate(args, source_env, clock, repository_factory)
        elif args.command == "show-active":
            result, writer = _active_result(
                args, source_env, clock, repository_factory, verify=False
            )
        elif args.command == "verify-active":
            result, writer = _active_result(
                args, source_env, clock, repository_factory, verify=True
            )
        elif args.command == "seed-collection-policy":
            result = _seed(args, source_env, repository_factory)
            writer = None
        else:
            raise HistoryAdminError("command_unavailable")
        _validate_result_shape(result)
        if writer is None:
            _emit(result, None)
        else:
            encoded = writer.write(result)
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()
        return 0
    except BaseException as exc:
        stage = exc.stage if isinstance(exc, HistoryAdminError) else "validation"
        print(
            f"history_admin_failed error_type={type(exc).__name__} stage={stage}",
            file=sys.stderr,
        )
        return 1


__all__ = (
    "RepositoryFactory",
    "RepositoryTargetV1",
    "compute_postgres_target_fingerprint",
    "create_attested_temp_dir",
    "main",
    "reattest_local_staged_handoff",
    "remove_attested_temp_dir",
    "repository_from_target",
    "utc_now",
)
