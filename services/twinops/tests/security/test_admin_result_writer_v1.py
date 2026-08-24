from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

import pytest


WORKTREE_ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = (
    WORKTREE_ROOT
    / "services"
    / "twinops"
    / "src"
    / "twinops"
    / "security"
    / "admin_result_writer_v1.py"
)
WRITER_AVAILABLE = MODULE_PATH.is_file()
requires_writer = pytest.mark.skipif(
    not WRITER_AVAILABLE,
    reason="admin result writer is the intentional Task A6 RED",
)


if WRITER_AVAILABLE:
    from twinops.security import admin_result_writer_v1 as writer_module
    from twinops.security.admin_result_writer_v1 import (
        AdminResultWriterError,
        AdminResultWriterV1,
        canonical_admin_result_bytes,
    )


@pytest.fixture
def isolated_worktree(tmp_path, monkeypatch):
    root = tmp_path / "worktree"
    launcher = root / "scripts" / "history_admin.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("# checked-in launcher test double\n", encoding="utf-8")
    monkeypatch.setattr(writer_module, "_CHECKED_IN_LAUNCHER", launcher)
    return root


def _allowed(root: Path, name: str = "result.json") -> Path:
    return root / "tmp" / "twinops-admin-results" / name


def _private_temps(root: Path) -> list[Path]:
    result_root = root / "tmp" / "twinops-admin-results"
    return [] if not result_root.exists() else list(result_root.glob(".*.tmp"))


def _valid_show_result(**overrides) -> dict[str, object]:
    result: dict[str, object] = {
        "command": "show-active",
        "environment": "local",
        "targetFingerprint": "sha256:" + "1" * 64,
        "schemaVersion": "003",
        "assetId": "forzy-motor-01",
        "activeBatchId": None,
        "sourceSha256": None,
        "manifestSha256": None,
        "assessmentManifestSha256": None,
        "rawRowCount": 0,
        "sampleCount": 0,
        "operatingCycleCount": 0,
        "assessmentCount": 0,
    }
    result.update(overrides)
    return result


def _published_bytes(value) -> bytes:
    return value.canonical_bytes if hasattr(value, "canonical_bytes") else value


def _published_sha256(writer, value) -> str | None:
    return getattr(value, "sha256", getattr(writer, "last_sha256", None))


@requires_writer
class TestResultPathBoundary:
    @pytest.mark.parametrize(
        "relative",
        [
            "result.txt",
            ".json",
            "-result.json",
            "result.JSON",
            "with space.json",
            "nested/result.json",
            "../result.json",
            "result.json/child",
            ("a" * 129) + ".json",
            "semi;colon.json",
        ],
    )
    def test_rejects_wrong_name_suffix_nested_and_lexical_escape(
        self,
        isolated_worktree,
        relative,
    ):
        candidate = (
            isolated_worktree / "tmp" / "twinops-admin-results" / relative
        )
        with pytest.raises((AdminResultWriterError, ValueError)):
            AdminResultWriterV1(candidate)
        assert not candidate.is_file()

    def test_rejects_relative_result_path(self, isolated_worktree):
        with pytest.raises((AdminResultWriterError, ValueError)):
            AdminResultWriterV1(Path("result.json"))

    def test_rejects_absolute_external_result_path(self, isolated_worktree, tmp_path):
        external = tmp_path / "external.json"
        with pytest.raises((AdminResultWriterError, ValueError)):
            AdminResultWriterV1(external)
        assert not external.exists()

    def test_accepts_only_direct_child_with_frozen_name_grammar(self, isolated_worktree):
        for name in ("a.json", "A-1_2.3.json", ("z" * 128) + ".json"):
            writer = AdminResultWriterV1(_allowed(isolated_worktree, name))
            assert writer.result_path == _allowed(isolated_worktree, name).resolve()

    def test_rejects_caller_selected_root_even_with_valid_tail(self, tmp_path, isolated_worktree):
        selected = tmp_path / "chosen" / "tmp" / "twinops-admin-results" / "ok.json"
        with pytest.raises((AdminResultWriterError, ValueError)):
            AdminResultWriterV1(selected)


