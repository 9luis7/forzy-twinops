from __future__ import annotations

from contextlib import closing
from copy import copy
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import pickle
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest


WORKTREE_ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = (
    WORKTREE_ROOT
    / "services"
    / "twinops"
    / "src"
    / "twinops"
    / "security"
    / "local_write_guard_v1.py"
)
GUARD_AVAILABLE = MODULE_PATH.is_file()
requires_guard = pytest.mark.skipif(
    not GUARD_AVAILABLE,
    reason="local write guard is the intentional Task A6 RED",
)


if GUARD_AVAILABLE:
    from twinops.security import local_write_guard_v1 as guard_module
    from twinops.security.local_write_guard_v1 import (
        LocalWriteGuardError,
        attest_local_database,
        compute_local_target_fingerprint,
        create_attested_temp_dir,
        preflight_new_local_database,
        reattest_local_database,
        reattest_local_staged_handoff,
    )
    from twinops.storage.schema_migrations import (
        DeploymentIdentityV1,
        apply_sqlite_migrations,
        ensure_deployment_identity,
        registered_migration_specs,
    )
    from twinops.storage.sqlite_historical_repository_v1 import (
        SQLiteHistoricalRepositoryV1,
    )

    storage_tests = WORKTREE_ROOT / "services" / "twinops" / "tests" / "storage"
    if str(storage_tests) not in sys.path:
        sys.path.insert(0, str(storage_tests))
    from historical_repository_contract import synthetic_prepared_batch


SCHEMA_VERSION = "003"
SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64


def _remove_attested_dir(permit) -> None:
    path = Path(permit.path)
    if path.exists():
        shutil.rmtree(path)


@pytest.fixture
def attested_dir():
    permit = create_attested_temp_dir()
    try:
        yield permit
    finally:
        _remove_attested_dir(permit)


def _migration_hashes() -> dict[str, str]:
    return {
        spec.version: spec.sqlite_sha256 for spec in registered_migration_specs()
    }


