from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
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
    from twinops.storage.collection_policy_v1 import (
        INITIAL_COLLECTION_POLICY_CONFIGURATION_HASH,
        INITIAL_COLLECTION_POLICY_ID,
        initial_collection_policy,
        read_collection_policy,
    )
    from twinops.storage.schema_migrations import (
        DeploymentIdentityV1,
        SchemaVerification,
        registered_migration_specs,
        verify_schema_version,
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
        assert repository.write_calls == ["stage_batch", "stage_batch"]
        payload = json.loads(result.read_bytes())
        assert payload["batchId"] == BATCH
        assert payload["manifestSha256"] == prepared.manifest_sha256
        _assert_no_sensitive_output(captured, source.resolve())
        result.unlink(missing_ok=True)