@requires_writer
class TestResultRootAttestation:
    def test_preflight_is_non_publishing_and_creates_no_private_temp(
        self,
        isolated_worktree,
    ):
        """Catches a boundary preflight that publishes or allocates result data."""

        destination = _allowed(isolated_worktree)
        writer = AdminResultWriterV1(destination)

        writer.preflight()

        assert destination.parent.is_dir()
        assert not destination.exists()
        assert _private_temps(isolated_worktree) == []

    def test_creates_only_exact_result_directory_chain(self, isolated_worktree):
        destination = _allowed(isolated_worktree)
        AdminResultWriterV1(destination).write(_valid_show_result())
        assert destination.is_file()
        assert destination.parent == isolated_worktree / "tmp" / "twinops-admin-results"
        assert sorted(path.name for path in isolated_worktree.iterdir()) == ["scripts", "tmp"]

    def test_rejects_symlinked_tmp_component(
        self,
        isolated_worktree,
        tmp_path,
        monkeypatch,
    ):
        external = tmp_path / "external"
        external.mkdir()
        try:
            (isolated_worktree / "tmp").symlink_to(external, target_is_directory=True)
        except OSError:
            (isolated_worktree / "tmp").mkdir()
            monkeypatch.setattr(
                writer_module,
                "_is_windows_reparse_point",
                lambda path, value: Path(path) == isolated_worktree / "tmp",
            )
        destination = _allowed(isolated_worktree)
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write(_valid_show_result())
        assert not (external / "twinops-admin-results" / "result.json").exists()

    def test_rejects_symlinked_result_root(
        self,
        isolated_worktree,
        tmp_path,
        monkeypatch,
    ):
        external = tmp_path / "external"
        external.mkdir()
        (isolated_worktree / "tmp").mkdir()
        try:
            (isolated_worktree / "tmp" / "twinops-admin-results").symlink_to(
                external,
                target_is_directory=True,
            )
        except OSError:
            (isolated_worktree / "tmp" / "twinops-admin-results").mkdir()
            monkeypatch.setattr(
                writer_module,
                "_is_windows_reparse_point",
                lambda path, value: Path(path)
                == isolated_worktree / "tmp" / "twinops-admin-results",
            )
        destination = _allowed(isolated_worktree)
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write(_valid_show_result())
        assert not (external / "result.json").exists()

    def test_mocked_reparse_result_root_is_rejected(
        self,
        isolated_worktree,
        monkeypatch,
    ):
        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        monkeypatch.setattr(
            writer_module,
            "_is_windows_reparse_point",
            lambda path, stat: Path(path) == destination.parent,
        )
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write(_valid_show_result())
        assert not destination.exists()

    def test_rejects_symlinked_existing_destination(
        self,
        isolated_worktree,
        tmp_path,
        monkeypatch,
    ):
        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        external = tmp_path / "external.json"
        external.write_bytes(b"external\n")
        try:
            destination.symlink_to(external)
        except OSError:
            destination.write_bytes(b"linked-placeholder")
            monkeypatch.setattr(
                writer_module,
                "_is_windows_reparse_point",
                lambda path, value: Path(path) == destination,
            )
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write(_valid_show_result())
        assert external.read_bytes() == b"external\n"

    def test_rejects_non_regular_existing_destination(self, isolated_worktree):
        destination = _allowed(isolated_worktree)
        destination.mkdir(parents=True)
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write(_valid_show_result())