def _create_migrated_database(path: Path) -> str:
    fingerprint = compute_local_target_fingerprint(
        path,
        expected_schema_version=SCHEMA_VERSION,
        migration_hashes=_migration_hashes(),
    )
    with closing(sqlite3.connect(path)) as connection:
        apply_sqlite_migrations(
            connection,
            registered_migration_specs(),
            initial_policy_effective_from=__import__("datetime").datetime(
                2026,
                5,
                19,
                tzinfo=__import__("datetime").timezone.utc,
            ),
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


def _stage_database(path: Path):
    fingerprint = _create_migrated_database(path)
    prepared = synthetic_prepared_batch(0)
    SQLiteHistoricalRepositoryV1(path).stage_batch(prepared)
    return fingerprint, prepared


@requires_guard
class TestLocalPathGrammarAndContainment:
    @pytest.mark.parametrize(
        "candidate",
        [
            Path("history.sqlite3"),
            Path("..") / "history.sqlite3",
            Path("C:history.sqlite3"),
            Path("C:\\"),
            Path("\\\\server\\share\\history.sqlite3"),
            Path("\\\\?\\C:\\history.sqlite3"),
            Path("\\.\\PhysicalDrive0"),
            Path("//server/share/history.sqlite3"),
            Path("//?/C:/history.sqlite3"),
            Path("//./PhysicalDrive0"),
        ],
    )
    def test_rejects_non_absolute_root_unc_and_device_paths(self, candidate: Path):
        with pytest.raises((LocalWriteGuardError, ValueError)):
            preflight_new_local_database(
                candidate,
                expected_schema_version=SCHEMA_VERSION,
            )

    def test_rejects_external_sibling_even_when_name_has_allowed_prefix(self, tmp_path):
        sibling = WORKTREE_ROOT.parent / f"{WORKTREE_ROOT.name}-evil" / "history.db"
        with pytest.raises(LocalWriteGuardError):
            preflight_new_local_database(
                sibling,
                expected_schema_version=SCHEMA_VERSION,
            )

    def test_rejects_lexical_dot_dot_escape(self):
        candidate = WORKTREE_ROOT / "tmp" / "inside" / ".." / ".." / ".." / "escape.db"
        with pytest.raises(LocalWriteGuardError):
            preflight_new_local_database(
                candidate,
                expected_schema_version=SCHEMA_VERSION,
            )

    def test_rejects_missing_parent(self, attested_dir):
        candidate = Path(attested_dir.path) / "missing" / "history.db"
        with pytest.raises(LocalWriteGuardError):
            preflight_new_local_database(
                candidate,
                expected_schema_version=SCHEMA_VERSION,
            )
        assert not candidate.exists()

    def test_rejects_non_directory_parent(self, attested_dir):
        parent = Path(attested_dir.path) / "not-a-directory"
        parent.write_bytes(b"regular")
        with pytest.raises(LocalWriteGuardError):
            preflight_new_local_database(
                parent / "history.db",
                expected_schema_version=SCHEMA_VERSION,
            )

    def test_rejects_existing_target_when_preflighting_new_database(self, attested_dir):
        target = Path(attested_dir.path) / "history.db"
        target.write_bytes(b"already here")
        with pytest.raises(LocalWriteGuardError):
            preflight_new_local_database(
                target,
                expected_schema_version=SCHEMA_VERSION,
            )
        assert target.read_bytes() == b"already here"

    def test_rejects_existing_non_regular_target(self, attested_dir):
        target = Path(attested_dir.path) / "history.db"
        target.mkdir()
        with pytest.raises(LocalWriteGuardError):
            attest_local_database(
                target,
                expected_schema_version=SCHEMA_VERSION,
                temp_permit=attested_dir,
                require_existing=True,
            )

    def test_rejects_arbitrary_system_temp_directory(self):
        arbitrary = Path(tempfile.mkdtemp(prefix="unattested-task6-"))
        candidate = arbitrary / "history.db"
        try:
            with pytest.raises(LocalWriteGuardError):
                preflight_new_local_database(
                    candidate,
                    expected_schema_version=SCHEMA_VERSION,
                )
        finally:
            shutil.rmtree(arbitrary)

    def test_accepts_same_process_attested_temp_directory(self, attested_dir):
        target = Path(attested_dir.path) / "history.db"
        target.write_bytes(b"sqlite-placeholder")
        permit = attest_local_database(
            target,
            expected_schema_version=SCHEMA_VERSION,
            temp_permit=attested_dir,
            require_existing=True,
        )
        assert permit.path == target.resolve()

    def test_accepts_regular_database_inside_worktree(self):
        parent = WORKTREE_ROOT / "tmp" / "task-6-guard-tests"
        target = parent / f"regular-{os.getpid()}.db"
        parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"sqlite-placeholder")
        try:
            permit = attest_local_database(
                target,
                expected_schema_version=SCHEMA_VERSION,
                require_existing=True,
            )
            assert permit.path == target.resolve()
        finally:
            target.unlink(missing_ok=True)
            try:
                parent.rmdir()
            except OSError:
                pass


