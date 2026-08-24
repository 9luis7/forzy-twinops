from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest


WORKTREE_ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = WORKTREE_ROOT / "services" / "twinops"
SCRIPT_PATH = WORKTREE_ROOT / "scripts" / "history_admin.py"
HISTORY_ADMIN_PATH = SERVICE_ROOT / "src" / "twinops" / "history_admin.py"
GUARD_PATH = (
    SERVICE_ROOT / "src" / "twinops" / "security" / "local_write_guard_v1.py"
)
WRITER_PATH = (
    SERVICE_ROOT / "src" / "twinops" / "security" / "admin_result_writer_v1.py"
)
SURFACE_READY = all(
    path.is_file()
    for path in (SCRIPT_PATH, HISTORY_ADMIN_PATH, GUARD_PATH, WRITER_PATH)
)
requires_surface = pytest.mark.skipif(
    not SURFACE_READY,
    reason="history admin surface is the intentional Task A6 RED",
)


def test_history_admin_surface_exists_before_behavior_tests_run() -> None:
    assert SURFACE_READY, "RED:A6:history-admin-missing"


if SURFACE_READY:
    from twinops import history_admin as history_admin_module
    from twinops.history_admin import main
    from twinops.ingestion.historical_import_v1 import (
        _prepare_historical_batch_for_profile,
    )
    from twinops.ingestion.history_profiles_v1 import (
        HistoryProfileV1,
        registered_profile,
    )
    from twinops.security import admin_result_writer_v1 as writer_module
    from twinops.storage import sqlite_historical_repository_v1 as sqlite_repository_module
    from twinops.storage.collection_policy_v1 import (
        INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH,
        INITIAL_COLLECTION_POLICY_ID,
        initial_collection_policy,
        read_collection_policy,
    )
    from twinops.storage.schema_migrations import (
        DeploymentIdentityV1,
        SchemaVerification,
        apply_sqlite_migrations,
        ensure_deployment_identity,
        registered_migration_specs,
        verify_schema_version,
    )
    from twinops.storage.postgres_historical_repository_v1 import (
        PostgresHistoricalRepositoryV1,
    )
    from twinops.storage.sqlite_historical_repository_v1 import (
        SQLiteHistoricalRepositoryV1,
    )


SCHEMA_VERSION = "003"
ASSET_ID = "forzy-motor-01"
PROFILE_ID = "forzy-history-2026-05-19-v1"
TARGET = "sha256:" + "1" * 64
SOURCE = "sha256:" + "2" * 64
MANIFEST = "sha256:" + "3" * 64
ASSESSMENT_MANIFEST = "sha256:" + "4" * 64
BATCH = "sha256:" + "5" * 64
ACTIVE = "sha256:" + "6" * 64
MIGRATION_MANIFEST = "sha256:" + "7" * 64
NOW = datetime(2026, 5, 19, 15, 0, 0, tzinfo=timezone.utc)


def _result_path(label: str) -> Path:
    return (
        WORKTREE_ROOT
        / "tmp"
        / "twinops-admin-results"
        / f"task6-{label}-{uuid4().hex}.json"
    )


def _base(command: str, *, environment: str = "preview") -> list[str]:
    return [
        command,
        "--environment",
        environment,
        "--expected-target-fingerprint",
        TARGET,
        "--expected-schema-version",
        SCHEMA_VERSION,
    ]


def _stage_args(input_path: Path, result_path: Path, *, mode: str = "--dry-run"):
    return _base("stage-history") + [
        mode,
        "--input",
        str(input_path),
        "--expected-sha256",
        SOURCE,
        "--profile",
        PROFILE_ID,
        "--asset-id",
        ASSET_ID,
        "--result-json",
        str(result_path),
    ]


def _activate_args(result_path: Path, *, mode: str = "--dry-run"):
    return _base("activate-history") + [
        mode,
        "--asset-id",
        ASSET_ID,
        "--batch-id",
        BATCH,
        "--expected-source-sha256",
        SOURCE,
        "--expected-manifest-sha256",
        MANIFEST,
        "--expected-assessment-manifest-sha256",
        ASSESSMENT_MANIFEST,
        "--expected-active-batch",
        "none",
        "--result-json",
        str(result_path),
    ]


def _show_args(result_path: Path, command: str = "show-active"):
    args = _base(command) + [
        "--asset-id",
        ASSET_ID,
        "--result-json",
        str(result_path),
    ]
    if command == "verify-active":
        args += [
            "--expected-batch-id",
            BATCH,
            "--expected-source-sha256",
            SOURCE,
            "--expected-manifest-sha256",
            MANIFEST,
            "--expected-assessment-manifest-sha256",
            ASSESSMENT_MANIFEST,
        ]
    return args


def _seed_args(*, mode: str = "--dry-run", environment: str = "preview"):
    return _base("seed-collection-policy", environment=environment) + [
        mode,
        "--effective-from",
        "2026-05-19T15:00:00.000Z",
    ]


def _migrate_apply_args(database: Path, result: Path) -> list[str]:
    args = _base("migrate-local", environment="local") + [
        "--apply",
        "--allow-local-write",
        "--database-path",
        str(database),
        "--initial-policy-effective-from",
        "2026-05-19T00:00:00.000Z",
        "--result-json",
        str(result),
    ]
    return _set_option(args, "--expected-target-fingerprint", _local_fingerprint(database))


class RepositorySpy:
    def __init__(self):
        self.write_calls: list[str] = []
        self.read_calls: list[str] = []
        self.summary = SimpleNamespace(
            batch_id=BATCH,
            asset_id=ASSET_ID,
            status="staged",
            source_sha256=SOURCE,
            manifest_sha256=MANIFEST,
            raw_row_count=2,
            sample_count=4,
            operating_cycle_count=1,
            assessment_count=1,
            assessment_manifest_sha256=ASSESSMENT_MANIFEST,
        )
        self.active = None
        self.existing_prepared = None
        self.target_identity_value = DeploymentIdentityV1(
            environment="preview",
            label="project-test/branch-test",
            target_fingerprint=TARGET,
            schema_version=SCHEMA_VERSION,
        )

    def verify_schema(self, expected_version):
        self.read_calls.append("verify_schema")
        hashes = {
            spec.version: spec.postgres_sha256
            for spec in registered_migration_specs()
        }
        return SchemaVerification(expected_version, SCHEMA_VERSION, hashes, True)

    def target_identity(self):
        self.read_calls.append("target_identity")
        return self.target_identity_value

    def collection_policy(self, policy_id):
        self.read_calls.append("collection_policy")
        return initial_collection_policy(NOW)

    def effective_collection_policy(self, asset_id, at):
        self.read_calls.append("effective_collection_policy")
        return initial_collection_policy(NOW)

    def active_batch(self, asset_id):
        self.read_calls.append("active_batch")
        return self.active

    def reconstruct_source(self, batch_id):
        self.read_calls.append("reconstruct_source")
        return b"synthetic registered bytes\r\n"

    def stage_batch(self, prepared):
        self.write_calls.append("stage_batch")
        self.existing_prepared = prepared
        self.summary = SimpleNamespace(
            **{
                **vars(self.summary),
                "batch_id": prepared.batch_id,
                "source_sha256": prepared.source_sha256,
                "manifest_sha256": prepared.manifest_sha256,
                "raw_row_count": len(prepared.raw_rows),
                "sample_count": len(prepared.samples),
            }
        )
        return SimpleNamespace(batch=self.summary, inserted=True, writes_performed=7)

    def _lookup_existing_batch_for_admin(self, *, batch_id):
        self.read_calls.append("lookup_existing_batch")
        if self.existing_prepared is None or self.summary.batch_id != batch_id:
            return None
        return SimpleNamespace(
            prepared=self.existing_prepared,
            summary=self.summary,
        )

    def activate_batch(self, *, asset_id, batch_id, expected_active_batch_id):
        self.write_calls.append("activate_batch")
        self.active = SimpleNamespace(**{**vars(self.summary), "status": "active"})
        return SimpleNamespace(
            asset_id=asset_id,
            batch_id=batch_id,
            previous_active_batch_id=expected_active_batch_id,
            active_batch_id=batch_id,
            activated=True,
            assessment_count=1,
            assessment_manifest_sha256=ASSESSMENT_MANIFEST,
            writes_performed=1,
        )


class RepositoryFactorySpy:
    def __init__(self, repository=None):
        self.repository = repository or RepositorySpy()
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.repository


