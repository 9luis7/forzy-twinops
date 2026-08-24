"""Canonical, fail-closed result publication for history administration."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
import secrets
import stat as stat_module


_CHECKED_IN_LAUNCHER = Path(__file__).resolve().parents[5] / "scripts" / "history_admin.py"
_RESULT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json$")
_REPARSE_ATTRIBUTE = 0x400


class AdminResultWriterError(RuntimeError):
    """Raised without filesystem details when result publication fails."""


def _identity(value: os.stat_result) -> tuple[int, int]:
    return (int(value.st_dev), int(value.st_ino))


def _is_windows_reparse_point(path: Path, value: os.stat_result) -> bool:
    del path
    return bool(getattr(value, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE)


def _lstat_regular(path: Path, *, directory: bool) -> os.stat_result:
    try:
        value = os.lstat(path)
    except OSError as exc:
        raise AdminResultWriterError("result path attestation failed") from exc
    if stat_module.S_ISLNK(value.st_mode) or _is_windows_reparse_point(path, value):
        raise AdminResultWriterError("result path contains a link or reparse point")
    expected = stat_module.S_ISDIR if directory else stat_module.S_ISREG
    if not expected(value.st_mode):
        raise AdminResultWriterError("result path has an invalid file type")
    return value


def _attest_absolute_chain(endpoint: Path, *, final_directory: bool) -> None:
    endpoint = endpoint.absolute()
    anchor = Path(endpoint.anchor)
    current = anchor
    for component in endpoint.parts[1:]:
        current = current / component
        value = _lstat_regular(
            current,
            directory=(current != endpoint or final_directory),
        )
        if os.path.ismount(current) and current != anchor:
            raise AdminResultWriterError("result path contains a mount point")


def canonical_admin_result_bytes(result: Mapping[str, object]) -> bytes:
    if not isinstance(result, Mapping):
        raise ValueError("admin result must be a mapping")
    if any(not isinstance(key, str) for key in result):
        raise ValueError("admin result keys must be strings")
    try:
        encoded = json.dumps(
            dict(result),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("admin result is not canonical JSON") from exc
    parsed = json.loads(encoded)
    if not isinstance(parsed, dict) or set(parsed) != set(result):
        raise ValueError("admin result is not a flat-keyed JSON object")
    return encoded + b"\n"


class AdminResultWriterV1:
    def __init__(self, result_path: Path) -> None:
        candidate = Path(result_path)
        if not candidate.is_absolute() or ".." in candidate.parts:
            raise AdminResultWriterError("result path must be absolute and canonical")
        launcher = Path(_CHECKED_IN_LAUNCHER)
        if (
            not launcher.is_absolute()
            or launcher.name != "history_admin.py"
            or launcher.parent.name != "scripts"
            or not launcher.is_file()
        ):
            raise AdminResultWriterError("checked-in launcher identity is invalid")
        launcher_stat = _lstat_regular(launcher, directory=False)
        worktree = launcher.parent.parent.resolve(strict=True)
        _attest_absolute_chain(launcher, final_directory=False)
        _attest_absolute_chain(worktree, final_directory=True)
        expected_root = worktree / "tmp" / "twinops-admin-results"
        expected = expected_root / candidate.name
        if (
            candidate.absolute() != expected.absolute()
            or candidate.parent.absolute() != expected_root.absolute()
            or not _RESULT_NAME_RE.fullmatch(candidate.name)
        ):
            raise AdminResultWriterError("result path is outside the fixed boundary")
        self.result_path = expected.resolve(strict=False)
        self._launcher = launcher.resolve(strict=True)
        self._launcher_identity = _identity(launcher_stat)
        self._worktree = worktree
        self._worktree_identity = _identity(_lstat_regular(worktree, directory=True))
        self._result_root = expected_root

    def _reattest_launcher_and_worktree(self) -> None:
        launcher_stat = _lstat_regular(self._launcher, directory=False)
        worktree_stat = _lstat_regular(self._worktree, directory=True)
        if (
            _identity(launcher_stat) != self._launcher_identity
            or _identity(worktree_stat) != self._worktree_identity
        ):
            raise AdminResultWriterError("launcher or worktree identity changed")

    def _ensure_result_root(self) -> tuple[int, int]:
        self._reattest_launcher_and_worktree()
        tmp = self._worktree / "tmp"
        if tmp.exists() or tmp.is_symlink():
            _lstat_regular(tmp, directory=True)
        else:
            try:
                os.mkdir(tmp)
            except FileExistsError:
                pass
            except OSError as exc:
                raise AdminResultWriterError("result directory creation failed") from exc
            _lstat_regular(tmp, directory=True)
        if self._result_root.exists() or self._result_root.is_symlink():
            root_stat = _lstat_regular(self._result_root, directory=True)
        else:
            try:
                os.mkdir(self._result_root)
            except FileExistsError:
                pass
            except OSError as exc:
                raise AdminResultWriterError("result directory creation failed") from exc
            root_stat = _lstat_regular(self._result_root, directory=True)
        try:
            self._result_root.resolve(strict=True).relative_to(
                self._worktree.resolve(strict=True)
            )
        except (OSError, ValueError) as exc:
            raise AdminResultWriterError("result directory escaped worktree") from exc
        return _identity(root_stat)

    def _destination_identity(self) -> tuple[int, int] | None:
        if not (self.result_path.exists() or self.result_path.is_symlink()):
            return None
        return _identity(_lstat_regular(self.result_path, directory=False))

    def _reattest_publication(
        self,
        root_identity: tuple[int, int],
        destination_identity: tuple[int, int] | None,
    ) -> None:
        self._reattest_launcher_and_worktree()
        root_stat = _lstat_regular(self._result_root, directory=True)
        if _identity(root_stat) != root_identity:
            raise AdminResultWriterError("result directory identity changed")
        current = self._destination_identity()
        if current != destination_identity:
            raise AdminResultWriterError("result destination identity changed")

    def _fsync_directory(self) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(self._result_root, flags)
        except OSError:
            if os.name == "nt":
                return
            raise
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def write(self, result: Mapping[str, object]) -> bytes:
        private_temp: Path | None = None
        replaced = False
        try:
            root_identity = self._ensure_result_root()
            destination_identity = self._destination_identity()
            self._reattest_publication(root_identity, destination_identity)
            payload = canonical_admin_result_bytes(result)
            self._reattest_publication(root_identity, destination_identity)

            for _ in range(16):
                private_temp = self._result_root / f".{secrets.token_hex(16)}.tmp"
                try:
                    descriptor = os.open(
                        private_temp,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                        0o600,
                    )
                    break
                except FileExistsError:
                    private_temp = None
            else:
                raise AdminResultWriterError("exclusive result temp allocation failed")

            try:
                with os.fdopen(descriptor, "wb", closefd=True) as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise

            temp_stat = _lstat_regular(private_temp, directory=False)
            if temp_stat.st_size != len(payload):
                raise AdminResultWriterError("result temp size verification failed")
            self._reattest_publication(root_identity, destination_identity)
            os.replace(private_temp, self.result_path)
            replaced = True
            private_temp = None
            published_stat = _lstat_regular(self.result_path, directory=False)
            if _identity(published_stat) != _identity(temp_stat):
                raise AdminResultWriterError("published result identity mismatch")
            if self.result_path.read_bytes() != payload:
                raise AdminResultWriterError("published result bytes mismatch")
            self._fsync_directory()
            self._reattest_launcher_and_worktree()
            root_stat = _lstat_regular(self._result_root, directory=True)
            if _identity(root_stat) != root_identity:
                raise AdminResultWriterError("result directory identity changed")
            return payload
        except AdminResultWriterError:
            raise
        except BaseException as exc:
            raise AdminResultWriterError("admin result publication failed") from exc
        finally:
            if private_temp is not None:
                try:
                    private_temp.unlink(missing_ok=True)
                except OSError:
                    pass


__all__ = (
    "AdminResultWriterError",
    "AdminResultWriterV1",
    "canonical_admin_result_bytes",
)