@requires_guard
class TestLinksReparseAndMounts:
    def test_rejects_symlinked_parent(self, attested_dir, tmp_path, monkeypatch):
        external = tmp_path / "external"
        external.mkdir()
        linked = Path(attested_dir.path) / "linked"
        try:
            linked.symlink_to(external, target_is_directory=True)
        except OSError:
            linked.mkdir()
            monkeypatch.setattr(
                guard_module,
                "_is_windows_reparse_point",
                lambda path, value: Path(path) == linked,
            )
        with pytest.raises(LocalWriteGuardError):
            preflight_new_local_database(
                linked / "history.db",
                expected_schema_version=SCHEMA_VERSION,
            )

    def test_rejects_symlinked_database_file(
        self,
        attested_dir,
        tmp_path,
        monkeypatch,
    ):
        external = tmp_path / "external.db"
        external.write_bytes(b"external")
        linked = Path(attested_dir.path) / "history.db"
        try:
            linked.symlink_to(external)
        except OSError:
            linked.write_bytes(b"linked-placeholder")
            monkeypatch.setattr(
                guard_module,
                "_is_windows_reparse_point",
                lambda path, value: Path(path) == linked,
            )
        with pytest.raises(LocalWriteGuardError):
            attest_local_database(
                linked,
                expected_schema_version=SCHEMA_VERSION,
                temp_permit=attested_dir,
                require_existing=True,
            )

    def test_mocked_windows_reparse_attribute_is_always_rejected(
        self,
        attested_dir,
        monkeypatch,
    ):
        target = Path(attested_dir.path) / "history.db"
        target.write_bytes(b"regular")
        real_lstat = guard_module.os.lstat

        def reparse_lstat(path, *args, **kwargs):
            result = real_lstat(path, *args, **kwargs)
            if Path(path) == Path(attested_dir.path):
                values = list(result)
                return os.stat_result(values)._replace(
                    st_file_attributes=getattr(result, "st_file_attributes", 0) | 0x400
                )
            return result

        monkeypatch.setattr(guard_module, "_is_windows_reparse_point", lambda path, stat: Path(path) == Path(attested_dir.path))
        with pytest.raises(LocalWriteGuardError):
            attest_local_database(
                target,
                expected_schema_version=SCHEMA_VERSION,
                temp_permit=attested_dir,
                require_existing=True,
            )

    @pytest.mark.skipif(os.name != "nt", reason="real junction is Windows-only")
    def test_real_windows_junction_is_rejected(self, attested_dir, tmp_path):
        external = tmp_path / "junction-target"
        external.mkdir()
        junction = Path(attested_dir.path) / "junction"
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(external)],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            pytest.skip("junction creation privilege is unavailable")
        try:
            with pytest.raises(LocalWriteGuardError):
                preflight_new_local_database(
                    junction / "history.db",
                    expected_schema_version=SCHEMA_VERSION,
                )
        finally:
            junction.rmdir()