def _prepared_batch(source_bytes=b"synthetic registered bytes\r\n"):
    source_sha256 = "sha256:" + sha256(source_bytes).hexdigest()
    manifest_json = json.dumps(
        {
            "operatingCycleCount": 1,
            "rawRowCount": 2,
            "sampleCount": 4,
            "sourceSha256": source_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return SimpleNamespace(
        batch_id=BATCH,
        asset_id=ASSET_ID,
        source_bytes=source_bytes,
        source_sha256=source_sha256,
        manifest_json=manifest_json,
        manifest_sha256="sha256:" + sha256(manifest_json.encode()).hexdigest(),
        imported_at=NOW,
        raw_rows=(SimpleNamespace(), SimpleNamespace()),
        samples=tuple(SimpleNamespace() for _ in range(4)),
    )


def _synthetic_admin_material(
    variant: int,
    *,
    ingested_at: datetime = NOW,
):
    rows = {
        0: (
            "2026-05-19T11:46:10.921;AQID;BAUG;0.04;0;27;0.05;0.01;34",
            "2026-05-19T11:46:20.921;CQoL;DA0O;0.06;0.02;28;0.07;0.03;35",
        ),
        1: (
            "2026-05-19T11:46:10.921;AQID;BAUG;0.14;0;27;0.15;0.01;34",
            "2026-05-19T11:46:20.921;CQoL;DA0O;0.16;0.02;28;0.17;0.03;35",
        ),
        2: (
            "2026-05-19T11:46:10.921;AQID;BAUG;0.24;0;27;0.25;0.01;34",
            "2026-05-19T11:46:20.921;CQoL;DA0O;0.26;0.02;28;0.27;0.03;35",
        ),
    }[variant]
    header = registered_profile(PROFILE_ID).header_records
    source_bytes = b"".join(header) + b"".join(
        row.encode("utf-8") + b"\r\n" for row in rows
    )
    profile = HistoryProfileV1(
        profile_id=f"task6-round2-{variant}",
        source_size_bytes=len(source_bytes),
        source_sha256="sha256:" + sha256(source_bytes).hexdigest(),
        header_records=header,
        encoding="utf-8",
        delimiter=";",
        newline="CRLF",
        final_crlf_required=True,
        data_record_count=2,
        sample_count=4,
        operating_cycle_count=1,
        timezone_name="America/Sao_Paulo",
        parser_version="forzy-history-parser-v1",
        contract_version="1.0",
        gap_seconds=15.0,
    )
    prepared = _prepare_historical_batch_for_profile(
        source_bytes,
        profile=profile,
        asset_id=ASSET_ID,
        ingested_at=ingested_at,
    )
    return source_bytes, profile, prepared


def _synthetic_admin_batch(variant: int, *, ingested_at: datetime = NOW):
    return _synthetic_admin_material(variant, ingested_at=ingested_at)[2]


def _set_option(args: list[str], option: str, value: str) -> list[str]:
    args[args.index(option) + 1] = value
    return args


def _local_fingerprint(path: Path) -> str:
    return history_admin_module.compute_local_target_fingerprint(
        path,
        expected_schema_version=SCHEMA_VERSION,
        migration_hashes={
            spec.version: spec.sqlite_sha256
            for spec in registered_migration_specs()
        },
    )


def _remote_env(**updates) -> dict[str, str]:
    env = {
        "DATABASE_URL": "postgresql://secret-user:secret-pass@secret-host/db",
        "TWINOPS_TARGET_PROJECT_ID": "project-test",
        "TWINOPS_TARGET_BRANCH_ID": "branch-test",
    }
    env.update(updates)
    return env


def _invoke(args, capsys, *, env=None, repository=None):
    factory = RepositoryFactorySpy(repository)
    code = main(
        args,
        env=_remote_env() if env is None else env,
        clock=lambda: NOW,
        repository_factory=factory,
    )
    captured = capsys.readouterr()
    return code, captured, factory


def _assert_no_sensitive_output(captured, *sensitive: object) -> None:
    combined = captured.out + captured.err
    for value in sensitive:
        assert str(value) not in combined
    assert "secret-user" not in combined
    assert "secret-host" not in combined
    assert "secret-pass" not in combined
    assert "synthetic registered bytes" not in combined


@requires_surface
class TestCliGrammar:
    def test_checked_in_launcher_exits_safely_without_arguments(self):
        launcher_env = os.environ.copy()
        launcher_env.pop("DATABASE_URL", None)
        launcher_env["PYTHONPATH"] = (
            f"{SERVICE_ROOT / 'src'}{os.pathsep}{WORKTREE_ROOT}"
        )
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=WORKTREE_ROOT,
            env=launcher_env,
            capture_output=True,
            text=True,
        )
        combined = completed.stdout + completed.stderr
        assert completed.returncode == 1
        assert "history_admin_failed" in completed.stderr
        assert "Traceback" not in combined
        assert str(WORKTREE_ROOT) not in combined

    @pytest.mark.parametrize(
        "command",
        [
            "migrate-local",
            "seed-collection-policy",
            "stage-history",
            "build-assessments",
            "activate-history",
            "show-active",
            "verify-active",
        ],
    )
    @pytest.mark.parametrize(
        "missing_option",
        ["--environment", "--expected-target-fingerprint", "--expected-schema-version"],
    )
    def test_every_command_requires_environment_fingerprint_and_schema(
        self,
        command,
        missing_option,
        capsys,
    ):
        args = _base(command)
        index = args.index(missing_option)
        del args[index : index + 2]
        code, captured, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.calls == []
        assert factory.repository.write_calls == []
        _assert_no_sensitive_output(captured)

    @pytest.mark.parametrize("environment", ["dev", "staging", "LOCAL", ""])
    def test_environment_is_closed_to_exact_values(self, environment, capsys):
        args = _base("show-active", environment=environment)
        code, _, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.calls == []

    @pytest.mark.parametrize("fingerprint", ["", "1" * 64, "sha256:ABC", "sha256:" + "g" * 64])
    def test_target_fingerprint_requires_canonical_sha256(self, fingerprint, capsys):
        args = _base("show-active")
        args[args.index("--expected-target-fingerprint") + 1] = fingerprint
        code, _, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.calls == []

    @pytest.mark.parametrize("schema", ["3", "03", "002", "004", "three"])
    def test_schema_version_is_exactly_003(self, schema, capsys):
        args = _base("show-active")
        args[args.index("--expected-schema-version") + 1] = schema
        code, _, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.calls == []

    @pytest.mark.parametrize(
        "command",
        [
            "migrate-local",
            "seed-collection-policy",
            "stage-history",
            "build-assessments",
            "activate-history",
        ],
    )
    @pytest.mark.parametrize("mode_flags", [[], ["--dry-run", "--apply"]])
    def test_write_commands_require_exactly_one_mode(self, command, mode_flags, capsys):
        args = _base(command) + mode_flags
        code, _, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.calls == []

    @pytest.mark.parametrize("command", ["show-active", "verify-active"])
    @pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
    def test_read_only_commands_reject_both_mode_flags(self, command, mode, capsys):
        code, _, factory = _invoke(_base(command) + [mode], capsys)
        assert code == 1
        assert factory.calls == []

    @pytest.mark.parametrize(
        "command",
        [
            "migrate-local",
            "stage-history",
            "build-assessments",
            "activate-history",
            "show-active",
            "verify-active",
        ],
    )
    def test_frozen_commands_require_result_json(self, command, capsys):
        args = _base(command) + ([] if command.startswith(("show", "verify")) else ["--dry-run"])
        code, _, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.repository.write_calls == []

    def test_unknown_command_and_unknown_options_fail_closed(self, capsys):
        for args in (["unknown"], _base("show-active") + ["--free-form", "value"]):
            code, _, factory = _invoke(args, capsys)
            assert code == 1
            assert factory.calls == []


@requires_surface
class TestEnvironmentAndLocalWriteGates:
    @pytest.mark.parametrize("environment", ["preview", "production"])
    def test_migrate_local_rejects_remote_environments(self, environment, capsys):
        args = _base("migrate-local", environment=environment) + [
            "--dry-run",
            "--database-path",
            str(WORKTREE_ROOT / "tmp" / "history.db"),
            "--initial-policy-effective-from",
            "2026-05-19T00:00:00.000Z",
            "--result-json",
            str(_result_path("migration")),
        ]
        code, _, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.calls == []

    @pytest.mark.parametrize("command", ["stage-history", "activate-history", "show-active", "verify-active"])
    def test_local_commands_require_absolute_guarded_database_path(self, command, capsys):
        result = _result_path("local-path")
        args = _base(command, environment="local")
        if command in {"stage-history", "activate-history"}:
            args.append("--dry-run")
        args += ["--database-path", "relative.db", "--result-json", str(result)]
        code, _, factory = _invoke(args, capsys, env={})
        assert code == 1
        assert factory.calls == []
        assert not result.exists()

    @pytest.mark.parametrize("command", ["stage-history", "activate-history"])
    def test_local_apply_requires_explicit_allow_local_write(self, command, capsys):
        result = _result_path("local-apply")
        args = _base(command, environment="local") + [
            "--apply",
            "--database-path",
            str(WORKTREE_ROOT / "tmp" / "history.db"),
            "--result-json",
            str(result),
        ]
        code, _, factory = _invoke(args, capsys, env={})
        assert code == 1
        assert factory.repository.write_calls == []
        assert not result.exists()

    @pytest.mark.parametrize("environment", ["preview", "production"])
    def test_remote_commands_reject_database_path(self, environment, capsys):
        result = _result_path("remote-path")
        args = _show_args(result) + [
            "--database-path",
            str(WORKTREE_ROOT / "tmp" / "history.db"),
        ]
        args[args.index("preview")] = environment
        code, _, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.calls == []
        assert not result.exists()

    @pytest.mark.parametrize(
        "missing",
        ["DATABASE_URL", "TWINOPS_TARGET_PROJECT_ID", "TWINOPS_TARGET_BRANCH_ID"],
    )
    def test_remote_target_requires_dsn_and_explicit_project_branch_identity(
        self,
        missing,
        capsys,
    ):
        result = _result_path("remote-env")
        env = _remote_env()
        del env[missing]
        code, captured, factory = _invoke(_show_args(result), capsys, env=env)
        assert code == 1
        assert factory.repository.write_calls == []
        assert not result.exists()
        _assert_no_sensitive_output(captured)

    def test_project_and_branch_are_not_inferred_from_dsn(self, capsys):
        result = _result_path("dsn-identity")
        env = {"DATABASE_URL": "postgresql://project:branch@secret-host/db"}
        code, captured, factory = _invoke(_show_args(result), capsys, env=env)
        assert code == 1
        assert factory.repository.write_calls == []
        assert not result.exists()
        _assert_no_sensitive_output(captured)


@requires_surface
class TestCommandSpecificPreflightAndNoWrite:
    @pytest.mark.parametrize(
        "mutation",
        [
            ("--profile", "unknown-profile"),
            ("--asset-id", "other-motor"),
            ("--expected-sha256", "sha256:" + "9" * 64),
        ],
    )
    def test_stage_rejects_profile_asset_and_file_hash_before_write(
        self,
        tmp_path,
        capsys,
        mutation,
    ):
        source = tmp_path / "synthetic.csv"
        source.write_bytes(b"payload-that-must-not-leak")
        result = _result_path("stage-mismatch")
        args = _stage_args(source.resolve(), result)
        option, value = mutation
        args[args.index(option) + 1] = value
        repository = RepositorySpy()
        code, captured, _ = _invoke(args, capsys, repository=repository)
        assert code == 1
        assert repository.write_calls == []
        assert not result.exists()
        _assert_no_sensitive_output(captured, source.resolve(), b"payload-that-must-not-leak")

    @pytest.mark.parametrize(
        "option,value",
        [
            ("--batch-id", "sha256:" + "8" * 64),
            ("--expected-source-sha256", "sha256:" + "8" * 64),
            ("--expected-manifest-sha256", "sha256:" + "8" * 64),
            ("--expected-assessment-manifest-sha256", "sha256:" + "8" * 64),
            ("--expected-active-batch", ACTIVE),
        ],
    )
    def test_activation_rejects_every_identity_or_hash_mismatch_before_write(
        self,
        capsys,
        option,
        value,
    ):
        result = _result_path("activation-mismatch")
        args = _activate_args(result)
        args[args.index(option) + 1] = value
        repository = RepositorySpy()
        code, captured, _ = _invoke(args, capsys, repository=repository)
        assert code == 1
        assert repository.write_calls == []
        assert not result.exists()
        _assert_no_sensitive_output(captured)

    @pytest.mark.parametrize("nullable", ["NONE", "null", "", "None"])
    def test_nullable_expected_values_accept_only_literal_lowercase_none(
        self,
        capsys,
        nullable,
    ):
        result = _result_path("nullable")
        args = _activate_args(result)
        args[args.index("--expected-active-batch") + 1] = nullable
        code, _, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.repository.write_calls == []
        assert not result.exists()

    def test_deployment_identity_mismatch_causes_zero_writes_and_no_result(self, capsys):
        result = _result_path("identity")
        repository = RepositorySpy()
        repository.target_identity_value = DeploymentIdentityV1(
            environment="production",
            label="wrong/wrong",
            target_fingerprint="sha256:" + "9" * 64,
            schema_version="002",
        )
        code, captured, _ = _invoke(_show_args(result), capsys, repository=repository)
        assert code == 1
        assert repository.write_calls == []
        assert not result.exists()
        _assert_no_sensitive_output(captured)

    @pytest.mark.parametrize("mismatch", ["hash", "validity"])
    def test_policy_hash_or_validity_mismatch_causes_zero_writes_and_no_result(
        self,
        tmp_path,
        capsys,
        monkeypatch,
        mismatch,
    ):
        source = tmp_path / "synthetic.csv"
        source_bytes = b"synthetic registered bytes\r\n"
        source.write_bytes(source_bytes)
        result = _result_path("policy")
        repository = RepositorySpy()
        if mismatch == "hash":
            repository.collection_policy = lambda policy_id: SimpleNamespace(
                collection_policy_id=INITIAL_COLLECTION_POLICY_ID,
                configuration_hash="sha256:" + "9" * 64,
                effective_from=NOW,
                effective_to=None,
            )
        else:
            repository.effective_collection_policy = lambda asset_id, at: None
        prepared = _prepared_batch(source_bytes)
        monkeypatch.setattr(history_admin_module, "prepare_historical_batch", lambda *a, **k: prepared)
        args = _set_option(
            _stage_args(source.resolve(), result),
            "--expected-sha256",
            prepared.source_sha256,
        )
        code, captured, _ = _invoke(
            args,
            capsys,
            repository=repository,
        )
        assert code == 1
        assert repository.write_calls == []
        assert not result.exists()
        _assert_no_sensitive_output(captured, source.resolve())

    def test_verify_post_activation_manifest_mismatch_writes_no_success_result(self, capsys):
        result = _result_path("verify-mismatch")
        repository = RepositorySpy()
        repository.active = SimpleNamespace(
            **{**vars(repository.summary), "status": "active", "manifest_sha256": ACTIVE}
        )
        code, captured, _ = _invoke(
            _show_args(result, "verify-active"),
            capsys,
            repository=repository,
        )
        assert code == 1
        assert repository.write_calls == []
        assert not result.exists()
        _assert_no_sensitive_output(captured)

    @pytest.mark.parametrize(
        "bad_path",
        [
            WORKTREE_ROOT / "outside.json",
            WORKTREE_ROOT / "tmp" / "twinops-admin-results" / "nested" / "x.json",
            WORKTREE_ROOT / "tmp" / "twinops-admin-results" / "wrong.txt",
        ],
    )
    def test_invalid_result_path_fails_before_database_write(self, bad_path, capsys):
        repository = RepositorySpy()
        code, _, _ = _invoke(_show_args(bad_path), capsys, repository=repository)
        assert code == 1
        assert repository.write_calls == []
        assert not bad_path.is_file()


@requires_surface
class TestSanitizedCanonicalResults:
    def _read_result(self, path: Path, captured):
        try:
            raw = path.read_bytes()
            assert captured.out.encode("utf-8") == raw
            assert captured.err == ""
            assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
            assert raw == json.dumps(
                json.loads(raw),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            return json.loads(raw)
        finally:
            path.unlink(missing_ok=True)

    def test_stage_result_has_exact_flat_shape_and_no_sensitive_values(
        self,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        source = tmp_path / "history.csv"
        source_bytes = b"synthetic registered bytes\r\n"
        source.write_bytes(source_bytes)
        result = _result_path("stage-shape")
        prepared = _prepared_batch(source_bytes)
        monkeypatch.setattr(history_admin_module, "prepare_historical_batch", lambda *a, **k: prepared)
        args = _set_option(
            _stage_args(source.resolve(), result),
            "--expected-sha256",
            prepared.source_sha256,
        )
        code, captured, _ = _invoke(args, capsys)
        assert code == 0
        payload = self._read_result(result, captured)
        assert set(payload) == {
            "command", "mode", "environment", "targetFingerprint", "schemaVersion",
            "assetId", "batchId", "sourceSha256", "manifestSha256", "rawRowCount",
            "sampleCount", "operatingCycleCount", "inserted", "writesPerformed",
        }
        assert payload["writesPerformed"] == 0
        _assert_no_sensitive_output(captured, source.resolve())

    def test_activate_result_has_exact_flat_shape(self, capsys):
        result = _result_path("activate-shape")
        repository = RepositorySpy()
        code, captured, _ = _invoke(_activate_args(result), capsys, repository=repository)
        assert code == 0
        payload = self._read_result(result, captured)
        assert set(payload) == {
            "command", "mode", "environment", "targetFingerprint", "schemaVersion",
            "assetId", "batchId", "previousActiveBatchId", "activeBatchId",
            "sourceSha256", "manifestSha256", "assessmentManifestSha256",
            "rawRowCount", "sampleCount", "operatingCycleCount", "assessmentCount",
            "activated", "writesPerformed",
        }
        assert payload["writesPerformed"] == 0

    def test_show_active_no_batch_uses_null_hashes_and_zero_counts(self, capsys):
        result = _result_path("show-empty")
        code, captured, _ = _invoke(_show_args(result), capsys)
        assert code == 0
        payload = self._read_result(result, captured)
        assert set(payload) == {
            "command", "environment", "targetFingerprint", "schemaVersion", "assetId",
            "activeBatchId", "sourceSha256", "manifestSha256",
            "assessmentManifestSha256", "rawRowCount", "sampleCount",
            "operatingCycleCount", "assessmentCount",
        }
        assert payload["activeBatchId"] is None
        assert payload["sourceSha256"] is None
        assert payload["manifestSha256"] is None
        assert payload["assessmentManifestSha256"] is None
        assert payload["rawRowCount"] == payload["sampleCount"] == 0
        assert payload["operatingCycleCount"] == payload["assessmentCount"] == 0

    def test_verify_active_success_adds_only_verified_true(self, capsys):
        result = _result_path("verify-shape")
        repository = RepositorySpy()
        reconstructed = b"verified reconstructed source"
        source_digest = "sha256:" + sha256(reconstructed).hexdigest()
        repository.reconstruct_source = lambda batch_id: reconstructed
        repository.summary = SimpleNamespace(
            **{**vars(repository.summary), "source_sha256": source_digest}
        )
        repository.active = SimpleNamespace(**{**vars(repository.summary), "status": "active"})
        args = _show_args(result, "verify-active")
        _set_option(args, "--expected-source-sha256", source_digest)
        code, captured, _ = _invoke(
            args,
            capsys,
            repository=repository,
        )
        assert code == 0
        payload = self._read_result(result, captured)
        assert payload["command"] == "verify-active"
        assert payload["verified"] is True
        assert "mode" not in payload
        assert "writesPerformed" not in payload

    def test_error_output_and_result_never_leak_dsn_paths_or_payloads(
        self,
        tmp_path,
        capsys,
    ):
        source = tmp_path / "sensitive-source.csv"
        database = tmp_path / "sensitive-user-database.db"
        source.write_bytes(b"CSV ROW PAYLOAD SECRET")
        result = _result_path("sanitize")
        args = _stage_args(source.resolve(), result)
        args += ["--database-path", str(database.resolve())]
        code, captured, _ = _invoke(args, capsys)
        assert code == 1
        assert not result.exists()
        _assert_no_sensitive_output(
            captured,
            source.resolve(),
            database.resolve(),
            "CSV ROW PAYLOAD SECRET",
        )


@requires_surface
class TestMigrateLocalAndCommittedResultFailure:
    def test_migrate_local_fresh_dry_run_creates_neither_database_nor_writes(
        self,
        capsys,
        monkeypatch,
    ):
        attested = history_admin_module.create_attested_temp_dir()
        database = Path(attested.path) / "history.db"
        result = _result_path("migrate-dry")
        args = _base("migrate-local", environment="local") + [
            "--dry-run",
            "--database-path", str(database),
            "--initial-policy-effective-from", "2026-05-19T00:00:00.000Z",
            "--result-json", str(result),
        ]
        _set_option(args, "--expected-target-fingerprint", _local_fingerprint(database))
        try:
            code, captured, _ = _invoke(args, capsys, env={})
            assert code == 0
            assert not database.exists()
            payload = json.loads(result.read_bytes())
            assert payload["writesPerformed"] == 0
            assert payload["appliedMigrationCount"] == 0
            _assert_no_sensitive_output(captured, database)
        finally:
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)

    def test_migrate_local_apply_and_second_run_are_exact_and_idempotent(self, capsys):
        attested = history_admin_module.create_attested_temp_dir()
        database = Path(attested.path) / "history.db"
        first_result = _result_path("migrate-first")
        second_result = _result_path("migrate-second")
        base = _base("migrate-local", environment="local") + [
            "--apply", "--allow-local-write",
            "--database-path", str(database),
            "--initial-policy-effective-from", "2026-05-19T00:00:00.000Z",
        ]
        _set_option(base, "--expected-target-fingerprint", _local_fingerprint(database))
        try:
            first, first_capture, _ = _invoke(base + ["--result-json", str(first_result)], capsys, env={})
            second, second_capture, _ = _invoke(base + ["--result-json", str(second_result)], capsys, env={})
            assert first == second == 0
            assert database.is_file()
            with closing(sqlite3.connect(database)) as connection:
                assert verify_schema_version(connection, SCHEMA_VERSION).is_current
                stored_policy = read_collection_policy(
                    connection,
                    INITIAL_COLLECTION_POLICY_ID,
                )
                assert stored_policy is not None
                assert (
                    stored_policy.configuration_hash
                    == INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH
                )
            one = json.loads(first_result.read_bytes())
            two = json.loads(second_result.read_bytes())
            exact = {
                "command", "mode", "environment", "targetFingerprint", "schemaVersion",
                "migrationManifestSha256", "initialPolicyId",
                "initialPolicyConfigurationHash", "appliedMigrationCount",
                "policyInserted", "writesPerformed",
            }
            assert set(one) == set(two) == exact
            assert two["appliedMigrationCount"] == 0
            assert two["policyInserted"] is False
            assert two["writesPerformed"] == 0
            assert two["initialPolicyId"] == INITIAL_COLLECTION_POLICY_ID
            assert two["initialPolicyConfigurationHash"] == INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH
            _assert_no_sensitive_output(first_capture, database)
            _assert_no_sensitive_output(second_capture, database)
        finally:
            first_result.unlink(missing_ok=True)
            second_result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)

    def test_result_write_failure_after_commit_never_compensates_or_retries_transaction(
        self,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        source = tmp_path / "history.csv"
        source_bytes = b"synthetic registered bytes\r\n"
        source.write_bytes(source_bytes)
        result = _result_path("write-failure")
        repository = RepositorySpy()
        prepared = _prepared_batch(source_bytes)
        monkeypatch.setattr(history_admin_module, "prepare_historical_batch", lambda *a, **k: prepared)
        monkeypatch.setattr(
            history_admin_module.AdminResultWriterV1,
            "write",
            lambda self, value: (_ for _ in ()).throw(OSError("secret-host/result denied")),
        )
        code, captured, _ = _invoke(
            _set_option(
                _stage_args(source.resolve(), result, mode="--apply"),
                "--expected-sha256",
                prepared.source_sha256,
            ),
            capsys,
            repository=repository,
        )
        assert code == 1
        assert repository.write_calls == ["stage_batch"]
        assert not result.exists()
        _assert_no_sensitive_output(captured, source.resolve(), "secret-host")

    def test_retry_after_result_failure_rereads_idempotent_committed_state(
        self,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        source = tmp_path / "history.csv"
        source_bytes = b"synthetic registered bytes\r\n"
        source.write_bytes(source_bytes)
        result = _result_path("retry")
        repository = RepositorySpy()
        prepared = _prepared_batch(source_bytes)
        monkeypatch.setattr(history_admin_module, "prepare_historical_batch", lambda *a, **k: prepared)
        real_writer = history_admin_module.AdminResultWriterV1
        calls = 0

        class FailOnceWriter(real_writer):
            def write(self, value):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("result unavailable")
                return super().write(value)

        monkeypatch.setattr(history_admin_module, "AdminResultWriterV1", FailOnceWriter)
        args = _stage_args(source.resolve(), result, mode="--apply")
        _set_option(args, "--expected-sha256", prepared.source_sha256)
        first, _, _ = _invoke(args, capsys, repository=repository)
        second, captured, _ = _invoke(args, capsys, repository=repository)
        assert first == 1 and second == 0
        assert repository.write_calls == ["stage_batch"]
        payload = json.loads(result.read_bytes())
        assert payload["batchId"] == BATCH
        assert payload["manifestSha256"] == prepared.manifest_sha256
        _assert_no_sensitive_output(captured, source.resolve())
        result.unlink(missing_ok=True)


@requires_surface
class TestFreshSQLiteCreationRaceHardening:
    def test_restored_parent_after_redirected_create_leaves_no_created_inode(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches cleanup looking only at the restored target pathname."""

        attested = history_admin_module.create_attested_temp_dir()
        root = Path(attested.path)
        parent = root / "database-restored"
        parent.mkdir()
        original_parent = root / "database-restored-original"
        redirected_parent = root / "database-restored-redirected"
        database = parent / "history.db"
        result = _result_path("fresh-parent-restored-race")
        real_open = history_admin_module.os.open
        real_attest = history_admin_module.attest_local_database
        attempted = False
        restored = False

        def redirect_create_then_restore(path, flags, *args, **kwargs):
            nonlocal attempted, restored
            if Path(path).name == database.name and flags & os.O_CREAT and not attempted:
                attempted = True
                parent.rename(original_parent)
                parent.mkdir()
                descriptor = real_open(path, flags, *args, **kwargs)
                parent.rename(redirected_parent)
                original_parent.rename(parent)
                restored = True
                return descriptor
            return real_open(path, flags, *args, **kwargs)

        def fail_created_target_attestation(path, *args, **kwargs):
            if kwargs.get("require_existing") is True and restored:
                raise RuntimeError("injected post-create attestation failure")
            return real_attest(path, *args, **kwargs)

        monkeypatch.setattr(history_admin_module.os, "open", redirect_create_then_restore)
        monkeypatch.setattr(
            history_admin_module,
            "attest_local_database",
            fail_created_target_attestation,
        )
        try:
            code, captured, _ = _invoke(
                _migrate_apply_args(database, result),
                capsys,
                env={},
            )
            assert attempted is True
            assert code == 1
            assert not database.exists()
            assert not (redirected_parent / database.name).exists()
            assert not result.exists()
            _assert_no_sensitive_output(captured, database, redirected_parent)
        finally:
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)

    @pytest.mark.skipif(os.name != "nt", reason="real junction race is Windows-only")
    def test_restored_parent_after_junction_redirect_leaves_no_external_inode(
        self,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        """Catches cleanup losing a created inode after a junction ABA restore."""

        attested = history_admin_module.create_attested_temp_dir()
        root = Path(attested.path)
        parent = root / "database-junction-restored"
        parent.mkdir()
        original_parent = root / "database-junction-original"
        external = tmp_path / "junction-restored-external"
        external.mkdir()
        sentinel = external / "keep.bin"
        sentinel.write_bytes(b"external-preexisting")
        proof = root / "junction-round2-privilege-proof"
        proof_result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(proof), str(external)],
            capture_output=True,
            text=True,
        )
        if proof_result.returncode != 0:
            history_admin_module.remove_attested_temp_dir(attested)
            pytest.skip("junction creation privilege is unavailable")
        proof.rmdir()
        database = parent / "history.db"
        result = _result_path("fresh-junction-restored-race")
        real_open = history_admin_module.os.open
        attempted = False

        def redirect_to_junction_then_restore(path, flags, *args, **kwargs):
            nonlocal attempted
            if Path(path).name == database.name and flags & os.O_CREAT and not attempted:
                attempted = True
                parent.rename(original_parent)
                completed = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(parent), str(external)],
                    capture_output=True,
                    text=True,
                )
                assert completed.returncode == 0
                descriptor = real_open(path, flags, *args, **kwargs)
                parent.rmdir()
                original_parent.rename(parent)
                return descriptor
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(
            history_admin_module.os,
            "open",
            redirect_to_junction_then_restore,
        )
        try:
            code, captured, _ = _invoke(
                _migrate_apply_args(database, result),
                capsys,
                env={},
            )
            assert attempted is True
            assert code == 1
            assert not database.exists()
            assert not (external / database.name).exists()
            assert sentinel.read_bytes() == b"external-preexisting"
            assert not result.exists()
            _assert_no_sensitive_output(captured, database, external)
        finally:
            result.unlink(missing_ok=True)
            if parent.is_symlink():
                parent.rmdir()
            if original_parent.exists() and not parent.exists():
                original_parent.rename(parent)
            history_admin_module.remove_attested_temp_dir(attested)
    def test_regular_parent_replacement_before_create_leaves_no_database_or_result(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches fresh creation accepting a different regular parent identity."""

        attested = history_admin_module.create_attested_temp_dir()
        root = Path(attested.path)
        parent = root / "database"
        parent.mkdir()
        moved_parent = root / "database-before-race"
        database = parent / "history.db"
        result = _result_path("fresh-parent-race")
        real_open = history_admin_module.os.open
        attempted = False

        def replace_parent_then_open(path, flags, *args, **kwargs):
            nonlocal attempted
            if Path(path).name == database.name and flags & os.O_CREAT and not attempted:
                attempted = True
                parent.rename(moved_parent)
                parent.mkdir()
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(history_admin_module.os, "open", replace_parent_then_open)
        try:
            code, captured, _ = _invoke(
                _migrate_apply_args(database, result),
                capsys,
                env={},
            )
            assert attempted is True
            assert code == 1
            assert not database.exists()
            assert not (moved_parent / database.name).exists()
            assert not result.exists()
            _assert_no_sensitive_output(captured, database)
        finally:
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)

    @pytest.mark.skipif(os.name != "nt", reason="real junction race is Windows-only")
    def test_junction_parent_replacement_before_create_leaves_no_external_residue(
        self,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        """Catches fresh creation following a raced junction into an external root."""

        attested = history_admin_module.create_attested_temp_dir()
        root = Path(attested.path)
        parent = root / "database"
        parent.mkdir()
        moved_parent = root / "database-before-junction-race"
        external = tmp_path / "external-junction-target"
        external.mkdir()
        proof = root / "junction-privilege-proof"
        proof_result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(proof), str(external)],
            capture_output=True,
            text=True,
        )
        if proof_result.returncode != 0:
            history_admin_module.remove_attested_temp_dir(attested)
            pytest.skip("junction creation privilege is unavailable")
        proof.rmdir()
        database = parent / "history.db"
        result = _result_path("fresh-junction-race")
        real_open = history_admin_module.os.open
        attempted = False

        def replace_parent_with_junction_then_open(path, flags, *args, **kwargs):
            nonlocal attempted
            if Path(path).name == database.name and flags & os.O_CREAT and not attempted:
                attempted = True
                parent.rename(moved_parent)
                completed = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(parent), str(external)],
                    capture_output=True,
                    text=True,
                )
                assert completed.returncode == 0
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(
            history_admin_module.os,
            "open",
            replace_parent_with_junction_then_open,
        )
        try:
            code, captured, _ = _invoke(
                _migrate_apply_args(database, result),
                capsys,
                env={},
            )
            assert attempted is True
            assert code == 1
            assert not (external / database.name).exists()
            assert not (moved_parent / database.name).exists()
            assert not result.exists()
            _assert_no_sensitive_output(captured, database, external)
        finally:
            result.unlink(missing_ok=True)
            if parent.exists():
                parent.rmdir()
            history_admin_module.remove_attested_temp_dir(attested)


