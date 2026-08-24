"""Fail-closed local SQLite path and staged-handoff attestation."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PureWindowsPath
import re
import secrets
import shutil
import sqlite3
import stat as stat_module
import tempfile
from types import MappingProxyType
from urllib.parse import quote
from weakref import WeakKeyDictionary

from twinops.storage.schema_migrations import (
    registered_migration_specs,
    verify_schema_version,
)


_CHECKED_IN_LAUNCHER = Path(__file__).resolve().parents[5] / "scripts" / "history_admin.py"
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^[0-9]{3}$")
_REPARSE_ATTRIBUTE = 0x400
_SQLITE_CONNECTION_ATTESTATION = object()


class LocalWriteGuardError(RuntimeError):
    """Raised without path-bearing details when local attestation fails."""


class _GuardedSQLiteConnection(sqlite3.Connection):
    """SQLite connection carrying an unexported exact-open attestation."""


class AttestedTempDirectoryV1:
    """Opaque process-local capability for one freshly-created temp root."""

    __slots__ = ("path", "__weakref__")

    path: Path

    def __init__(self, path: Path) -> None:
        object.__setattr__(self, "path", Path(path))

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("attested temp capability is immutable")

    def __repr__(self) -> str:
        return "AttestedTempDirectoryV1(<opaque>)"

    def __copy__(self):
        return type(self)(self.path)

    def __reduce__(self):
        raise TypeError("attested temp capability is not serializable")

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("attested temp capability is not serializable")


class LocalDatabasePermitV1:
    """Opaque process-local authorization bound to attested filesystem state."""

    __slots__ = (
        "path",
        "expected_schema_version",
        "target_fingerprint",
        "root",
        "root_identity",
        "parent_identity",
        "target_identity",
        "creator_pid",
        "__weakref__",
    )

    def __init__(
        self,
        *,
        path: Path,
        expected_schema_version: str,
        target_fingerprint: str,
        root: Path,
        root_identity: tuple[int, int],
        parent_identity: tuple[int, int],
        target_identity: tuple[int, int] | None,
        creator_pid: int,
    ) -> None:
        for name, value in (
            ("path", Path(path)),
            ("expected_schema_version", expected_schema_version),
            ("target_fingerprint", target_fingerprint),
            ("root", Path(root)),
            ("root_identity", root_identity),
            ("parent_identity", parent_identity),
            ("target_identity", target_identity),
            ("creator_pid", creator_pid),
        ):
            object.__setattr__(self, name, value)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("local database capability is immutable")

    def __repr__(self) -> str:
        return "LocalDatabasePermitV1(<opaque>)"

    def __copy__(self):
        return type(self)(
            path=self.path,
            expected_schema_version=self.expected_schema_version,
            target_fingerprint=self.target_fingerprint,
            root=self.root,
            root_identity=self.root_identity,
            parent_identity=self.parent_identity,
            target_identity=self.target_identity,
            creator_pid=self.creator_pid,
        )

    def __reduce__(self):
        raise TypeError("local database capability is not serializable")

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("local database capability is not serializable")


_TempRecord = tuple[str, int, Path, tuple[int, int]]
_DatabaseRecord = tuple[str, int, AttestedTempDirectoryV1 | None]
_TEMP_PERMITS: WeakKeyDictionary[AttestedTempDirectoryV1, _TempRecord] = (
    WeakKeyDictionary()
)
_DATABASE_PERMITS: WeakKeyDictionary[LocalDatabasePermitV1, _DatabaseRecord] = (
    WeakKeyDictionary()
)


def _identity(value: os.stat_result) -> tuple[int, int]:
    return (int(value.st_dev), int(value.st_ino))


def _is_windows_reparse_point(path: Path, value: os.stat_result) -> bool:
    del path
    return bool(getattr(value, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE)


def _guarded_lstat(path: Path) -> os.stat_result:
    try:
        value = os.lstat(path)
    except OSError as exc:
        raise LocalWriteGuardError("local path attestation failed") from exc
    if stat_module.S_ISLNK(value.st_mode) or _is_windows_reparse_point(path, value):
        raise LocalWriteGuardError("local path contains a link or reparse point")
    return value


def _attest_absolute_chain(endpoint: Path, *, final_directory: bool) -> None:
    endpoint = endpoint.absolute()
    anchor = Path(endpoint.anchor)
    current = anchor
    for component in endpoint.parts[1:]:
        current = current / component
        value = _guarded_lstat(current)
        is_final = current == endpoint
        if os.path.ismount(current) and current != anchor:
            raise LocalWriteGuardError("local path contains a mount point")
        if (not is_final or final_directory) and not stat_module.S_ISDIR(value.st_mode):
            raise LocalWriteGuardError("local path parent is not a directory")
        if is_final and not final_directory and not stat_module.S_ISREG(value.st_mode):
            raise LocalWriteGuardError("checked-in launcher is not regular")


def _launcher_worktree_root() -> Path:
    launcher = _CHECKED_IN_LAUNCHER
    if not launcher.is_absolute():
        raise LocalWriteGuardError("checked-in launcher identity is invalid")
    expected = launcher.parent.parent
    if launcher.name != "history_admin.py" or launcher.parent.name != "scripts":
        raise LocalWriteGuardError("checked-in launcher identity is invalid")
    if not expected.is_dir():
        raise LocalWriteGuardError("worktree root is unavailable")
    _attest_absolute_chain(launcher, final_directory=False)
    _attest_absolute_chain(expected, final_directory=True)
    return expected.resolve(strict=True)


def _validate_path_grammar(path: Path) -> Path:
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise LocalWriteGuardError("local database path is invalid")
    windows = PureWindowsPath(raw)
    normalized_windows = raw.replace("\\", "/")
    if normalized_windows.startswith("//"):
        raise LocalWriteGuardError("UNC and device paths are forbidden")
    if windows.drive and not windows.root:
        raise LocalWriteGuardError("drive-relative paths are forbidden")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise LocalWriteGuardError("local database path must be absolute")
    if candidate == Path(candidate.anchor):
        raise LocalWriteGuardError("volume roots are forbidden")
    if ".." in candidate.parts:
        raise LocalWriteGuardError("lexical parent traversal is forbidden")
    return candidate


def _walk_existing(root: Path, endpoint: Path) -> None:
    root = root.absolute()
    endpoint = endpoint.absolute()
    try:
        relative = endpoint.relative_to(root)
    except ValueError as exc:
        raise LocalWriteGuardError("local path escapes the allowed root") from exc

    root_stat = _guarded_lstat(root)
    if not stat_module.S_ISDIR(root_stat.st_mode):
        raise LocalWriteGuardError("allowed root is not a directory")
    current = root
    for component in relative.parts:
        current = current / component
        if not current.exists() and not current.is_symlink():
            break
        value = _guarded_lstat(current)
        if os.path.ismount(current) and current != root:
            raise LocalWriteGuardError("local path contains a mount point")
        if current != endpoint and not stat_module.S_ISDIR(value.st_mode):
            raise LocalWriteGuardError("local path parent is not a directory")


def _canonical_contained(path: Path, root: Path) -> Path:
    try:
        canonical_root = root.resolve(strict=True)
        canonical = path.resolve(strict=False)
        canonical.relative_to(canonical_root)
    except (OSError, ValueError) as exc:
        raise LocalWriteGuardError("local path escapes the allowed root") from exc
    return canonical


def _registered_temp_permit(permit: AttestedTempDirectoryV1) -> tuple[Path, tuple[int, int]]:
    if not isinstance(permit, AttestedTempDirectoryV1):
        raise LocalWriteGuardError("temporary directory permit is forged or stale")
    record = _TEMP_PERMITS.get(permit)
    if record is None:
        raise LocalWriteGuardError("temporary directory permit is forged or stale")
    _secret, creator_pid, root, expected_identity = record
    if (
        root != permit.path
        or creator_pid != os.getpid()
    ):
        raise LocalWriteGuardError("temporary directory permit is forged or stale")
    value = _guarded_lstat(root)
    if not stat_module.S_ISDIR(value.st_mode) or _identity(value) != expected_identity:
        raise LocalWriteGuardError("temporary directory identity changed")
    return root, expected_identity


def _automatic_temp_permit(
    path: Path,
) -> tuple[AttestedTempDirectoryV1, Path, tuple[int, int]] | None:
    for permit, (_secret, creator_pid, root, identity) in tuple(
        _TEMP_PERMITS.items()
    ):
        if creator_pid != os.getpid():
            continue
        try:
            path.absolute().relative_to(root.absolute())
        except ValueError:
            continue
        value = _guarded_lstat(root)
        if _identity(value) != identity:
            raise LocalWriteGuardError("temporary directory identity changed")
        return permit, root, identity
    return None


def create_attested_temp_dir() -> AttestedTempDirectoryV1:
    root = Path(tempfile.mkdtemp(prefix="twinops-history-admin-"))
    value = _guarded_lstat(root)
    permit = AttestedTempDirectoryV1(root.resolve(strict=True))
    _TEMP_PERMITS[permit] = (
        secrets.token_hex(32),
        os.getpid(),
        permit.path,
        _identity(value),
    )
    return permit


def remove_attested_temp_dir(permit: AttestedTempDirectoryV1) -> None:
    root, expected_identity = _registered_temp_permit(permit)
    value = _guarded_lstat(root)
    if _identity(value) != expected_identity:
        raise LocalWriteGuardError("temporary directory identity changed")
    shutil.rmtree(root)
    _TEMP_PERMITS.pop(permit, None)


def _validated_migration_hashes(migration_hashes) -> dict[str, str]:
    if not migration_hashes:
        raise ValueError("migration hash map must not be empty")
    result: dict[str, str] = {}
    for version, digest in migration_hashes.items():
        if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
            raise ValueError("migration version is invalid")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ValueError("migration hash is invalid")
        result[version] = digest
    return dict(sorted(result.items()))


def compute_local_target_fingerprint(
    path: Path,
    *,
    expected_schema_version: str,
    migration_hashes,
) -> str:
    candidate = _validate_path_grammar(Path(path))
    if not _VERSION_RE.fullmatch(expected_schema_version):
        raise ValueError("expected schema version is invalid")
    hashes = _validated_migration_hashes(migration_hashes)
    payload = {
        "kind": "local-sqlite",
        "migrationHashes": hashes,
        "path": os.path.normcase(str(candidate.resolve(strict=False))),
        "schemaVersion": expected_schema_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + sha256(canonical).hexdigest()


def _registered_hashes() -> MappingProxyType:
    return MappingProxyType(
        {
            spec.version: spec.sqlite_sha256
            for spec in registered_migration_specs()
        }
    )


def _allowed_root(
    path: Path,
    temp_permit: AttestedTempDirectoryV1 | None,
) -> tuple[Path, tuple[int, int], AttestedTempDirectoryV1 | None]:
    if temp_permit is not None:
        root, root_identity = _registered_temp_permit(temp_permit)
        return root, root_identity, temp_permit
    worktree = _launcher_worktree_root()
    try:
        path.absolute().relative_to(worktree.absolute())
        return worktree, _identity(_guarded_lstat(worktree)), None
    except ValueError:
        automatic = _automatic_temp_permit(path)
        if automatic is None:
            raise LocalWriteGuardError("local path is outside an allowed root")
        permit, root, root_identity = automatic
        return root, root_identity, permit


def _attest(
    path: Path,
    *,
    expected_schema_version: str,
    temp_permit: AttestedTempDirectoryV1 | None,
    require_existing: bool,
) -> LocalDatabasePermitV1:
    candidate = _validate_path_grammar(Path(path))
    if not _VERSION_RE.fullmatch(expected_schema_version):
        raise ValueError("expected schema version is invalid")
    root, root_identity, owning_temp_permit = _allowed_root(candidate, temp_permit)
    canonical = _canonical_contained(candidate, root)
    parent = canonical.parent
    if not parent.exists():
        raise LocalWriteGuardError("local database parent does not exist")
    _walk_existing(root, canonical)
    parent_stat = _guarded_lstat(parent)
    if not stat_module.S_ISDIR(parent_stat.st_mode):
        raise LocalWriteGuardError("local database parent is not a directory")

    target_identity = None
    target_exists = canonical.exists() or canonical.is_symlink()
    if require_existing and not target_exists:
        raise LocalWriteGuardError("local database does not exist")
    if not require_existing and target_exists:
        raise LocalWriteGuardError("local database already exists")
    if target_exists:
        target_stat = _guarded_lstat(canonical)
        if (
            not stat_module.S_ISREG(target_stat.st_mode)
            or int(target_stat.st_nlink) != 1
        ):
            raise LocalWriteGuardError("local database is not a regular file")
        target_identity = _identity(target_stat)

    fingerprint = compute_local_target_fingerprint(
        canonical,
        expected_schema_version=expected_schema_version,
        migration_hashes=_registered_hashes(),
    )
    permit = LocalDatabasePermitV1(
        path=canonical,
        expected_schema_version=expected_schema_version,
        target_fingerprint=fingerprint,
        root=root.resolve(strict=True),
        root_identity=root_identity,
        parent_identity=_identity(parent_stat),
        target_identity=target_identity,
        creator_pid=os.getpid(),
    )
    _DATABASE_PERMITS[permit] = (
        secrets.token_hex(32),
        os.getpid(),
        owning_temp_permit,
    )
    return permit


def attest_local_database(
    path: Path,
    *,
    expected_schema_version: str,
    temp_permit: AttestedTempDirectoryV1 | None = None,
    require_existing: bool = True,
) -> LocalDatabasePermitV1:
    return _attest(
        path,
        expected_schema_version=expected_schema_version,
        temp_permit=temp_permit,
        require_existing=require_existing,
    )


def preflight_new_local_database(
    path: Path,
    *,
    expected_schema_version: str,
    temp_permit: AttestedTempDirectoryV1 | None = None,
) -> str:
    permit = _attest(
        path,
        expected_schema_version=expected_schema_version,
        temp_permit=temp_permit,
        require_existing=False,
    )
    return permit.target_fingerprint


def reattest_local_database(
    permit: LocalDatabasePermitV1,
    *,
    opened_connection: sqlite3.Connection | None = None,
) -> None:
    if not isinstance(permit, LocalDatabasePermitV1):
        raise LocalWriteGuardError("local database permit is forged or stale")
    record = _DATABASE_PERMITS.get(permit)
    if record is None or record[1] != os.getpid() or permit.creator_pid != os.getpid():
        raise LocalWriteGuardError("local database permit is forged or stale")
    owning_temp_permit = record[2]
    if owning_temp_permit is not None:
        _registered_temp_permit(owning_temp_permit)
    root_stat = _guarded_lstat(permit.root)
    if _identity(root_stat) != permit.root_identity:
        raise LocalWriteGuardError("allowed root identity changed")
    _walk_existing(permit.root, permit.path)
    parent_stat = _guarded_lstat(permit.path.parent)
    if _identity(parent_stat) != permit.parent_identity:
        raise LocalWriteGuardError("local database parent identity changed")
    exists = permit.path.exists() or permit.path.is_symlink()
    if permit.target_identity is None:
        if exists:
            raise LocalWriteGuardError("new local database appeared after preflight")
    else:
        if not exists:
            raise LocalWriteGuardError("local database disappeared after preflight")
        target_stat = _guarded_lstat(permit.path)
        if (
            not stat_module.S_ISREG(target_stat.st_mode)
            or int(target_stat.st_nlink) != 1
            or _identity(target_stat) != permit.target_identity
        ):
            raise LocalWriteGuardError("local database identity changed")
    if opened_connection is not None:
        if (
            getattr(opened_connection, "_twinops_attestation", None)
            is _SQLITE_CONNECTION_ATTESTATION
            and getattr(opened_connection, "_twinops_target_identity", None)
            == permit.target_identity
        ):
            return
        row = opened_connection.execute("PRAGMA database_list").fetchone()
        if row is None or Path(row[2]).resolve(strict=False) != permit.path:
            raise LocalWriteGuardError("opened SQLite target identity mismatch")


def _pin_windows_directory(path: Path) -> int | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        create_file = ctypes.windll.kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        handle = create_file(
            str(path),
            0x1 | 0x80,
            0x1 | 0x2,
            None,
            3,
            0x02000000 | 0x00200000,
            None,
        )
        invalid = ctypes.c_void_p(-1).value
        if handle in (None, invalid):
            raise OSError("directory handle unavailable")
        return int(handle)
    except BaseException as exc:
        raise LocalWriteGuardError("local directory pinning failed") from exc


class _RetainedNewLocalDatabaseV1:
    """Retain the attested root and parent through create and cleanup."""

    def __init__(self, permit: LocalDatabasePermitV1) -> None:
        if not isinstance(permit, LocalDatabasePermitV1):
            raise LocalWriteGuardError("local database permit is forged or stale")
        if permit.target_identity is not None:
            raise LocalWriteGuardError("fresh local database permit is required")
        self.permit = permit
        self._root_descriptor: int | None = None
        self._parent_descriptor: int | None = None
        self._windows_root_handle: int | None = None
        self._windows_parent_handle: int | None = None
        self.created_identity: tuple[int, int] | None = None

    def pin(self) -> None:
        reattest_local_database(self.permit)
        try:
            if os.name == "nt":
                self._windows_root_handle = _pin_windows_directory(
                    self.permit.root
                )
                if self.permit.path.parent != self.permit.root:
                    self._windows_parent_handle = _pin_windows_directory(
                        self.permit.path.parent
                    )
            else:
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                )
                self._root_descriptor = os.open(self.permit.root, flags)
                if _identity(os.fstat(self._root_descriptor)) != self.permit.root_identity:
                    raise LocalWriteGuardError("allowed root identity changed")
                current = os.dup(self._root_descriptor)
                try:
                    relative_parent = self.permit.path.parent.relative_to(
                        self.permit.root
                    )
                    for component in relative_parent.parts:
                        following = os.open(component, flags, dir_fd=current)
                        os.close(current)
                        current = following
                    self._parent_descriptor = current
                    current = None
                finally:
                    if current is not None:
                        os.close(current)
                if (
                    _identity(os.fstat(self._parent_descriptor))
                    != self.permit.parent_identity
                ):
                    raise LocalWriteGuardError(
                        "local database parent identity changed"
                    )
            reattest_local_database(self.permit)
        except BaseException:
            self.close()
            raise

    def _created_stat(self) -> os.stat_result:
        if self._parent_descriptor is not None:
            return os.stat(
                self.permit.path.name,
                dir_fd=self._parent_descriptor,
                follow_symlinks=False,
            )
        return os.lstat(self.permit.path)

    def _attest_created_path(self) -> None:
        if self.created_identity is None:
            raise LocalWriteGuardError("created local database identity is unavailable")
        root_stat = _guarded_lstat(self.permit.root)
        parent_stat = _guarded_lstat(self.permit.path.parent)
        if (
            _identity(root_stat) != self.permit.root_identity
            or _identity(parent_stat) != self.permit.parent_identity
        ):
            raise LocalWriteGuardError("local database parent identity changed")
        _walk_existing(self.permit.root, self.permit.path)
        path_stat = _guarded_lstat(self.permit.path)
        retained_stat = self._created_stat()
        for value in (path_stat, retained_stat):
            if (
                not stat_module.S_ISREG(value.st_mode)
                or stat_module.S_ISLNK(value.st_mode)
                or _is_windows_reparse_point(self.permit.path, value)
                or int(value.st_nlink) != 1
                or _identity(value) != self.created_identity
            ):
                raise LocalWriteGuardError("created local database identity changed")
        if (
            self._root_descriptor is not None
            and _identity(os.fstat(self._root_descriptor))
            != self.permit.root_identity
        ):
            raise LocalWriteGuardError("allowed root identity changed")
        if (
            self._parent_descriptor is not None
            and _identity(os.fstat(self._parent_descriptor))
            != self.permit.parent_identity
        ):
            raise LocalWriteGuardError("local database parent identity changed")

    def create(self) -> int:
        if (
            self._root_descriptor is None
            and self._windows_root_handle is None
        ):
            raise LocalWriteGuardError("local directory pin is unavailable")
        reattest_local_database(self.permit)
        descriptor: int | None = None
        try:
            flags = (
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_BINARY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            if self._parent_descriptor is not None:
                descriptor = os.open(
                    self.permit.path.name,
                    flags,
                    0o600,
                    dir_fd=self._parent_descriptor,
                )
            else:
                descriptor = os.open(self.permit.path, flags, 0o600)
            created = os.fstat(descriptor)
            self.created_identity = _identity(created)
            if (
                not stat_module.S_ISREG(created.st_mode)
                or int(created.st_nlink) != 1
            ):
                raise LocalWriteGuardError("created local database is not regular")
            self._attest_created_path()
            return descriptor
        except BaseException:
            if descriptor is not None:
                os.close(descriptor)
            self.cleanup_created()
            raise

    def cleanup_created(self) -> None:
        if self.created_identity is None:
            return
        try:
            current = self._created_stat()
        except FileNotFoundError:
            self.created_identity = None
            return
        except OSError as exc:
            raise LocalWriteGuardError(
                "created local database cleanup attestation failed"
            ) from exc
        if (
            not stat_module.S_ISREG(current.st_mode)
            or stat_module.S_ISLNK(current.st_mode)
            or _is_windows_reparse_point(self.permit.path, current)
            or int(current.st_nlink) != 1
            or _identity(current) != self.created_identity
        ):
            raise LocalWriteGuardError(
                "created local database cleanup identity changed"
            )
        try:
            if self._parent_descriptor is not None:
                os.unlink(
                    self.permit.path.name,
                    dir_fd=self._parent_descriptor,
                )
            else:
                parent = _guarded_lstat(self.permit.path.parent)
                if _identity(parent) != self.permit.parent_identity:
                    raise LocalWriteGuardError(
                        "local database parent identity changed"
                    )
                os.unlink(self.permit.path)
        except LocalWriteGuardError:
            raise
        except OSError as exc:
            raise LocalWriteGuardError(
                "created local database cleanup failed"
            ) from exc
        self.created_identity = None

    def close(self) -> None:
        for name in ("_parent_descriptor", "_root_descriptor"):
            descriptor = getattr(self, name)
            if descriptor is not None:
                try:
                    os.close(descriptor)
                finally:
                    setattr(self, name, None)
        for name in ("_windows_parent_handle", "_windows_root_handle"):
            handle = getattr(self, name)
            if handle is not None:
                try:
                    _close_windows_handle(handle)
                finally:
                    setattr(self, name, None)


def _retain_new_local_database(
    permit: LocalDatabasePermitV1,
) -> _RetainedNewLocalDatabaseV1:
    retained = _RetainedNewLocalDatabaseV1(permit)
    retained.pin()
    return retained


def _pin_windows_file(path: Path) -> int | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        create_file = ctypes.windll.kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        handle = create_file(
            str(path),
            0x80,
            0x1 | 0x2,
            None,
            3,
            0x00200000,
            None,
        )
        invalid = ctypes.c_void_p(-1).value
        if handle in (None, invalid):
            raise OSError("file handle unavailable")
        return int(handle)
    except BaseException as exc:
        raise LocalWriteGuardError("SQLite file pinning failed") from exc


def _close_windows_handle(handle: int | None) -> None:
    if handle is None:
        return
    import ctypes
    from ctypes import wintypes

    close_handle = ctypes.windll.kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    close_handle(wintypes.HANDLE(handle))


def _proc_fd_inventory() -> frozenset[int] | None:
    root = Path("/proc/self/fd")
    if not root.is_dir():
        return None
    descriptors: set[int] = set()
    try:
        for name in os.listdir(root):
            try:
                descriptors.add(int(name))
            except ValueError:
                continue
    except OSError as exc:
        raise LocalWriteGuardError(
            "opened SQLite identity verification failed"
        ) from exc
    return frozenset(descriptors)


def _new_fd_identities(before: frozenset[int]) -> frozenset[tuple[int, int]]:
    after = _proc_fd_inventory()
    if after is None:
        raise LocalWriteGuardError("opened SQLite identity verification unavailable")
    identities: set[tuple[int, int]] = set()
    for descriptor in after - before:
        try:
            value = os.fstat(descriptor)
        except OSError:
            continue
        if stat_module.S_ISREG(value.st_mode):
            identities.add(_identity(value))
    return frozenset(identities)


def _directory_change_token(path: Path) -> tuple[int, int, int, int]:
    value = _guarded_lstat(path)
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_mtime_ns),
        int(value.st_ctime_ns),
    )


def _open_attested_sqlite_connection(
    permit: LocalDatabasePermitV1,
    *,
    read_only: bool = False,
) -> sqlite3.Connection:
    """Open and prove the actual SQLite file while an identity pin is held."""

    reattest_local_database(permit)
    descriptor: int | None = None
    windows_handle: int | None = None
    connection: sqlite3.Connection | None = None
    try:
        parent_token = (
            _directory_change_token(permit.path.parent)
            if os.name != "nt"
            else None
        )
        descriptor = os.open(
            permit.path,
            (os.O_RDONLY if read_only else os.O_RDWR)
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if (
            not stat_module.S_ISREG(opened.st_mode)
            or int(opened.st_nlink) != 1
            or _identity(opened) != permit.target_identity
        ):
            raise LocalWriteGuardError("opened SQLite target identity mismatch")
        windows_handle = _pin_windows_file(permit.path)
        reattest_local_database(permit)
        before_fds = _proc_fd_inventory()
        if os.name != "nt" and before_fds is None:
            raise LocalWriteGuardError(
                "opened SQLite identity verification unavailable"
            )
        if os.name != "nt":
            proc_path = Path("/proc/self/fd") / str(descriptor)
            if not proc_path.exists():
                raise LocalWriteGuardError(
                    "opened SQLite identity verification unavailable"
                )
            mode = "ro" if read_only else "rw"
            uri = "file:" + quote(proc_path.as_posix(), safe="/:") + f"?mode={mode}"
            connection = sqlite3.connect(
                uri,
                uri=True,
                timeout=5,
                factory=_GuardedSQLiteConnection,
            )
        elif read_only:
            uri = "file:" + quote(permit.path.as_posix(), safe="/:") + "?mode=ro"
            connection = sqlite3.connect(
                uri,
                uri=True,
                timeout=5,
                factory=_GuardedSQLiteConnection,
            )
        else:
            connection = sqlite3.connect(
                permit.path,
                timeout=5,
                factory=_GuardedSQLiteConnection,
            )
        connection.row_factory = sqlite3.Row
        if (
            parent_token is not None
            and _directory_change_token(permit.path.parent) != parent_token
        ):
            raise LocalWriteGuardError("opened SQLite target identity mismatch")
        reattest_local_database(permit)
        if before_fds is not None:
            opened_identities = _new_fd_identities(before_fds)
            if opened_identities != frozenset({permit.target_identity}):
                raise LocalWriteGuardError("opened SQLite target identity mismatch")
        setattr(
            connection,
            "_twinops_attestation",
            _SQLITE_CONNECTION_ATTESTATION,
        )
        setattr(connection, "_twinops_target_identity", permit.target_identity)
        reattest_local_database(permit, opened_connection=connection)
        if read_only:
            connection.execute("PRAGMA query_only=ON")
            if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
                raise LocalWriteGuardError("SQLite query-only mode is unavailable")
        return connection
    except BaseException:
        if connection is not None:
            connection.close()
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
        _close_windows_handle(windows_handle)


def _readonly_connection(permit: LocalDatabasePermitV1) -> sqlite3.Connection:
    return _open_attested_sqlite_connection(permit, read_only=True)


def reattest_local_staged_handoff(
    path: Path,
    *,
    expected_target_fingerprint: str,
    expected_schema_version: str,
    expected_batch_id: str,
    expected_source_sha256: str,
    expected_manifest_sha256: str,
    expected_raw_row_count: int,
    expected_sample_count: int,
    expected_operating_cycle_count: int,
    require_no_active_batch: bool,
) -> None:
    for digest in (
        expected_target_fingerprint,
        expected_batch_id,
        expected_source_sha256,
        expected_manifest_sha256,
    ):
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ValueError("handoff identity must be canonical sha256")
    permit = attest_local_database(
        path,
        expected_schema_version=expected_schema_version,
        require_existing=True,
    )
    if permit.target_fingerprint != expected_target_fingerprint:
        raise LocalWriteGuardError("local target fingerprint mismatch")
    before_identity = permit.target_identity
    connection = _readonly_connection(permit)
    try:
        reattest_local_database(permit, opened_connection=connection)
        verification = verify_schema_version(connection, expected_schema_version)
        if not verification.is_current:
            raise LocalWriteGuardError("local schema verification failed")
        identity_row = connection.execute(
            "SELECT environment,target_fingerprint,schema_version "
            "FROM deployment_identity_v1 WHERE identity_key='primary'"
        ).fetchone()
        if (
            identity_row is None
            or identity_row["environment"] != "local"
            or identity_row["target_fingerprint"] != expected_target_fingerprint
            or identity_row["schema_version"] != expected_schema_version
        ):
            raise LocalWriteGuardError("local deployment identity mismatch")
        row = connection.execute(
            "SELECT status,source_bytes,source_sha256,manifest_json,manifest_sha256,"
            "raw_row_count,sample_count,operating_cycle_count "
            "FROM historical_import_batches_v1 WHERE batch_id=?",
            (expected_batch_id,),
        ).fetchone()
        if row is None or row["status"] != "staged":
            raise LocalWriteGuardError("staged handoff batch mismatch")
        source_bytes = row["source_bytes"]
        if isinstance(source_bytes, memoryview):
            source_bytes = source_bytes.tobytes()
        if type(source_bytes) is not bytes:
            raise LocalWriteGuardError("stored source is malformed")
        actual_source = "sha256:" + sha256(source_bytes).hexdigest()
        actual_manifest = "sha256:" + sha256(row["manifest_json"].encode("utf-8")).hexdigest()
        if (
            actual_source != expected_source_sha256
            or row["source_sha256"] != expected_source_sha256
            or actual_manifest != expected_manifest_sha256
            or row["manifest_sha256"] != expected_manifest_sha256
            or row["raw_row_count"] != expected_raw_row_count
            or row["sample_count"] != expected_sample_count
            or row["operating_cycle_count"] != expected_operating_cycle_count
        ):
            raise LocalWriteGuardError("staged handoff evidence mismatch")
        raw_count = connection.execute(
            "SELECT COUNT(*) FROM historical_raw_rows_v1 WHERE batch_id=?",
            (expected_batch_id,),
        ).fetchone()[0]
        sample_count = connection.execute(
            "SELECT COUNT(*) FROM historical_samples_v1 WHERE batch_id=?",
            (expected_batch_id,),
        ).fetchone()[0]
        if raw_count != expected_raw_row_count or sample_count != expected_sample_count:
            raise LocalWriteGuardError("staged handoff row count mismatch")
        active_count = connection.execute(
            "SELECT COUNT(*) FROM historical_import_batches_v1 WHERE status='active'"
        ).fetchone()[0]
        if require_no_active_batch and active_count:
            raise LocalWriteGuardError("an active historical batch already exists")
        from twinops.storage.sqlite_historical_repository_v1 import (
            SQLiteHistoricalRepositoryV1,
        )

        repository = SQLiteHistoricalRepositoryV1(
            permit.path,
            connection_factory=lambda ignored: _readonly_connection(permit),
        )
        reconstructed = repository.reconstruct_source(expected_batch_id)
        summary = repository._stored_batch(connection, expected_batch_id).summary
        if (
            reconstructed != source_bytes
            or summary.status != "staged"
            or summary.source_sha256 != expected_source_sha256
            or summary.manifest_sha256 != expected_manifest_sha256
            or summary.raw_row_count != expected_raw_row_count
            or summary.sample_count != expected_sample_count
            or summary.operating_cycle_count != expected_operating_cycle_count
        ):
            raise LocalWriteGuardError("staged handoff reconstruction mismatch")
        reattest_local_database(permit, opened_connection=connection)
        if permit.target_identity != before_identity:
            raise LocalWriteGuardError("local database identity changed")
    except (sqlite3.Error, UnicodeError, TypeError, AttributeError) as exc:
        raise LocalWriteGuardError("read-only staged handoff verification failed") from exc
    finally:
        connection.close()


__all__ = (
    "AttestedTempDirectoryV1",
    "LocalDatabasePermitV1",
    "LocalWriteGuardError",
    "attest_local_database",
    "compute_local_target_fingerprint",
    "create_attested_temp_dir",
    "preflight_new_local_database",
    "reattest_local_database",
    "reattest_local_staged_handoff",
    "remove_attested_temp_dir",
)