@requires_guard
class TestAttestationIdentityAndRaces:
    def test_copied_or_forged_temp_permit_is_rejected(self, attested_dir):
        copied = copy(attested_dir)
        target = Path(attested_dir.path) / "history.db"
        target.write_bytes(b"regular")
        with pytest.raises(LocalWriteGuardError):
            attest_local_database(
                target,
                expected_schema_version=SCHEMA_VERSION,
                temp_permit=copied,
                require_existing=True,
            )

    def test_permit_from_another_creator_pid_is_rejected(
        self,
        attested_dir,
        monkeypatch,
    ):
        target = Path(attested_dir.path) / "history.db"
        target.write_bytes(b"regular")
        creator_pid = os.getpid()
        monkeypatch.setattr(guard_module.os, "getpid", lambda: creator_pid + 1000)
        with pytest.raises(LocalWriteGuardError):
            attest_local_database(
                target,
                expected_schema_version=SCHEMA_VERSION,
                temp_permit=attested_dir,
                require_existing=True,
            )

    def test_replaced_attested_root_is_rejected(self, attested_dir):
        original = Path(attested_dir.path)
        moved = original.with_name(original.name + "-old")
        original.rename(moved)
        original.mkdir()
        try:
            target = original / "history.db"
            target.write_bytes(b"regular")
            with pytest.raises(LocalWriteGuardError):
                attest_local_database(
                    target,
                    expected_schema_version=SCHEMA_VERSION,
                    temp_permit=attested_dir,
                    require_existing=True,
                )
        finally:
            shutil.rmtree(original)
            moved.rename(original)

    def test_parent_replacement_between_preflight_and_transaction_is_rejected(
        self,
        attested_dir,
    ):
        parent = Path(attested_dir.path) / "database"
        parent.mkdir()
        target = parent / "history.db"
        target.write_bytes(b"first")
        permit = attest_local_database(
            target,
            expected_schema_version=SCHEMA_VERSION,
            temp_permit=attested_dir,
            require_existing=True,
        )
        moved = parent.with_name("database-old")
        parent.rename(moved)
        parent.mkdir()
        target.write_bytes(b"second")
        with pytest.raises(LocalWriteGuardError):
            reattest_local_database(permit)
        assert target.read_bytes() == b"second"

    def test_target_replacement_between_preflight_and_open_is_rejected(
        self,
        attested_dir,
    ):
        target = Path(attested_dir.path) / "history.db"
        target.write_bytes(b"first")
        permit = attest_local_database(
            target,
            expected_schema_version=SCHEMA_VERSION,
            temp_permit=attested_dir,
            require_existing=True,
        )
        replacement = Path(attested_dir.path) / "replacement.db"
        replacement.write_bytes(b"second")
        os.replace(replacement, target)
        with pytest.raises(LocalWriteGuardError):
            reattest_local_database(permit)

    def test_target_replacement_after_sqlite_open_is_rejected(
        self,
        attested_dir,
        monkeypatch,
    ):
        target = Path(attested_dir.path) / "history.db"
        sqlite3.connect(target).close()
        permit = attest_local_database(
            target,
            expected_schema_version=SCHEMA_VERSION,
            temp_permit=attested_dir,
            require_existing=True,
        )
        connection = sqlite3.connect(target)
        replacement = Path(attested_dir.path) / "replacement.db"
        sqlite3.connect(replacement).close()
        real_guarded_lstat = guard_module._guarded_lstat

        def changed_target_identity(path):
            if Path(path) == target:
                return os.lstat(replacement)
            return real_guarded_lstat(path)

        monkeypatch.setattr(guard_module, "_guarded_lstat", changed_target_identity)
        try:
            with pytest.raises(LocalWriteGuardError):
                reattest_local_database(permit, opened_connection=connection)
        finally:
            connection.close()

    def test_existing_database_hard_link_is_rejected_without_changing_external_bytes(
        self,
        attested_dir,
        tmp_path,
    ):
        """Catches initial attestation accepting an existing multiply-linked inode."""

        external = tmp_path / "external-hard-linked.sqlite3"
        external.write_bytes(b"external database bytes")
        target = Path(attested_dir.path) / "history.db"
        os.link(external, target)
        before = external.read_bytes()

        with pytest.raises(LocalWriteGuardError):
            attest_local_database(
                target,
                expected_schema_version=SCHEMA_VERSION,
                temp_permit=attested_dir,
                require_existing=True,
            )

        assert external.read_bytes() == before
        assert target.read_bytes() == before

    def test_new_hard_link_after_attestation_is_rejected_on_every_reattest(
        self,
        attested_dir,
    ):
        """Catches repeated attestation ignoring an increased hard-link count."""

        target = Path(attested_dir.path) / "history.db"
        target.write_bytes(b"guarded database bytes")
        permit = attest_local_database(
            target,
            expected_schema_version=SCHEMA_VERSION,
            temp_permit=attested_dir,
            require_existing=True,
        )
        external = Path(attested_dir.path) / "external-alias.db"
        os.link(target, external)
        before = external.read_bytes()

        with pytest.raises(LocalWriteGuardError):
            reattest_local_database(permit)

        assert target.read_bytes() == before
        assert external.read_bytes() == before