@requires_surface
class TestResultBoundaryBeforeTransactions:
    @pytest.mark.parametrize("linked_component", ["root", "destination"])
    def test_linked_result_boundary_preflight_causes_zero_repository_writes(
        self,
        linked_component,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        """Catches result-boundary validation deferred until after a DB commit."""

        worktree = tmp_path / "writer-worktree"
        launcher = worktree / "scripts" / "history_admin.py"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("# test launcher\n", encoding="utf-8")
        monkeypatch.setattr(writer_module, "_CHECKED_IN_LAUNCHER", launcher)
        result_root = worktree / "tmp" / "twinops-admin-results"
        external = tmp_path / "external-result-boundary"
        external.mkdir()
        result = result_root / "stage.json"
        if linked_component == "root":
            result_root.parent.mkdir(parents=True)
            try:
                result_root.symlink_to(external, target_is_directory=True)
            except OSError:
                result_root.mkdir()
                monkeypatch.setattr(
                    writer_module,
                    "_is_windows_reparse_point",
                    lambda path, value: Path(path) == result_root,
                )
        else:
            result_root.mkdir(parents=True)
            external_file = external / "existing.json"
            external_file.write_bytes(b'{"external":true}\n')
            try:
                result.symlink_to(external_file)
            except OSError:
                result.write_bytes(b"linked-placeholder")
                monkeypatch.setattr(
                    writer_module,
                    "_is_windows_reparse_point",
                    lambda path, value: Path(path) == result,
                )

        source = tmp_path / "history.csv"
        source_bytes = b"synthetic registered bytes\r\n"
        source.write_bytes(source_bytes)
        prepared = _prepared_batch(source_bytes)
        monkeypatch.setattr(
            history_admin_module,
            "prepare_historical_batch",
            lambda *args, **kwargs: prepared,
        )
        repository = RepositorySpy()
        args = _set_option(
            _stage_args(source.resolve(), result, mode="--apply"),
            "--expected-sha256",
            prepared.source_sha256,
        )

        code, captured, _ = _invoke(args, capsys, repository=repository)

        assert code == 1
        assert repository.write_calls == []
        if linked_component == "root":
            assert not (external / result.name).exists()
        else:
            assert (external / "existing.json").read_bytes() == b'{"external":true}\n'
        _assert_no_sensitive_output(captured, source.resolve(), external)


@requires_surface
class TestClosedGrammarAndDryRunState:
    def test_show_active_rejects_nonregistered_asset_before_repository_access(
        self,
        capsys,
    ):
        """Catches show-active accepting an asset outside the frozen grammar."""

        result = _result_path("show-asset")
        args = _set_option(_show_args(result), "--asset-id", "other-motor")
        try:
            code, _, factory = _invoke(args, capsys)
            assert code == 1
            assert factory.calls == []
            assert not result.exists()
        finally:
            result.unlink(missing_ok=True)

    def test_history_admin_reexports_task7_read_only_handoff(self):
        """Catches the exact Task 7 import disappearing from the public module."""

        exported = getattr(
            history_admin_module,
            "reattest_local_staged_handoff",
            None,
        )
        assert callable(exported)
        assert "reattest_local_staged_handoff" in history_admin_module.__all__

    def test_stage_dry_run_reports_existing_identical_batch_without_writes(
        self,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        """Catches dry-run predicting an insert without reading stored batch state."""

        source = tmp_path / "history.csv"
        source_bytes = b"synthetic registered bytes\r\n"
        source.write_bytes(source_bytes)
        prepared = _prepared_batch(source_bytes)
        repository = RepositorySpy()
        repository.summary = SimpleNamespace(
            **{
                **vars(repository.summary),
                "batch_id": prepared.batch_id,
                "source_sha256": prepared.source_sha256,
                "manifest_sha256": prepared.manifest_sha256,
                "raw_row_count": len(prepared.raw_rows),
                "sample_count": len(prepared.samples),
            }
        )
        repository.existing_prepared = prepared
        monkeypatch.setattr(
            history_admin_module,
            "prepare_historical_batch",
            lambda *args, **kwargs: prepared,
        )
        result = _result_path("stage-existing-dry-run")
        args = _set_option(
            _stage_args(source.resolve(), result),
            "--expected-sha256",
            prepared.source_sha256,
        )
        try:
            code, captured, _ = _invoke(args, capsys, repository=repository)
            assert code == 0
            payload = json.loads(result.read_bytes())
            assert payload["inserted"] is False
            assert payload["writesPerformed"] == 0
            assert repository.write_calls == []
            _assert_no_sensitive_output(captured, source.resolve())
        finally:
            result.unlink(missing_ok=True)


class _ActivationRetryRepository(RepositorySpy):
    def __init__(self):
        super().__init__()
        self.active = SimpleNamespace(
            **{
                **vars(self.summary),
                "batch_id": ACTIVE,
                "status": "active",
            }
        )

    def activate_batch(self, *, asset_id, batch_id, expected_active_batch_id):
        if expected_active_batch_id != ACTIVE:
            raise RuntimeError("compare-and-swap mismatch")
        self.write_calls.append("activate_batch")
        self.summary = SimpleNamespace(
            **{**vars(self.summary), "status": "active"}
        )
        self.active = self.summary
        return SimpleNamespace(
            asset_id=asset_id,
            batch_id=batch_id,
            previous_active_batch_id=ACTIVE,
            active_batch_id=batch_id,
            activated=True,
            assessment_count=self.summary.assessment_count,
            assessment_manifest_sha256=self.summary.assessment_manifest_sha256,
            writes_performed=2,
        )

    def _activation_predecessor_for_retry(self, *, asset_id, batch_id):
        assert asset_id == ASSET_ID
        assert batch_id == BATCH
        return ACTIVE


class _UnprovedActivationRetryRepository(RepositorySpy):
    def __init__(self):
        super().__init__()
        self.summary = SimpleNamespace(
            **{**vars(self.summary), "status": "active"}
        )
        self.active = self.summary


@requires_surface
class TestCommittedActivationRetry:
    @staticmethod
    def _local_args(database, fingerprint, prepared, result, expected_active):
        args = _activate_args(result, mode="--apply") + [
            "--database-path",
            str(database),
            "--allow-local-write",
        ]
        _set_option(args, "--environment", "local")
        _set_option(args, "--expected-target-fingerprint", fingerprint)
        _set_option(args, "--batch-id", prepared.batch_id)
        _set_option(args, "--expected-source-sha256", prepared.source_sha256)
        _set_option(args, "--expected-manifest-sha256", prepared.manifest_sha256)
        _set_option(args, "--expected-assessment-manifest-sha256", "none")
        _set_option(args, "--expected-active-batch", expected_active)
        return args

    def test_first_activation_retry_proves_no_predecessor_without_second_cas(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches committed first activation being unretryable for expected none."""

        attested = history_admin_module.create_attested_temp_dir()
        database = Path(attested.path) / "first-activation-retry.sqlite3"
        fingerprint = _create_local_admin_database(database)
        repository = SQLiteHistoricalRepositoryV1(database)
        prepared = _synthetic_admin_batch(0)
        ticks = iter(
            (
                NOW + timedelta(seconds=1),
                NOW + timedelta(seconds=2),
            )
        )
        monkeypatch.setattr(
            sqlite_repository_module,
            "_now_utc_millis",
            lambda: next(ticks),
        )
        repository.stage_batch(prepared)
        cas_calls = 0
        real_activate = repository.activate_batch

        def counted_activate(**kwargs):
            nonlocal cas_calls
            cas_calls += 1
            return real_activate(**kwargs)

        monkeypatch.setattr(repository, "activate_batch", counted_activate)
        real_writer = history_admin_module.AdminResultWriterV1
        publication_calls = 0

        class FailOnceWriter(real_writer):
            def write(self, value):
                nonlocal publication_calls
                publication_calls += 1
                if publication_calls == 1:
                    raise OSError("injected first publication failure")
                return super().write(value)

        monkeypatch.setattr(history_admin_module, "AdminResultWriterV1", FailOnceWriter)
        result = _result_path("first-activation-retry-none")
        args = self._local_args(database, fingerprint, prepared, result, "none")
        try:
            first, _, _ = _invoke(args, capsys, env={}, repository=repository)
            second, captured, _ = _invoke(args, capsys, env={}, repository=repository)

            assert first == 1
            assert second == 0
            assert cas_calls == 1
            payload = json.loads(result.read_bytes())
            assert payload["previousActiveBatchId"] is None
            assert payload["activeBatchId"] == prepared.batch_id
            assert payload["writesPerformed"] == 1
            _assert_no_sensitive_output(captured, database)
        finally:
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)

    def test_retry_rejects_older_non_immediate_superseded_batch_without_cas(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches any older superseded batch being accepted as predecessor proof."""

        attested = history_admin_module.create_attested_temp_dir()
        database = Path(attested.path) / "activation-predecessor.sqlite3"
        fingerprint = _create_local_admin_database(database)
        repository = SQLiteHistoricalRepositoryV1(database)
        first_batch = _synthetic_admin_batch(0)
        immediate_batch = _synthetic_admin_batch(1)
        active_batch = _synthetic_admin_batch(2)
        ticks = iter(NOW + timedelta(seconds=value) for value in range(1, 7))
        monkeypatch.setattr(
            sqlite_repository_module,
            "_now_utc_millis",
            lambda: next(ticks),
        )
        for prepared in (first_batch, immediate_batch, active_batch):
            repository.stage_batch(prepared)
        repository.activate_batch(
            asset_id=ASSET_ID,
            batch_id=first_batch.batch_id,
            expected_active_batch_id=None,
        )
        repository.activate_batch(
            asset_id=ASSET_ID,
            batch_id=immediate_batch.batch_id,
            expected_active_batch_id=first_batch.batch_id,
        )
        repository.activate_batch(
            asset_id=ASSET_ID,
            batch_id=active_batch.batch_id,
            expected_active_batch_id=immediate_batch.batch_id,
        )
        cas_calls = 0
        real_activate = repository.activate_batch

        def counted_activate(**kwargs):
            nonlocal cas_calls
            cas_calls += 1
            return real_activate(**kwargs)

        monkeypatch.setattr(repository, "activate_batch", counted_activate)
        result = _result_path("non-immediate-activation-predecessor")
        args = self._local_args(
            database,
            fingerprint,
            active_batch,
            result,
            first_batch.batch_id,
        )
        try:
            code, captured, _ = _invoke(args, capsys, env={}, repository=repository)

            assert code == 1
            assert cas_calls == 0
            assert not result.exists()
            assert repository.active_batch(ASSET_ID).batch_id == active_batch.batch_id
            _assert_no_sensitive_output(captured, database)
        finally:
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)

    def test_retry_fails_closed_when_activation_timestamps_tie(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches batch-ID ordering inventing a predecessor for tied activations."""

        attested = history_admin_module.create_attested_temp_dir()
        database = Path(attested.path) / "activation-predecessor-tie.sqlite3"
        fingerprint = _create_local_admin_database(database)
        repository = SQLiteHistoricalRepositoryV1(database)
        first_batch = _synthetic_admin_batch(0)
        tied_batch = _synthetic_admin_batch(1)
        active_batch = _synthetic_admin_batch(2)
        ticks = iter(
            (
                NOW + timedelta(seconds=1),
                NOW + timedelta(seconds=2),
                NOW + timedelta(seconds=3),
                NOW + timedelta(seconds=4),
                NOW + timedelta(seconds=4),
                NOW + timedelta(seconds=5),
            )
        )
        monkeypatch.setattr(
            sqlite_repository_module,
            "_now_utc_millis",
            lambda: next(ticks),
        )
        for prepared in (first_batch, tied_batch, active_batch):
            repository.stage_batch(prepared)
        repository.activate_batch(
            asset_id=ASSET_ID,
            batch_id=first_batch.batch_id,
            expected_active_batch_id=None,
        )
        repository.activate_batch(
            asset_id=ASSET_ID,
            batch_id=tied_batch.batch_id,
            expected_active_batch_id=first_batch.batch_id,
        )
        repository.activate_batch(
            asset_id=ASSET_ID,
            batch_id=active_batch.batch_id,
            expected_active_batch_id=tied_batch.batch_id,
        )
        result = _result_path("activation-predecessor-tie")
        args = self._local_args(
            database,
            fingerprint,
            active_batch,
            result,
            tied_batch.batch_id,
        )
        try:
            code, captured, _ = _invoke(args, capsys, env={}, repository=repository)
            assert code == 1
            assert not result.exists()
            assert repository.active_batch(ASSET_ID).batch_id == active_batch.batch_id
            _assert_no_sensitive_output(captured, database)
        finally:
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)

    def test_retry_double_without_explicit_predecessor_proof_fails_closed(
        self,
        capsys,
    ):
        """Catches a test double silently authorizing retry from active state alone."""

        repository = _UnprovedActivationRetryRepository()
        result = _result_path("activation-retry-unproved-double")
        args = _set_option(
            _activate_args(result, mode="--apply"),
            "--expected-active-batch",
            ACTIVE,
        )
        try:
            code, captured, _ = _invoke(args, capsys, repository=repository)
            assert code == 1
            assert repository.write_calls == []
            assert not result.exists()
            _assert_no_sensitive_output(captured)
        finally:
            result.unlink(missing_ok=True)

    def test_postgres_retry_rejects_non_immediate_predecessor_from_fresh_rows(
        self,
        capsys,
    ):
        """Catches the PostgreSQL retry path trusting only one older summary."""

        older_id = ACTIVE
        immediate_id = "sha256:" + "8" * 64
        target = SimpleNamespace(
            **{
                **vars(RepositorySpy().summary),
                "status": "active",
                "activated_at": NOW + timedelta(seconds=3),
            }
        )
        older = SimpleNamespace(
            **{
                **vars(target),
                "batch_id": older_id,
                "status": "superseded",
                "activated_at": NOW + timedelta(seconds=1),
            }
        )
        rows = [
            {
                "batch_id": older_id,
                "status": "superseded",
                "activated_at": NOW + timedelta(seconds=1),
            },
            {
                "batch_id": immediate_id,
                "status": "superseded",
                "activated_at": NOW + timedelta(seconds=2),
            },
            {
                "batch_id": BATCH,
                "status": "active",
                "activated_at": NOW + timedelta(seconds=3),
            },
        ]

        class FakeCursor:
            def fetchall(self):
                return rows

        class FakeConnection:
            def execute(self, statement, parameters):
                assert "historical_import_batches_v1" in statement
                assert parameters == (ASSET_ID,)
                return FakeCursor()

        @contextmanager
        def fake_connection():
            yield FakeConnection()

        support = RepositorySpy()
        repository = PostgresHistoricalRepositoryV1("postgresql://unused")
        repository.summary = target
        repository.verify_schema = support.verify_schema
        repository.target_identity = support.target_identity
        repository.collection_policy = support.collection_policy
        repository.effective_collection_policy = support.effective_collection_policy
        repository.active_batch = lambda asset_id: target
        repository._connection = fake_connection
        repository._stored_batch = lambda connection, batch_id: SimpleNamespace(
            summary=older
        )
        result = _result_path("postgres-non-immediate-predecessor")
        args = _set_option(
            _activate_args(result, mode="--apply"),
            "--expected-active-batch",
            older_id,
        )
        try:
            code, captured, _ = _invoke(args, capsys, repository=repository)
            assert code == 1
            assert not result.exists()
            _assert_no_sensitive_output(captured)
        finally:
            result.unlink(missing_ok=True)
    def test_identical_retry_reproduces_committed_activation_without_second_cas(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches an identical retry rejecting its own committed active target."""

        repository = _ActivationRetryRepository()
        result = _result_path("activation-retry")
        real_writer = history_admin_module.AdminResultWriterV1
        write_attempts = 0

        class FailOnceWriter(real_writer):
            def write(self, value):
                nonlocal write_attempts
                write_attempts += 1
                if write_attempts == 1:
                    raise OSError("injected publication failure")
                return super().write(value)

        monkeypatch.setattr(history_admin_module, "AdminResultWriterV1", FailOnceWriter)
        args = _set_option(
            _activate_args(result, mode="--apply"),
            "--expected-active-batch",
            ACTIVE,
        )
        try:
            first, _, _ = _invoke(args, capsys, repository=repository)
            second, captured, _ = _invoke(args, capsys, repository=repository)

            assert first == 1
            assert second == 0
            assert repository.write_calls == ["activate_batch"]
            payload = json.loads(result.read_bytes())
            assert payload["batchId"] == BATCH
            assert payload["previousActiveBatchId"] == ACTIVE
            assert payload["activeBatchId"] == BATCH
            assert payload["sourceSha256"] == SOURCE
            assert payload["manifestSha256"] == MANIFEST
            assert payload["assessmentManifestSha256"] == ASSESSMENT_MANIFEST
            assert payload["activated"] is True
            assert payload["writesPerformed"] == 2
            _assert_no_sensitive_output(captured)
        finally:
            result.unlink(missing_ok=True)

    def test_different_retry_does_not_weaken_original_compare_and_swap(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches retry recovery treating a different CAS request as identical."""

        repository = _ActivationRetryRepository()
        result = _result_path("activation-different-retry")
        real_writer = history_admin_module.AdminResultWriterV1
        write_attempts = 0

        class FailOnceWriter(real_writer):
            def write(self, value):
                nonlocal write_attempts
                write_attempts += 1
                if write_attempts == 1:
                    raise OSError("injected publication failure")
                return super().write(value)

        monkeypatch.setattr(history_admin_module, "AdminResultWriterV1", FailOnceWriter)
        original = _set_option(
            _activate_args(result, mode="--apply"),
            "--expected-active-batch",
            ACTIVE,
        )
        first, _, _ = _invoke(original, capsys, repository=repository)
        different = _set_option(
            _activate_args(result, mode="--apply"),
            "--expected-active-batch",
            "none",
        )
        second, captured, _ = _invoke(different, capsys, repository=repository)

        assert first == second == 1
        assert repository.write_calls == ["activate_batch"]
        assert not result.exists()
        _assert_no_sensitive_output(captured)


class _PostCommitDivergenceRepository(RepositorySpy):
    def __init__(self, divergence: str):
        super().__init__()
        self.divergence = divergence
        self.after_commit = False

    def verify_schema(self, expected_version):
        if self.after_commit and self.divergence == "schema":
            self.read_calls.append("verify_schema")
            return SchemaVerification(expected_version, "002", {}, False)
        return super().verify_schema(expected_version)

    def target_identity(self):
        if self.after_commit and self.divergence == "identity":
            self.read_calls.append("target_identity")
            return DeploymentIdentityV1(
                environment="production",
                label="wrong/wrong",
                target_fingerprint="sha256:" + "9" * 64,
                schema_version="002",
            )
        return super().target_identity()

    def collection_policy(self, policy_id):
        if self.after_commit and self.divergence == "policy":
            self.read_calls.append("collection_policy")
            return SimpleNamespace(
                collection_policy_id=INITIAL_COLLECTION_POLICY_ID,
                configuration_hash="sha256:" + "9" * 64,
            )
        return super().collection_policy(policy_id)

    def effective_collection_policy(self, asset_id, at):
        if self.after_commit and self.divergence == "policy":
            self.read_calls.append("effective_collection_policy")
            return None
        return super().effective_collection_policy(asset_id, at)

    def stage_batch(self, prepared):
        committed = super().stage_batch(prepared)
        self.after_commit = True
        if self.divergence == "batch":
            self.summary = SimpleNamespace(
                **{
                    **vars(self.summary),
                    "manifest_sha256": "sha256:" + "9" * 64,
                    "raw_row_count": self.summary.raw_row_count + 1,
                }
            )
        return committed

    def activate_batch(self, *, asset_id, batch_id, expected_active_batch_id):
        committed = super().activate_batch(
            asset_id=asset_id,
            batch_id=batch_id,
            expected_active_batch_id=expected_active_batch_id,
        )
        self.after_commit = True
        if self.divergence == "batch":
            self.summary = SimpleNamespace(
                **{
                    **vars(self.summary),
                    "status": "active",
                    "assessment_count": self.summary.assessment_count + 1,
                    "assessment_manifest_sha256": "sha256:" + "9" * 64,
                }
            )
            self.active = self.summary
        return committed


@requires_surface
class TestFreshPostCommitRereads:
    @pytest.mark.parametrize("divergence", ["identity", "schema", "policy", "batch"])
    def test_stage_apply_divergence_fails_before_result_publication(
        self,
        divergence,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        """Catches stage results built from pre-commit or repository return values."""

        source = tmp_path / "history.csv"
        source_bytes = b"synthetic registered bytes\r\n"
        source.write_bytes(source_bytes)
        prepared = _prepared_batch(source_bytes)
        monkeypatch.setattr(
            history_admin_module,
            "prepare_historical_batch",
            lambda *args, **kwargs: prepared,
        )
        repository = _PostCommitDivergenceRepository(divergence)
        result = _result_path(f"stage-postcommit-{divergence}")
        args = _set_option(
            _stage_args(source.resolve(), result, mode="--apply"),
            "--expected-sha256",
            prepared.source_sha256,
        )

        try:
            code, captured, _ = _invoke(args, capsys, repository=repository)

            assert code == 1
            assert repository.write_calls == ["stage_batch"]
            assert not result.exists()
            _assert_no_sensitive_output(captured, source.resolve())
        finally:
            result.unlink(missing_ok=True)

    @pytest.mark.parametrize("divergence", ["identity", "schema", "policy", "batch"])
    def test_activation_apply_divergence_fails_before_result_publication(
        self,
        divergence,
        capsys,
    ):
        """Catches activation results emitted without a fresh committed-state reread."""

        repository = _PostCommitDivergenceRepository(divergence)
        result = _result_path(f"activate-postcommit-{divergence}")

        try:
            code, captured, _ = _invoke(
                _activate_args(result, mode="--apply"),
                capsys,
                repository=repository,
            )

            assert code == 1
            assert repository.write_calls == ["activate_batch"]
            assert not result.exists()
            _assert_no_sensitive_output(captured)
        finally:
            result.unlink(missing_ok=True)


class _PsycopgIdentityConnection:
    def __init__(self, database: str, schema: str):
        self.database = database
        self.schema = schema
        self.queries: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))
        return SimpleNamespace(fetchone=lambda: (self.database, self.schema))


def _remote_target(
    *,
    environment: str = "preview",
    project: str = "project-test",
    branch: str = "branch-test",
    fingerprint: str = TARGET,
):
    return history_admin_module.RepositoryTargetV1(
        environment=environment,
        expected_target_fingerprint=fingerprint,
        expected_schema_version=SCHEMA_VERSION,
        database_path=None,
        database_url="postgresql://secret-user:secret-pass@secret-host/database",
        project_id=project,
        branch_id=branch,
        local_permit=None,
    )


@requires_surface
class TestRepositoryFromTargetPsycopgBoundary:
    @pytest.mark.parametrize(
        "changed",
        ["project", "branch", "database", "schema"],
    )
    def test_remote_fingerprint_is_sensitive_to_every_public_identity_component(
        self,
        changed,
        monkeypatch,
    ):
        """Catches repository construction ignoring one remote identity component."""

        expected = history_admin_module.compute_postgres_target_fingerprint(
            project_id="project-test",
            branch_id="branch-test",
            database="history",
            schema="public",
        )
        project = "project-other" if changed == "project" else "project-test"
        branch = "branch-other" if changed == "branch" else "branch-test"
        database = "history_other" if changed == "database" else "history"
        schema = "private" if changed == "schema" else "public"
        connection = _PsycopgIdentityConnection(database, schema)
        monkeypatch.setattr(
            history_admin_module.psycopg,
            "connect",
            lambda database_url: connection,
        )

        with pytest.raises(history_admin_module.HistoryAdminError) as failure:
            history_admin_module.repository_from_target(
                _remote_target(
                    project=project,
                    branch=branch,
                    fingerprint=expected,
                )
            )

        assert failure.value.stage == "target_identity"
        assert connection.queries == [
            ("SELECT current_database(), current_schema()", None)
        ]

    @pytest.mark.parametrize("environment", ["preview", "production"])
    def test_preview_and_production_accept_only_matching_fake_server_identity(
        self,
        environment,
        monkeypatch,
    ):
        """Catches an environment branch that skips SQL database/schema identity."""

        fingerprint = history_admin_module.compute_postgres_target_fingerprint(
            project_id="project-test",
            branch_id="branch-test",
            database="history",
            schema="public",
        )
        connection = _PsycopgIdentityConnection("history", "public")
        monkeypatch.setattr(
            history_admin_module.psycopg,
            "connect",
            lambda database_url: connection,
        )

        repository = history_admin_module.repository_from_target(
            _remote_target(environment=environment, fingerprint=fingerprint)
        )

        assert repository.database_url.endswith("@secret-host/database")
        assert len(connection.queries) == 1

    def test_remote_connection_failure_is_sanitized_by_public_main(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches DSN-bearing psycopg exceptions leaking through the CLI boundary."""

        def fail_connect(database_url):
            raise RuntimeError(f"connection failed for {database_url}")

        monkeypatch.setattr(history_admin_module.psycopg, "connect", fail_connect)
        result = _result_path("fake-psycopg-failure")
        code = main(
            _show_args(result),
            env=_remote_env(),
            clock=lambda: NOW,
            repository_factory=history_admin_module.repository_from_target,
        )
        captured = capsys.readouterr()

        assert code == 1
        assert not result.exists()
        _assert_no_sensitive_output(captured, _remote_env()["DATABASE_URL"])

    def test_deployment_label_mismatch_after_remote_connect_fails_before_writes(
        self,
    ):
        """Catches project/branch fingerprint checks replacing deployment-label binding."""

        target = _remote_target(fingerprint=TARGET)
        repository = RepositorySpy()
        repository.target_identity_value = DeploymentIdentityV1(
            environment="preview",
            label="project-test/wrong-branch",
            target_fingerprint=TARGET,
            schema_version=SCHEMA_VERSION,
        )

        with pytest.raises(history_admin_module.HistoryAdminError):
            history_admin_module._preflight_repository(repository, target)

        assert repository.write_calls == []


def _create_local_admin_database(path: Path) -> str:
    fingerprint = _local_fingerprint(path)
    with closing(sqlite3.connect(path)) as connection:
        apply_sqlite_migrations(
            connection,
            registered_migration_specs(),
            initial_policy_effective_from=NOW,
        )
        connection.execute("BEGIN IMMEDIATE")
        ensure_deployment_identity(
            connection,
            DeploymentIdentityV1(
                environment="local",
                label="local-history-admin",
                target_fingerprint=fingerprint,
                schema_version=SCHEMA_VERSION,
            ),
        )
        connection.commit()
    return fingerprint


def _local_seed_args(database: Path, fingerprint: str) -> list[str]:
    args = _seed_args(mode="--apply", environment="local") + [
        "--database-path",
        str(database),
        "--allow-local-write",
    ]
    return _set_option(args, "--expected-target-fingerprint", fingerprint)


@requires_surface
class TestSeedCollectionPolicyPhaseA:
    @pytest.mark.parametrize(
        "timestamp",
        [
            "2026-05-19T15:00:00Z",
            "2026-05-19T15:00:00.000+00:00",
            "2026-05-19 15:00:00.000Z",
            "not-a-time",
        ],
    )
    def test_seed_rejects_noncanonical_public_time_before_repository_access(
        self,
        timestamp,
        capsys,
    ):
        """Catches seed accepting timestamps outside exact UTC-millisecond grammar."""

        args = _set_option(_seed_args(), "--effective-from", timestamp)
        code, _, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.calls == []
        assert factory.repository.write_calls == []

    @pytest.mark.parametrize("stored", ["identical", "absent"])
    def test_seed_dry_run_reads_pinned_policy_and_performs_zero_writes(
        self,
        stored,
        capsys,
    ):
        """Catches dry-run writing or skipping pinned-policy equality checks."""

        repository = RepositorySpy()
        if stored == "absent":
            repository.collection_policy = lambda policy_id: None
        code, captured, _ = _invoke(
            _seed_args(),
            capsys,
            repository=repository,
        )
        payload = json.loads(captured.out)

        assert code == 0
        assert payload["command"] == "seed-collection-policy"
        assert payload["policyInserted"] is (stored == "absent")
        assert payload["writesPerformed"] == 0
        assert repository.write_calls == []
        _assert_no_sensitive_output(captured)

    def test_seed_rejects_same_id_with_nonidentical_pinned_policy(self, capsys):
        """Catches policy-ID equality being treated as full pinned-policy equality."""

        repository = RepositorySpy()
        repository.collection_policy = lambda policy_id: initial_collection_policy(
            datetime(2026, 5, 19, 16, tzinfo=timezone.utc)
        )
        code, captured, _ = _invoke(
            _seed_args(),
            capsys,
            repository=repository,
        )
        assert code == 1
        assert repository.write_calls == []
        _assert_no_sensitive_output(captured)

    def test_local_seed_apply_requires_explicit_write_authorization(self, capsys):
        """Catches seed omitting the local capability gate used by other writes."""

        database = WORKTREE_ROOT / "tmp" / "must-not-be-created.sqlite3"
        args = _seed_args(mode="--apply", environment="local") + [
            "--database-path",
            str(database),
        ]
        code, _, factory = _invoke(args, capsys, env={})
        assert code == 1
        assert factory.calls == []
        assert not database.exists()

    def test_remote_seed_identity_mismatch_performs_zero_writes(self, capsys):
        """Catches seed bypassing the common remote deployment identity preflight."""

        repository = RepositorySpy()
        repository.target_identity_value = DeploymentIdentityV1(
            environment="production",
            label="wrong/wrong",
            target_fingerprint="sha256:" + "9" * 64,
            schema_version="002",
        )
        code, captured, _ = _invoke(
            _seed_args(mode="--apply"),
            capsys,
            repository=repository,
        )
        assert code == 1
        assert repository.write_calls == []
        _assert_no_sensitive_output(captured)

    def test_local_seed_apply_is_idempotent_after_first_insert(
        self,
        capsys,
    ):
        """Catches seed replay changing or duplicating the pinned policy."""

        attested = history_admin_module.create_attested_temp_dir()
        database = Path(attested.path) / "seed.sqlite3"
        fingerprint = _create_local_admin_database(database)
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "DELETE FROM collection_policies_v1 WHERE policy_id=?",
                (INITIAL_COLLECTION_POLICY_ID,),
            )
            connection.commit()
        args = _local_seed_args(database, fingerprint)
        try:
            first = main(
                args,
                env={},
                clock=lambda: NOW,
                repository_factory=history_admin_module.repository_from_target,
            )
            first_capture = capsys.readouterr()
            second = main(
                args,
                env={},
                clock=lambda: NOW,
                repository_factory=history_admin_module.repository_from_target,
            )
            second_capture = capsys.readouterr()

            assert first == second == 0
            assert json.loads(first_capture.out)["policyInserted"] is True
            assert json.loads(first_capture.out)["writesPerformed"] == 1
            assert json.loads(second_capture.out)["policyInserted"] is False
            assert json.loads(second_capture.out)["writesPerformed"] == 0
            with closing(sqlite3.connect(database)) as connection:
                assert connection.execute(
                    "SELECT COUNT(*) FROM collection_policies_v1 "
                    "WHERE policy_id=?",
                    (INITIAL_COLLECTION_POLICY_ID,),
                ).fetchone()[0] == 1
        finally:
            history_admin_module.remove_attested_temp_dir(attested)

    def test_seed_conflict_rolls_back_partial_policy_insert(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches a failed policy seed leaving its insert committed."""

        attested = history_admin_module.create_attested_temp_dir()
        database = Path(attested.path) / "seed-rollback.sqlite3"
        fingerprint = _create_local_admin_database(database)
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "DELETE FROM collection_policies_v1 WHERE policy_id=?",
                (INITIAL_COLLECTION_POLICY_ID,),
            )
            connection.commit()
        real_seed = history_admin_module.ensure_initial_collection_policy

        def insert_then_fail(connection, *, effective_from):
            real_seed(connection, effective_from=effective_from)
            raise RuntimeError("injected policy conflict")

        monkeypatch.setattr(
            history_admin_module,
            "ensure_initial_collection_policy",
            insert_then_fail,
        )
        try:
            code = main(
                _local_seed_args(database, fingerprint),
                env={},
                clock=lambda: NOW,
                repository_factory=history_admin_module.repository_from_target,
            )
            captured = capsys.readouterr()
            assert code == 1
            with closing(sqlite3.connect(database)) as connection:
                assert connection.execute(
                    "SELECT COUNT(*) FROM collection_policies_v1 "
                    "WHERE policy_id=?",
                    (INITIAL_COLLECTION_POLICY_ID,),
                ).fetchone()[0] == 0
            _assert_no_sensitive_output(captured, database)
        finally:
            history_admin_module.remove_attested_temp_dir(attested)

    def test_build_assessments_stays_phase_b_grammar_without_repository_access(
        self,
        capsys,
    ):
        """Catches Phase A accidentally executing the Phase B assessment command."""

        result = _result_path("phase-b-only")
        args = _base("build-assessments") + [
            "--dry-run",
            "--batch-id",
            BATCH,
            "--result-json",
            str(result),
        ]
        code, captured, factory = _invoke(args, capsys)
        assert code == 1
        assert factory.calls == []
        assert not result.exists()
        _assert_no_sensitive_output(captured)


def _local_stage_command(
    *,
    database: Path,
    fingerprint: str,
    source: Path,
    source_sha256: str,
    result: Path,
    mode: str,
) -> list[str]:
    args = _stage_args(source.resolve(), result, mode=mode) + [
        "--database-path",
        str(database),
    ]
    if mode == "--apply":
        args.append("--allow-local-write")
    _set_option(args, "--environment", "local")
    _set_option(args, "--expected-target-fingerprint", fingerprint)
    _set_option(args, "--expected-sha256", source_sha256)
    return args


def _sqlite_tracing_repository_factory(dml: list[str], *, mutate=None):
    def factory(target):
        repository = history_admin_module.repository_from_target(target)
        guarded_connect = repository._connection_factory

        def traced_connect(path):
            connection = guarded_connect(path)
            connection.set_trace_callback(
                lambda statement: dml.append(statement)
                if statement.lstrip().upper().startswith(
                    ("INSERT", "UPDATE", "DELETE", "REPLACE")
                )
                else None
            )
            return connection

        repository._connection_factory = traced_connect
        if mutate is not None:
            mutate(repository)
        return repository

    return factory


@requires_surface
class TestStageExistingBatchRecoveryRound3:
    def test_real_sqlite_retry_reuses_committed_ingested_at_across_two_clocks(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches retry rebuilding stored sample provenance with the retry clock."""

        attested = history_admin_module.create_attested_temp_dir()
        root = Path(attested.path)
        database = root / "clock-retry.sqlite3"
        fingerprint = _create_local_admin_database(database)
        source_bytes, synthetic_profile, expected_first = _synthetic_admin_material(
            0,
            ingested_at=NOW + timedelta(minutes=1),
        )
        source = root / "clock-retry.csv"
        source.write_bytes(source_bytes)
        result = _result_path("clock-varying-stage-retry")
        real_writer = history_admin_module.AdminResultWriterV1
        publication_calls = 0
        dml: list[str] = []

        def prepare(source_payload, *, profile, asset_id, ingested_at):
            del profile
            return _prepare_historical_batch_for_profile(
                source_payload,
                profile=synthetic_profile,
                asset_id=asset_id,
                ingested_at=ingested_at,
            )

        class FailOnceWriter(real_writer):
            def write(self, value):
                nonlocal publication_calls
                publication_calls += 1
                if publication_calls == 1:
                    raise OSError("injected result publication failure")
                return super().write(value)

        monkeypatch.setattr(history_admin_module, "prepare_historical_batch", prepare)
        monkeypatch.setattr(history_admin_module, "AdminResultWriterV1", FailOnceWriter)
        args = _local_stage_command(
            database=database,
            fingerprint=fingerprint,
            source=source,
            source_sha256=expected_first.source_sha256,
            result=result,
            mode="--apply",
        )
        clocks = (
            NOW + timedelta(minutes=1),
            NOW + timedelta(minutes=2),
        )
        factory = _sqlite_tracing_repository_factory(dml)
        try:
            first = main(args, env={}, clock=lambda: clocks[0], repository_factory=factory)
            first_dml_count = len(dml)
            with closing(sqlite3.connect(database)) as connection:
                first_evidence = connection.execute(
                    "SELECT imported_at,manifest_sha256,raw_row_count,sample_count "
                    "FROM historical_import_batches_v1 WHERE batch_id=?",
                    (expected_first.batch_id,),
                ).fetchone()
                first_sample_bytes = tuple(
                    row[0]
                    for row in connection.execute(
                        "SELECT canonical_json FROM historical_samples_v1 "
                        "WHERE batch_id=? ORDER BY reading_id",
                        (expected_first.batch_id,),
                    ).fetchall()
                )

            second = main(args, env={}, clock=lambda: clocks[1], repository_factory=factory)
            captured = capsys.readouterr()

            assert first == 1
            assert second == 0
            assert first_dml_count > 0
            assert len(dml) == first_dml_count
            assert first_evidence == (
                "2026-05-19T15:01:00.000Z",
                expected_first.manifest_sha256,
                len(expected_first.raw_rows),
                len(expected_first.samples),
            )
            with closing(sqlite3.connect(database)) as connection:
                second_evidence = connection.execute(
                    "SELECT imported_at,manifest_sha256,raw_row_count,sample_count "
                    "FROM historical_import_batches_v1 WHERE batch_id=?",
                    (expected_first.batch_id,),
                ).fetchone()
                second_sample_bytes = tuple(
                    row[0]
                    for row in connection.execute(
                        "SELECT canonical_json FROM historical_samples_v1 "
                        "WHERE batch_id=? ORDER BY reading_id",
                        (expected_first.batch_id,),
                    ).fetchall()
                )
            assert second_evidence == first_evidence
            assert second_sample_bytes == first_sample_bytes
            payload = json.loads(result.read_bytes())
            assert payload["batchId"] == expected_first.batch_id
            assert payload["manifestSha256"] == expected_first.manifest_sha256
            assert payload["inserted"] is False
            assert payload["writesPerformed"] == 0
            _assert_no_sensitive_output(captured, database, source)
        finally:
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)

    def test_generic_postgres_backed_retry_uses_explicit_stored_prepared_evidence(
        self,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        """Catches generic remote retry invoking stage again with a new clock."""

        source = tmp_path / "generic-postgres-retry.csv"
        source_bytes = b"synthetic registered bytes\r\n"
        source.write_bytes(source_bytes)
        result = _result_path("generic-postgres-clock-retry")
        repository = RepositorySpy()
        real_writer = history_admin_module.AdminResultWriterV1
        publication_calls = 0

        def clock_sensitive_prepare(*args, ingested_at, **kwargs):
            del args, kwargs
            base = _prepared_batch(source_bytes)
            return SimpleNamespace(
                **{
                    **vars(base),
                    "imported_at": ingested_at,
                    "samples": tuple(
                        SimpleNamespace(index=index, ingested_at=ingested_at)
                        for index in range(4)
                    ),
                }
            )

        class FailOnceWriter(real_writer):
            def write(self, value):
                nonlocal publication_calls
                publication_calls += 1
                if publication_calls == 1:
                    raise OSError("injected remote result failure")
                return super().write(value)

        monkeypatch.setattr(
            history_admin_module,
            "prepare_historical_batch",
            clock_sensitive_prepare,
        )
        monkeypatch.setattr(history_admin_module, "AdminResultWriterV1", FailOnceWriter)
        args = _set_option(
            _stage_args(source.resolve(), result, mode="--apply"),
            "--expected-sha256",
            "sha256:" + sha256(source_bytes).hexdigest(),
        )
        factory = RepositoryFactorySpy(repository)
        try:
            first = main(
                args,
                env=_remote_env(),
                clock=lambda: NOW + timedelta(minutes=1),
                repository_factory=factory,
            )
            second = main(
                args,
                env=_remote_env(),
                clock=lambda: NOW + timedelta(minutes=2),
                repository_factory=factory,
            )
            captured = capsys.readouterr()

            assert first == 1
            assert second == 0
            assert repository.write_calls == ["stage_batch"]
            assert repository.existing_prepared.imported_at == NOW + timedelta(minutes=1)
            payload = json.loads(result.read_bytes())
            assert payload["batchId"] == BATCH
            assert payload["inserted"] is False
            assert payload["writesPerformed"] == 0
            _assert_no_sensitive_output(captured, source.resolve())
        finally:
            result.unlink(missing_ok=True)

    @pytest.mark.parametrize(
        "state,statement,expected_code,expected_inserted",
        [
            ("missing", None, 0, True),
            ("valid", None, 0, False),
            (
                "corrupt-projection",
                "UPDATE historical_import_batches_v1 SET raw_row_count=raw_row_count+1",
                1,
                None,
            ),
            (
                "corrupt-manifest",
                "UPDATE historical_import_batches_v1 SET manifest_json=manifest_json || ' '",
                1,
                None,
            ),
            (
                "corrupt-raw",
                "UPDATE historical_raw_rows_v1 SET canonical_values_json='{}' "
                "WHERE record_ordinal=1",
                1,
                None,
            ),
        ],
    )
    def test_real_sqlite_dry_run_distinguishes_missing_valid_and_corrupt_batches(
        self,
        state,
        statement,
        expected_code,
        expected_inserted,
        capsys,
        monkeypatch,
    ):
        """Catches corrupt stored evidence being classified as a missing batch."""

        attested = history_admin_module.create_attested_temp_dir()
        root = Path(attested.path)
        database = root / f"lookup-{state}.sqlite3"
        fingerprint = _create_local_admin_database(database)
        source_bytes, synthetic_profile, prepared = _synthetic_admin_material(0)
        source = root / f"lookup-{state}.csv"
        source.write_bytes(source_bytes)
        if state != "missing":
            SQLiteHistoricalRepositoryV1(database).stage_batch(prepared)
        if statement is not None:
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(statement)
                connection.commit()
        result = _result_path(f"lookup-{state}")
        dml: list[str] = []

        monkeypatch.setattr(
            history_admin_module,
            "prepare_historical_batch",
            lambda payload, *, profile, asset_id, ingested_at: (
                _prepare_historical_batch_for_profile(
                    payload,
                    profile=synthetic_profile,
                    asset_id=asset_id,
                    ingested_at=ingested_at,
                )
            ),
        )
        args = _local_stage_command(
            database=database,
            fingerprint=fingerprint,
            source=source,
            source_sha256=prepared.source_sha256,
            result=result,
            mode="--dry-run",
        )
        try:
            code = main(
                args,
                env={},
                clock=lambda: NOW,
                repository_factory=_sqlite_tracing_repository_factory(dml),
            )
            captured = capsys.readouterr()

            assert code == expected_code
            assert dml == []
            if expected_code == 0:
                payload = json.loads(result.read_bytes())
                assert payload["inserted"] is expected_inserted
                assert payload["writesPerformed"] == 0
            else:
                assert not result.exists()
            _assert_no_sensitive_output(captured, database, source)
        finally:
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)

    def test_real_sqlite_dry_run_propagates_operational_lookup_failure(
        self,
        capsys,
        monkeypatch,
    ):
        """Catches a read failure being converted into an absent-batch prediction."""

        attested = history_admin_module.create_attested_temp_dir()
        root = Path(attested.path)
        database = root / "lookup-operational.sqlite3"
        fingerprint = _create_local_admin_database(database)
        source_bytes, synthetic_profile, prepared = _synthetic_admin_material(0)
        SQLiteHistoricalRepositoryV1(database).stage_batch(prepared)
        source = root / "lookup-operational.csv"
        source.write_bytes(source_bytes)
        result = _result_path("lookup-operational")
        dml: list[str] = []

        monkeypatch.setattr(
            history_admin_module,
            "prepare_historical_batch",
            lambda payload, *, profile, asset_id, ingested_at: (
                _prepare_historical_batch_for_profile(
                    payload,
                    profile=synthetic_profile,
                    asset_id=asset_id,
                    ingested_at=ingested_at,
                )
            ),
        )

        def inject_failure(repository):
            repository._stored_batch = lambda *args, **kwargs: (_ for _ in ()).throw(
                sqlite3.OperationalError("injected lookup failure")
            )

        args = _local_stage_command(
            database=database,
            fingerprint=fingerprint,
            source=source,
            source_sha256=prepared.source_sha256,
            result=result,
            mode="--dry-run",
        )
        try:
            code = main(
                args,
                env={},
                clock=lambda: NOW,
                repository_factory=_sqlite_tracing_repository_factory(
                    dml,
                    mutate=inject_failure,
                ),
            )
            captured = capsys.readouterr()

            assert code == 1
            assert dml == []
            assert not result.exists()
            _assert_no_sensitive_output(captured, database, source, "injected lookup failure")
        finally:
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)


@requires_surface
class TestExactMigrationRereadRound3:
    @pytest.mark.parametrize(
        "requested_effective_from,mutation",
        [
            ("2026-05-19T00:00:00.000Z", None),
            (
                "2026-05-19T15:00:00.000Z",
                "UPDATE collection_policies_v1 "
                "SET effective_to='2026-05-20T00:00:00.000Z' "
                "WHERE policy_id='forzy-live-window-v1'",
            ),
        ],
    )
    def test_existing_migration_dry_run_requires_exact_policy_validity(
        self,
        requested_effective_from,
        mutation,
        capsys,
    ):
        """Catches migration dry-run checking only policy ID/configuration hash."""

        attested = history_admin_module.create_attested_temp_dir()
        database = Path(attested.path) / "migrate-dry-exact.sqlite3"
        fingerprint = _create_local_admin_database(database)
        if mutation is not None:
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(mutation)
                connection.commit()
        result = _result_path("migrate-dry-exact")
        args = _base("migrate-local", environment="local") + [
            "--dry-run",
            "--database-path",
            str(database),
            "--initial-policy-effective-from",
            requested_effective_from,
            "--result-json",
            str(result),
        ]
        _set_option(args, "--expected-target-fingerprint", fingerprint)
        try:
            code = main(args, env={})
            captured = capsys.readouterr()
            assert code == 1
            assert not result.exists()
            _assert_no_sensitive_output(captured, database)
        finally:
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)

    @pytest.mark.parametrize("target_state", ["fresh", "existing"])
    @pytest.mark.parametrize(
        "mutation",
        [
            "policy-validity-mutation",
            "deployment-delete-replace",
            "migration-delete-replace",
        ],
    )
    def test_migration_apply_closes_then_reopens_and_rejects_postcommit_drift(
        self,
        target_state,
        mutation,
        capsys,
        monkeypatch,
    ):
        """Catches migration results published from counts on the write connection."""

        attested = history_admin_module.create_attested_temp_dir()
        database = Path(attested.path) / f"migrate-{target_state}-{mutation}.sqlite3"
        fingerprint = _local_fingerprint(database)
        if target_state == "existing":
            assert _create_local_admin_database(database) == fingerprint
        result = _result_path(f"migrate-{target_state}-{mutation}")
        args = _base("migrate-local", environment="local") + [
            "--apply",
            "--allow-local-write",
            "--database-path",
            str(database),
            "--initial-policy-effective-from",
            "2026-05-19T15:00:00.000Z",
            "--result-json",
            str(result),
        ]
        _set_option(args, "--expected-target-fingerprint", fingerprint)
        real_open = history_admin_module._open_attested_sqlite_connection
        opened: list[sqlite3.Connection] = []
        mutation_ran = False
        write_closed_before_reread = False

        def open_then_mutate(permit, *open_args, **open_kwargs):
            nonlocal mutation_ran, write_closed_before_reread
            if opened and not mutation_ran:
                try:
                    opened[0].execute("SELECT 1")
                except sqlite3.ProgrammingError:
                    write_closed_before_reread = True
                with closing(sqlite3.connect(database)) as connection:
                    if mutation == "policy-validity-mutation":
                        connection.execute(
                            "UPDATE collection_policies_v1 "
                            "SET effective_to='2026-05-20T00:00:00.000Z' "
                            "WHERE policy_id=?",
                            (INITIAL_COLLECTION_POLICY_ID,),
                        )
                    elif mutation == "deployment-delete-replace":
                        connection.execute(
                            "DELETE FROM deployment_identity_v1 WHERE identity_key='primary'"
                        )
                        connection.execute(
                            "INSERT INTO deployment_identity_v1 "
                            "(identity_key,environment,label,target_fingerprint,schema_version) "
                            "VALUES ('primary','local','wrong-label',?,'003')",
                            (fingerprint,),
                        )
                    else:
                        connection.execute(
                            "DELETE FROM schema_migrations_v1 WHERE migration_version='003'"
                        )
                        connection.execute(
                            "INSERT INTO schema_migrations_v1 "
                            "(migration_version,sql_sha256,applied_at) "
                            "VALUES ('004',?,'2026-05-19T15:00:00.000Z')",
                            ("sha256:" + "9" * 64,),
                        )
                    connection.commit()
                mutation_ran = True
            connection = real_open(permit, *open_args, **open_kwargs)
            opened.append(connection)
            return connection

        monkeypatch.setattr(
            history_admin_module,
            "_open_attested_sqlite_connection",
            open_then_mutate,
        )
        try:
            code = main(args, env={})
            captured = capsys.readouterr()

            assert code == 1
            assert mutation_ran is True
            assert write_closed_before_reread is True
            assert len(opened) >= 2
            assert not result.exists()
            _assert_no_sensitive_output(captured, database)
        finally:
            for connection in opened:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass
            result.unlink(missing_ok=True)
            history_admin_module.remove_attested_temp_dir(attested)


@requires_surface
class TestDeterministicResultPreflightRound3:
    @pytest.mark.parametrize("failure", ["oversized", "unreadable"])
    def test_stage_apply_rejects_existing_unpublishable_result_before_repository_write(
        self,
        failure,
        tmp_path,
        capsys,
        monkeypatch,
    ):
        """Catches deterministic destination failure being delayed until after commit."""

        source = tmp_path / f"preflight-{failure}.csv"
        source_bytes = b"synthetic registered bytes\r\n"
        source.write_bytes(source_bytes)
        prepared = _prepared_batch(source_bytes)
        repository = RepositorySpy()
        result = _result_path(f"preflight-{failure}")
        result.parent.mkdir(parents=True, exist_ok=True)
        original_bytes = b"x" * (1024 * 1024 + 1) if failure == "oversized" else b"readable-before-denial\n"
        result.write_bytes(original_bytes)
        monkeypatch.setattr(
            history_admin_module,
            "prepare_historical_batch",
            lambda *args, **kwargs: prepared,
        )
        if failure == "unreadable":
            real_open_child = history_admin_module.AdminResultWriterV1._open_child

            def deny_destination_read(writer, name, flags, mode=0o600):
                if name == result.name and flags & os.O_RDONLY == os.O_RDONLY:
                    raise PermissionError("injected unreadable result")
                return real_open_child(writer, name, flags, mode)

            monkeypatch.setattr(
                history_admin_module.AdminResultWriterV1,
                "_open_child",
                deny_destination_read,
            )
        args = _set_option(
            _stage_args(source.resolve(), result, mode="--apply"),
            "--expected-sha256",
            prepared.source_sha256,
        )
        try:
            code, captured, _ = _invoke(args, capsys, repository=repository)

            assert code == 1
            assert repository.write_calls == []
            assert result.read_bytes() == original_bytes
            _assert_no_sensitive_output(captured, source.resolve(), "injected unreadable result")
        finally:
            result.unlink(missing_ok=True)


@requires_surface
class TestPostgresActivationPredecessorPositiveRound3:
    @pytest.mark.parametrize(
        "expected_predecessor,rows,expected_writes",
        [
            (
                None,
                [
                    {
                        "batch_id": BATCH,
                        "status": "active",
                        "activated_at": NOW + timedelta(seconds=2),
                    }
                ],
                1,
            ),
            (
                ACTIVE,
                [
                    {
                        "batch_id": ACTIVE,
                        "status": "superseded",
                        "activated_at": NOW + timedelta(seconds=1),
                    },
                    {
                        "batch_id": BATCH,
                        "status": "active",
                        "activated_at": NOW + timedelta(seconds=2),
                    },
                ],
                2,
            ),
        ],
    )
    def test_postgres_retry_proves_first_or_immediate_predecessor_without_cas(
        self,
        expected_predecessor,
        rows,
        expected_writes,
        capsys,
    ):
        """Catches the positive PostgreSQL predecessor proof becoming unreachable."""

        target_summary = SimpleNamespace(
            **{
                **vars(RepositorySpy().summary),
                "status": "active",
                "activated_at": NOW + timedelta(seconds=2),
            }
        )

        class FakeCursor:
            def fetchall(self):
                return rows

        class FakeConnection:
            def execute(self, statement, parameters):
                assert "historical_import_batches_v1" in statement
                assert parameters == (ASSET_ID,)
                return FakeCursor()

        @contextmanager
        def fake_connection():
            yield FakeConnection()

        support = RepositorySpy()
        repository = PostgresHistoricalRepositoryV1("postgresql://unused")
        repository.summary = target_summary
        repository.verify_schema = support.verify_schema
        repository.target_identity = support.target_identity
        repository.collection_policy = support.collection_policy
        repository.effective_collection_policy = support.effective_collection_policy
        repository.active_batch = lambda asset_id: target_summary
        repository._connection = fake_connection
        cas_calls = 0

        def forbidden_cas(**kwargs):
            nonlocal cas_calls
            cas_calls += 1
            raise AssertionError("committed retry must not issue a second CAS")

        repository.activate_batch = forbidden_cas
        result = _result_path(
            "postgres-first-positive"
            if expected_predecessor is None
            else "postgres-immediate-positive"
        )
        args = _set_option(
            _activate_args(result, mode="--apply"),
            "--expected-active-batch",
            "none" if expected_predecessor is None else expected_predecessor,
        )
        try:
            code, captured, _ = _invoke(args, capsys, repository=repository)

            assert code == 0
            assert cas_calls == 0
            payload = json.loads(result.read_bytes())
            assert payload["previousActiveBatchId"] == expected_predecessor
            assert payload["activeBatchId"] == BATCH
            assert payload["writesPerformed"] == expected_writes
            _assert_no_sensitive_output(captured)
        finally:
            result.unlink(missing_ok=True)
