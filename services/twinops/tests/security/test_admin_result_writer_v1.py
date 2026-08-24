from __future__ import annotations

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
    def test_creates_only_exact_result_directory_chain(self, isolated_worktree):
        destination = _allowed(isolated_worktree)
        AdminResultWriterV1(destination).write({"ok": True})
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
            AdminResultWriterV1(destination).write({"ok": True})
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
            AdminResultWriterV1(destination).write({"ok": True})
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
            AdminResultWriterV1(destination).write({"ok": True})
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
            AdminResultWriterV1(destination).write({"ok": True})
        assert external.read_bytes() == b"external\n"

    def test_rejects_non_regular_existing_destination(self, isolated_worktree):
        destination = _allowed(isolated_worktree)
        destination.mkdir(parents=True)
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write({"ok": True})


@requires_writer
class TestCanonicalBytesAndAtomicity:
    def test_writes_compact_sorted_utf8_json_plus_one_lf(self, isolated_worktree):
        destination = _allowed(isolated_worktree)
        result = {"z": "ação", "a": 1, "nested": {"b": False, "a": None}}
        written = AdminResultWriterV1(destination).write(result)
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
        assert written == expected
        assert canonical_admin_result_bytes(result) == expected
        assert destination.read_bytes() == expected

    def test_canonical_bytes_are_stable_across_mapping_order(self, isolated_worktree):
        left = {"command": "show-active", "environment": "local", "count": 0}
        right = {"count": 0, "environment": "local", "command": "show-active"}
        assert canonical_admin_result_bytes(left) == canonical_admin_result_bytes(right)

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), {1, 2}, b"payload"])
    def test_unserializable_or_noncanonical_values_create_no_file(
        self,
        isolated_worktree,
        value,
    ):
        destination = _allowed(isolated_worktree)
        with pytest.raises((AdminResultWriterError, TypeError, ValueError)):
            AdminResultWriterV1(destination).write({"value": value})
        assert not destination.exists()
        assert _private_temps(isolated_worktree) == []

    def test_preexisting_regular_result_is_atomically_replaced(self, isolated_worktree):
        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'{"old":true}\n')
        expected = canonical_admin_result_bytes({"new": True})
        AdminResultWriterV1(destination).write({"new": True})
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

        def fail_replace(source, target):
            raise OSError("replace denied")

        monkeypatch.setattr(writer_module.os, "replace", fail_replace)
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write({"new": True})
        assert destination.read_bytes() == b'{"old":true}\n'
        assert unrelated.read_bytes() == b"keep"
        assert _private_temps(isolated_worktree) == []

    def test_flush_or_fsync_failure_leaves_no_new_result(self, isolated_worktree, monkeypatch):
        destination = _allowed(isolated_worktree)

        def fail_fsync(fd):
            raise OSError("fsync denied")

        monkeypatch.setattr(writer_module.os, "fsync", fail_fsync)
        with pytest.raises(AdminResultWriterError):
            AdminResultWriterV1(destination).write({"new": True})
        assert not destination.exists()
        assert _private_temps(isolated_worktree) == []

    def test_private_temp_uses_exclusive_create(self, isolated_worktree, monkeypatch):
        destination = _allowed(isolated_worktree)
        destination.parent.mkdir(parents=True)
        real_open = writer_module.os.open
        observed_flags = []

        def recording_open(path, flags, *args, **kwargs):
            if Path(path).parent == destination.parent and Path(path) != destination:
                observed_flags.append(flags)
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(writer_module.os, "open", recording_open)
        AdminResultWriterV1(destination).write({"ok": True})
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
        AdminResultWriterV1(destination).write({"ok": True})
        assert len(fsynced) >= 2 or os.name == "nt"


@requires_writer
class TestReplacementRaces:
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
            AdminResultWriterV1(destination).write({"new": True})
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

        def racing_replace(source, target):
            original_root.rename(moved_root)
            original_root.mkdir()
            return real_replace(source, target)

        monkeypatch.setattr(writer_module.os, "replace", racing_replace)
        try:
            with pytest.raises(AdminResultWriterError):
                AdminResultWriterV1(destination).write({"new": True})
            assert not destination.exists()
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
            writer.write({"ok": True})
        assert not destination.exists()