@requires_guard
class TestPermitCredentialConfinement:
    def test_permit_credentials_are_absent_from_repr_and_dataclass_export(
        self,
        attested_dir,
    ):
        """Catches capability tokens leaking through repr or dataclasses.asdict."""

        target = Path(attested_dir.path) / "history.db"
        target.write_bytes(b"regular")
        database_permit = attest_local_database(
            target,
            expected_schema_version=SCHEMA_VERSION,
            temp_permit=attested_dir,
            require_existing=True,
        )

        for permit in (attested_dir, database_permit):
            rendered = repr(permit)
            assert "_token" not in rendered
            assert "token=" not in rendered.lower()
            with pytest.raises(TypeError):
                asdict(permit)

    def test_permits_are_not_pickle_serializable(self, attested_dir):
        """Catches capability credentials leaving process memory through pickle."""

        target = Path(attested_dir.path) / "history.db"
        target.write_bytes(b"regular")
        database_permit = attest_local_database(
            target,
            expected_schema_version=SCHEMA_VERSION,
            temp_permit=attested_dir,
            require_existing=True,
        )

        for permit in (attested_dir, database_permit):
            with pytest.raises((TypeError, pickle.PicklingError)):
                pickle.dumps(permit)

    def test_forced_stale_object_id_reuse_cannot_authorize_a_copied_permit(
        self,
        monkeypatch,
    ):
        """Catches registries that trust reusable id(obj) plus copied token fields."""

        monkeypatch.setattr(guard_module, "id", lambda value: 424242, raising=False)
        temp_permit = create_attested_temp_dir()
        try:
            target = Path(temp_permit.path) / "history.db"
            target.write_bytes(b"regular")
            database_permit = attest_local_database(
                target,
                expected_schema_version=SCHEMA_VERSION,
                temp_permit=temp_permit,
                require_existing=True,
            )
            try:
                copied = copy(database_permit)
            except TypeError:
                return

            with pytest.raises(LocalWriteGuardError):
                reattest_local_database(copied)
        finally:
            path = Path(temp_permit.path)
            if path.exists():
                guard_module.remove_attested_temp_dir(temp_permit)