@requires_writer
class TestCanonicalBytesAndAtomicity:
    def test_writes_compact_sorted_utf8_json_plus_one_lf(self, isolated_worktree):
        destination = _allowed(isolated_worktree)
        result = _valid_show_result()
        writer = AdminResultWriterV1(destination)
        written = writer.write(result)
        expected = (
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
        assert _published_bytes(written) == expected
        assert _published_sha256(writer, written) == (
            "sha256:" + sha256(expected).hexdigest()
        )
        assert canonical_admin_result_bytes(result) == expected
        assert destination.read_bytes() == expected

    def test_canonical_bytes_are_stable_across_mapping_order(self, isolated_worktree):
        left = _valid_show_result()
        right = dict(reversed(tuple(left.items())))
        assert canonical_admin_result_bytes(left) == canonical_admin_result_bytes(right)

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), {1, 2}, b"payload"])
    def test_unserializable_or_noncanonical_values_create_no_file(
        self,
        isolated_worktree,
        value,
    ):
        destination = _allowed(isolated_worktree)
        invalid = _valid_show_result(rawRowCount=value)
        with pytest.raises((AdminResultWriterError, TypeError, ValueError)):
            AdminResultWriterV1(destination).write(invalid)
        assert not destination.exists()
        assert _private_temps(isolated_worktree) == []

    def test_preexisting_regular_result_is_atomically_replaced(self, isolated_worktree):
        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'{"old":true}\n')
        expected = canonical_admin_result_bytes(_valid_show_result())
        AdminResultWriterV1(destination).write(_valid_show_result())
        assert destination.read_bytes() == expected
        assert _private_temps(isolated_worktree) == []

    def test_replace_failure_preserves_old_file_and_removes_only_private_temp(
        self,
        isolated_worktree,
        monkeypatch,
    ):
        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'{"old":true}\n')
        unrelated = destination.parent / "unrelated.tmp"
        unrelated.write_bytes(b"keep")

        def fail_replace(source, target, *args, **kwargs):
            del source, target, args, kwargs
            raise OSError("replace denied")

        monkeypatch.setattr(writer_module.os, "replace", fail_replace)
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write(_valid_show_result())
        assert destination.read_bytes() == b'{"old":true}\n'
        assert unrelated.read_bytes() == b"keep"
        assert _private_temps(isolated_worktree) == []

    def test_flush_or_fsync_failure_leaves_no_new_result(self, isolated_worktree, monkeypatch):
        destination = _allowed(isolated_worktree)

        def fail_fsync(fd):
            raise OSError("fsync denied")

        monkeypatch.setattr(writer_module.os, "fsync", fail_fsync)
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write(_valid_show_result())
        assert not destination.exists()
        assert _private_temps(isolated_worktree) == []

    def test_private_temp_uses_exclusive_create(self, isolated_worktree, monkeypatch):
        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        real_open = writer_module.os.open
        observed_flags = []

        def recording_open(path, flags, *args, **kwargs):
            candidate = Path(path)
            if (
                kwargs.get("dir_fd") is not None
                or (
                    candidate.parent == destination.parent
                    and candidate != destination
                )
            ):
                observed_flags.append(flags)
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(writer_module.os, "open", recording_open)
        AdminResultWriterV1(destination).write(_valid_show_result())
        assert observed_flags
        assert all(flags & os.O_CREAT and flags & os.O_EXCL for flags in observed_flags)

    def test_result_directory_is_fsynced_where_supported(self, isolated_worktree, monkeypatch):
        destination = _allowed(isolated_worktree)
        real_fsync = writer_module.os.fsync
        fsynced = []

        def recording_fsync(fd):
            fsynced.append(fd)
            return real_fsync(fd)

        monkeypatch.setattr(writer_module.os, "fsync", recording_fsync)
        AdminResultWriterV1(destination).write(_valid_show_result())
        assert len(fsynced) >= 2 or os.name == "nt"


@requires_writer
class TestStrictCommandModels:
    @pytest.mark.parametrize(
        "mutation",
        [
            {"command": "unknown-command"},
            {"extra": "unknown-key"},
            {"assetId": {"nested": "value"}},
            {"assetId": b"model bytes"},
            {"assetId": str(Path.cwd().resolve())},
            {"environment": "postgresql://user:pass@host/database"},
            {"environment": "staging"},
            {"targetFingerprint": "sha256:" + "A" * 64},
            {"schemaVersion": "3"},
            {"rawRowCount": True},
            {"sampleCount": -1},
            {"activeBatchId": None, "sourceSha256": "sha256:" + "2" * 64},
            {"activeBatchId": None, "rawRowCount": 1},
            {
                "activeBatchId": "sha256:" + "3" * 64,
                "sourceSha256": None,
                "manifestSha256": None,
                "rawRowCount": 1,
                "sampleCount": 2,
                "operatingCycleCount": 1,
            },
            {"assessmentManifestSha256": None, "assessmentCount": 1},
        ],
        ids=(
            "unknown-command",
            "unknown-key",
            "nested-value",
            "bytes-value",
            "absolute-path-value",
            "dsn-value",
            "environment-literal",
            "noncanonical-hash",
            "schema-literal",
            "boolean-count",
            "negative-count",
            "null-batch-with-hash",
            "null-batch-with-count",
            "batch-with-null-hashes",
            "assessment-count-with-null-hash",
        ),
    )
    def test_writer_rejects_invalid_flat_command_result_before_publication(
        self,
        isolated_worktree,
        mutation,
    ):
        """Catches permissive JSON serialization bypassing the frozen result model."""

        destination = _allowed(isolated_worktree)
        invalid = _valid_show_result(**mutation)

        with pytest.raises((AdminResultWriterError, TypeError, ValueError)):
            AdminResultWriterV1(destination).write(invalid)

        assert not destination.exists()
        assert _private_temps(isolated_worktree) == []