@requires_guard
class TestLocalTargetFingerprint:
    def test_preflight_new_database_is_absence_only_and_creates_nothing(self, attested_dir):
        target = Path(attested_dir.path) / "new.db"
        fingerprint = preflight_new_local_database(
            target,
            expected_schema_version=SCHEMA_VERSION,
            temp_permit=attested_dir,
        )
        assert fingerprint.startswith("sha256:")
        assert len(fingerprint) == 71
        assert not target.exists()

    def test_fingerprint_is_sha256_of_exact_canonical_payload(self, attested_dir):
        target = Path(attested_dir.path) / "new.db"
        hashes = _migration_hashes()
        actual = compute_local_target_fingerprint(
            target,
            expected_schema_version=SCHEMA_VERSION,
            migration_hashes=hashes,
        )
        payload = {
            "kind": "local-sqlite",
            "migrationHashes": dict(sorted(hashes.items())),
            "path": os.path.normcase(str(target.resolve())),
            "schemaVersion": SCHEMA_VERSION,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        assert actual == "sha256:" + sha256(canonical).hexdigest()

    def test_fingerprint_changes_with_path_schema_or_migration_hash(self, attested_dir):
        root = Path(attested_dir.path)
        hashes = _migration_hashes()
        baseline = compute_local_target_fingerprint(
            root / "a.db",
            expected_schema_version=SCHEMA_VERSION,
            migration_hashes=hashes,
        )
        changed_hashes = dict(hashes)
        changed_hashes[min(changed_hashes)] = SHA_C
        variants = {
            compute_local_target_fingerprint(
                root / "b.db",
                expected_schema_version=SCHEMA_VERSION,
                migration_hashes=hashes,
            ),
            compute_local_target_fingerprint(
                root / "a.db",
                expected_schema_version="002",
                migration_hashes=hashes,
            ),
            compute_local_target_fingerprint(
                root / "a.db",
                expected_schema_version=SCHEMA_VERSION,
                migration_hashes=changed_hashes,
            ),
        }
        assert baseline not in variants
        assert len(variants) == 3

    @pytest.mark.parametrize(
        "version,hashes",
        [
            ("3", {"003": SHA_A}),
            ("003", {}),
            ("003", {"003": "not-a-hash"}),
            ("003", {"3": SHA_A}),
        ],
    )
    def test_fingerprint_rejects_noncanonical_schema_and_migration_map(
        self,
        attested_dir,
        version,
        hashes,
    ):
        with pytest.raises(ValueError):
            compute_local_target_fingerprint(
                Path(attested_dir.path) / "new.db",
                expected_schema_version=version,
                migration_hashes=hashes,
            )


@requires_guard
class TestReadOnlyStagedHandoff:
    def _call(self, path: Path, fingerprint: str, prepared, **overrides):
        values = {
            "expected_target_fingerprint": fingerprint,
            "expected_schema_version": SCHEMA_VERSION,
            "expected_batch_id": prepared.batch_id,
            "expected_source_sha256": prepared.source_sha256,
            "expected_manifest_sha256": prepared.manifest_sha256,
            "expected_raw_row_count": len(prepared.raw_rows),
            "expected_sample_count": len(prepared.samples),
            "expected_operating_cycle_count": 1,
            "require_no_active_batch": True,
        }
        values.update(overrides)
        return reattest_local_staged_handoff(path, **values)

    def test_valid_handoff_is_query_only_and_byte_stable(self, attested_dir, capsys):
        path = Path(attested_dir.path) / "history.db"
        fingerprint, prepared = _stage_database(path)
        before = path.read_bytes()
        self._call(path, fingerprint, prepared)
        after = path.read_bytes()
        captured = capsys.readouterr()
        assert after == before
        assert captured.out == captured.err == ""
        assert not list(path.parent.glob("history.db-*"))

    @pytest.mark.parametrize(
        "field,value",
        [
            ("expected_target_fingerprint", SHA_A),
            ("expected_schema_version", "002"),
            ("expected_batch_id", SHA_A),
            ("expected_source_sha256", SHA_B),
            ("expected_manifest_sha256", SHA_C),
            ("expected_raw_row_count", 999),
            ("expected_sample_count", 999),
            ("expected_operating_cycle_count", 999),
        ],
    )
    def test_wrong_handoff_identity_hash_or_count_is_read_only(
        self,
        attested_dir,
        field,
        value,
    ):
        path = Path(attested_dir.path) / "history.db"
        fingerprint, prepared = _stage_database(path)
        before = path.read_bytes()
        with pytest.raises((LocalWriteGuardError, ValueError, RuntimeError)):
            self._call(path, fingerprint, prepared, **{field: value})
        assert path.read_bytes() == before

    def test_non_staged_batch_is_rejected_without_new_writes(self, attested_dir):
        path = Path(attested_dir.path) / "history.db"
        fingerprint, prepared = _stage_database(path)
        SQLiteHistoricalRepositoryV1(path).activate_batch(
            asset_id="forzy-motor-01",
            batch_id=prepared.batch_id,
            expected_active_batch_id=None,
        )
        before = path.read_bytes()
        with pytest.raises((LocalWriteGuardError, ValueError, RuntimeError)):
            self._call(path, fingerprint, prepared)
        assert path.read_bytes() == before

    def test_any_active_batch_is_rejected_when_required(self, attested_dir):
        path = Path(attested_dir.path) / "history.db"
        fingerprint = _create_migrated_database(path)
        active = synthetic_prepared_batch(0)
        staged = synthetic_prepared_batch(1)
        repository = SQLiteHistoricalRepositoryV1(path)
        repository.stage_batch(active)
        repository.activate_batch(
            asset_id="forzy-motor-01",
            batch_id=active.batch_id,
            expected_active_batch_id=None,
        )
        repository.stage_batch(staged)
        before = path.read_bytes()
        with pytest.raises((LocalWriteGuardError, ValueError, RuntimeError)):
            self._call(path, fingerprint, staged)
        assert path.read_bytes() == before

    @pytest.mark.parametrize(
        "statement",
        [
            "UPDATE historical_raw_rows_v1 SET row_sha256='sha256:' || printf('%064d', 0) WHERE record_ordinal=1",
            "UPDATE historical_raw_rows_v1 SET canonical_values_json='{}' WHERE record_ordinal=1",
            "UPDATE historical_import_batches_v1 SET raw_row_count=999",
            "UPDATE historical_import_batches_v1 SET manifest_json=manifest_json || ' '",
        ],
    )
    def test_malformed_rows_and_reconstruction_divergence_fail_read_only(
        self,
        attested_dir,
        statement,
    ):
        path = Path(attested_dir.path) / "history.db"
        fingerprint, prepared = _stage_database(path)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(statement)
            connection.commit()
        before = path.read_bytes()
        with pytest.raises((LocalWriteGuardError, ValueError, RuntimeError)):
            self._call(path, fingerprint, prepared)
        assert path.read_bytes() == before

    def test_replaced_target_is_rejected_before_query(self, attested_dir):
        path = Path(attested_dir.path) / "history.db"
        fingerprint, prepared = _stage_database(path)
        replacement = Path(attested_dir.path) / "replacement.db"
        sqlite3.connect(replacement).close()
        os.replace(replacement, path)
        with pytest.raises((LocalWriteGuardError, ValueError, RuntimeError)):
            self._call(path, fingerprint, prepared)


@requires_guard
@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor-bound SQLite proof")
def test_posix_open_rejects_aba_with_expected_identity_decoy_before_any_sql(
    attested_dir,
    monkeypatch,
):
    """Catches a decoy FD satisfying an existential opened-file identity check."""

    expected = Path(attested_dir.path) / "expected.sqlite3"
    substituted = Path(attested_dir.path) / "substituted.sqlite3"
    with closing(sqlite3.connect(expected)) as connection:
        connection.execute("CREATE TABLE marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker(value) VALUES ('expected')")
        connection.commit()
    with closing(sqlite3.connect(substituted)) as connection:
        connection.execute("CREATE TABLE marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker(value) VALUES ('substituted')")
        connection.commit()
    expected_before = expected.read_bytes()
    substituted_before = substituted.read_bytes()
    permit = attest_local_database(
        expected,
        expected_schema_version=SCHEMA_VERSION,
        temp_permit=attested_dir,
        require_existing=True,
    )
    real_connect = guard_module.sqlite3.connect
    executed: list[str] = []
    decoy_descriptors: list[int] = []
    opened_connections: list[sqlite3.Connection] = []

    class RecordingConnection(sqlite3.Connection):
        def execute(self, statement, parameters=(), /, *args, **kwargs):
            executed.append(str(statement))
            return super().execute(statement, parameters, *args, **kwargs)

    def racing_connect(database, *args, **kwargs):
        moved_expected = expected.with_name("expected-original.sqlite3")
        expected.rename(moved_expected)
        substituted.rename(expected)
        try:
            kwargs["factory"] = RecordingConnection
            connection = real_connect(database, *args, **kwargs)
            opened_connections.append(connection)
        finally:
            expected.rename(substituted)
            moved_expected.rename(expected)
        decoy_descriptors.append(os.open(expected, os.O_RDONLY))
        return connection

    monkeypatch.setattr(guard_module.sqlite3, "connect", racing_connect)
    returned = None
    try:
        with pytest.raises(LocalWriteGuardError):
            returned = guard_module._open_attested_sqlite_connection(permit)
        assert executed == []
        assert expected.read_bytes() == expected_before
        assert substituted.read_bytes() == substituted_before
    finally:
        if returned is not None:
            returned.close()
        for connection in opened_connections:
            try:
                connection.close()
            except sqlite3.Error:
                pass
        for descriptor in decoy_descriptors:
            os.close(descriptor)


class _RecordingWin32Call:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


@requires_guard
@pytest.mark.skipif(os.name != "nt", reason="Win32 CreateFileW contract")
def test_windows_directory_pin_requests_no_delete_access(attested_dir, monkeypatch):
    """Catches DELETE desired access on a compatibility-sensitive directory pin."""

    import ctypes

    create_file = _RecordingWin32Call(4321)
    close_handle = _RecordingWin32Call(1)
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(
            kernel32=SimpleNamespace(
                CreateFileW=create_file,
                CloseHandle=close_handle,
            )
        ),
    )
    handle = guard_module._pin_windows_directory(Path(attested_dir.path))
    try:
        assert len(create_file.calls) == 1
        call = create_file.calls[0]
        assert call[1] == 0x1 | 0x80
        assert call[1] & 0x10000 == 0
        assert call[2] == 0x1 | 0x2
        assert call[4] == 3
        assert call[5] == 0x02000000 | 0x00200000
    finally:
        guard_module._close_windows_handle(handle)