@requires_writer
class TestReplacementRaces:
    def test_final_reattest_root_swap_cannot_publish_controlled_same_name_temp(
        self,
        isolated_worktree,
        monkeypatch,
    ):
        """Catches path-based replace crossing into a post-reattest replacement root."""

        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        old_bytes = b'{"old":true}\n'
        external_bytes = b'{"external":true}\n'
        controlled_bytes = b'{"controlled-temp":true}\n'
        destination.write_bytes(old_bytes)
        original_root = destination.parent
        moved_root = original_root.with_name("twinops-admin-results-owned-moved")
        external_root = isolated_worktree.parent / "controlled-external-result-root"
        external_root.mkdir()
        (external_root / destination.name).write_bytes(external_bytes)
        real_replace = writer_module.os.replace
        attempted = False
        moved = False
        private_name = None

        def replace_after_root_swap(source, target, *args, **kwargs):
            nonlocal attempted, moved, private_name
            attempted = True
            private_name = Path(source).name
            original_root.rename(moved_root)
            (external_root / private_name).write_bytes(controlled_bytes)
            external_root.rename(original_root)
            moved = True
            return real_replace(source, target, *args, **kwargs)

        monkeypatch.setattr(writer_module.os, "replace", replace_after_root_swap)
        try:
            with pytest.raises(AdminResultWriterError):
                AdminResultWriterV1(destination).write(_valid_show_result())

            assert attempted is True
            owned_root = moved_root if moved else original_root
            external_boundary = original_root if moved else external_root
            assert (owned_root / destination.name).read_bytes() == old_bytes
            assert (external_boundary / destination.name).read_bytes() == external_bytes
            if moved:
                assert private_name is not None
                assert (external_boundary / private_name).read_bytes() == controlled_bytes
            assert list(owned_root.glob(".*.tmp")) == []
        finally:
            if original_root.exists():
                shutil.rmtree(original_root)
            if moved_root.exists():
                moved_root.rename(original_root)
            if external_root.exists():
                shutil.rmtree(external_root)

    def test_destination_replaced_after_preflight_is_rejected(
        self,
        isolated_worktree,
        monkeypatch,
    ):
        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'{"old":true}\n')
        real_reattest = writer_module.AdminResultWriterV1._reattest_publication
        calls = 0

        def racing_reattest(writer, root_identity, destination_identity):
            nonlocal calls
            calls += 1
            if calls == 3:
                destination.unlink()
                destination.write_bytes(b'{"racer":true}\n')
            return real_reattest(writer, root_identity, destination_identity)

        monkeypatch.setattr(
            writer_module.AdminResultWriterV1,
            "_reattest_publication",
            racing_reattest,
        )
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write(_valid_show_result())
        assert destination.read_bytes() == b'{"racer":true}\n'
        assert _private_temps(isolated_worktree) == []

    def test_result_root_replaced_before_atomic_replace_is_rejected(
        self,
        isolated_worktree,
        monkeypatch,
    ):
        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        original_root = destination.parent
        moved_root = original_root.with_name("twinops-admin-results-old")
        real_replace = writer_module.os.replace

        def racing_replace(source, target, *args, **kwargs):
            original_root.rename(moved_root)
            original_root.mkdir()
            return real_replace(source, target, *args, **kwargs)

        monkeypatch.setattr(writer_module.os, "replace", racing_replace)
        try:
            with pytest.raises(AdminResultWriterError):
                AdminResultWriterV1(destination).write(_valid_show_result())
            assert not destination.exists()
            assert not list(moved_root.glob(".*.tmp"))
        finally:
            if original_root.exists():
                shutil.rmtree(original_root)
            if moved_root.exists():
                moved_root.rename(original_root)

    def test_private_temp_substitution_preserves_old_destination(
        self,
        isolated_worktree,
        monkeypatch,
    ):
        """Catches path-based replace publishing a substituted private temp inode."""

        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        old_bytes = b'{"old":true}\n'
        destination.write_bytes(old_bytes)
        real_replace = writer_module.os.replace
        substituted = False

        def substitute_private_temp(source, target, *args, **kwargs):
            nonlocal substituted
            source_path = Path(source)
            if not source_path.is_absolute():
                source_path = destination.parent / source_path
            if source_path.name.startswith(".") and source_path.suffix == ".tmp":
                source_path.unlink()
                source_path.write_bytes(b'{"attacker":true}\n')
                substituted = True
            return real_replace(source, target, *args, **kwargs)

        monkeypatch.setattr(writer_module.os, "replace", substitute_private_temp)

        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write(_valid_show_result())

        assert substituted is True
        assert destination.read_bytes() == old_bytes
        assert _private_temps(isolated_worktree) == []

    def test_moved_root_reparse_race_preserves_old_result_and_cleans_temp(
        self,
        isolated_worktree,
        monkeypatch,
    ):
        """Catches publication following a moved root into a replacement reparse root."""

        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        old_bytes = b'{"old":true}\n'
        destination.write_bytes(old_bytes)
        original_root = destination.parent
        moved_root = original_root.with_name("twinops-admin-results-pinned-old")
        real_replace = writer_module.os.replace
        moved = False

        def move_then_mark_reparse(source, target, *args, **kwargs):
            nonlocal moved
            original_root.rename(moved_root)
            original_root.mkdir()
            moved = True
            return real_replace(source, target, *args, **kwargs)

        real_reparse = writer_module._is_windows_reparse_point
        monkeypatch.setattr(writer_module.os, "replace", move_then_mark_reparse)
        monkeypatch.setattr(
            writer_module,
            "_is_windows_reparse_point",
            lambda path, value: (
                (moved and Path(path) == original_root)
                or real_reparse(path, value)
            ),
        )
        try:
            with pytest.raises(AdminResultWriterError):
                AdminResultWriterV1(destination).write(_valid_show_result())
            if moved:
                assert not destination.exists()
                assert (moved_root / destination.name).read_bytes() == old_bytes
                assert not list(moved_root.glob(".*.tmp"))
            else:
                assert destination.read_bytes() == old_bytes
                assert _private_temps(isolated_worktree) == []
        finally:
            if original_root.exists():
                shutil.rmtree(original_root)
            if moved_root.exists():
                moved_root.rename(original_root)

    def test_launcher_or_worktree_identity_change_fails_closed(
        self,
        isolated_worktree,
    ):
        destination = _allowed(isolated_worktree)
        writer = AdminResultWriterV1(destination)
        launcher = isolated_worktree / "scripts" / "history_admin.py"
        moved = launcher.with_suffix(".old")
        launcher.rename(moved)
        launcher.write_text("# replacement\n", encoding="utf-8")
        with pytest.raises(AdminResultWriterError):
            writer.write(_valid_show_result())
        assert not destination.exists()
