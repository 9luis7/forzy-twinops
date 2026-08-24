"""Canonical, fail-closed result publication for history administration."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import stat as stat_module


_CHECKED_IN_LAUNCHER = Path(__file__).resolve().parents[5] / "scripts" / "history_admin.py"
_RESULT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPARSE_ATTRIBUTE = 0x400
_ASSET_ID = "forzy-motor-01"
_SCHEMA_VERSION = "003"
_ENVIRONMENTS = frozenset({"local", "preview", "production"})
_RESULT_KEYS = {
    "migrate-local": frozenset(
        {
            "command", "mode", "environment", "targetFingerprint",
            "schemaVersion", "migrationManifestSha256", "initialPolicyId",
            "initialPolicyConfigurationHash", "appliedMigrationCount",
            "policyInserted", "writesPerformed",
        }
    ),
    "stage-history": frozenset(
        {
            "command", "mode", "environment", "targetFingerprint",
            "schemaVersion", "assetId", "batchId", "sourceSha256",
            "manifestSha256", "rawRowCount", "sampleCount",
            "operatingCycleCount", "inserted", "writesPerformed",
        }
    ),
    "activate-history": frozenset(
        {
            "command", "mode", "environment", "targetFingerprint",
            "schemaVersion", "assetId", "batchId", "previousActiveBatchId",
            "activeBatchId", "sourceSha256", "manifestSha256",
            "assessmentManifestSha256", "rawRowCount", "sampleCount",
            "operatingCycleCount", "assessmentCount", "activated",
            "writesPerformed",
        }
    ),
    "show-active": frozenset(
        {
            "command", "environment", "targetFingerprint", "schemaVersion",
            "assetId", "activeBatchId", "sourceSha256", "manifestSha256",
            "assessmentManifestSha256", "rawRowCount", "sampleCount",
            "operatingCycleCount", "assessmentCount",
        }
    ),
    "verify-active": frozenset(
        {
            "command", "environment", "targetFingerprint", "schemaVersion",
            "assetId", "activeBatchId", "sourceSha256", "manifestSha256",
            "assessmentManifestSha256", "rawRowCount", "sampleCount",
            "operatingCycleCount", "assessmentCount", "verified",
        }
    ),
}
_ORIGINAL_OS_REPLACE = os.replace


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
    return _require_regular_stat(value, path=path, directory=directory)


def _require_regular_stat(
    value: os.stat_result,
    *,
    path: Path,
    directory: bool,
) -> os.stat_result:
    if stat_module.S_ISLNK(value.st_mode) or _is_windows_reparse_point(path, value):
        raise AdminResultWriterError("result path contains a link or reparse point")
    expected = stat_module.S_ISDIR if directory else stat_module.S_ISREG
    if not expected(value.st_mode):
        raise AdminResultWriterError("result path has an invalid file type")
    if not directory and int(value.st_nlink) != 1:
        raise AdminResultWriterError("result path has an invalid link count")
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


def _require_sha256(value: object, field: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be canonical sha256")


def _require_count(value: object, field: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")


def _validate_common(result: Mapping[str, object]) -> None:
    if result["environment"] not in _ENVIRONMENTS:
        raise ValueError("environment literal is invalid")
    if result["schemaVersion"] != _SCHEMA_VERSION:
        raise ValueError("schema version literal is invalid")
    _require_sha256(result["targetFingerprint"], "target fingerprint")
    if "assetId" in result and result["assetId"] != _ASSET_ID:
        raise ValueError("asset literal is invalid")


def _validate_active_fields(result: Mapping[str, object]) -> None:
    active = result["activeBatchId"]
    _require_sha256(active, "active batch", nullable=True)
    _require_sha256(result["sourceSha256"], "source", nullable=True)
    _require_sha256(result["manifestSha256"], "manifest", nullable=True)
    _require_sha256(
        result["assessmentManifestSha256"],
        "assessment manifest",
        nullable=True,
    )
    for field in (
        "rawRowCount",
        "sampleCount",
        "operatingCycleCount",
        "assessmentCount",
    ):
        _require_count(result[field], field)
    if active is None:
        if any(
            result[field] is not None
            for field in (
                "sourceSha256",
                "manifestSha256",
                "assessmentManifestSha256",
            )
        ) or any(
            result[field] != 0
            for field in (
                "rawRowCount",
                "sampleCount",
                "operatingCycleCount",
                "assessmentCount",
            )
        ):
            raise ValueError("null active batch fields are inconsistent")
        return
    if result["sourceSha256"] is None or result["manifestSha256"] is None:
        raise ValueError("active batch hashes are required")
    if (
        result["assessmentManifestSha256"] is None
    ) != (result["assessmentCount"] == 0):
        raise ValueError("assessment manifest/count fields are inconsistent")


def validate_admin_result_v1(result: Mapping[str, object]) -> None:
    """Validate one frozen, command-specific, scalar-only admin result."""

    if not isinstance(result, Mapping):
        raise ValueError("admin result must be a mapping")
    if any(not isinstance(key, str) for key in result):
        raise ValueError("admin result keys must be strings")
    if any(
        value is not None
        and type(value) not in {str, int, bool}
        for value in result.values()
    ):
        raise ValueError("admin result values must be flat JSON scalars")
    command = result.get("command")
    if not isinstance(command, str) or command not in _RESULT_KEYS:
        raise ValueError("admin result command is invalid")
    if set(result) != _RESULT_KEYS[command]:
        raise ValueError("admin result keys do not match command model")
    _validate_common(result)

    if command == "migrate-local":
        if result["mode"] not in {"dry-run", "apply"}:
            raise ValueError("mode literal is invalid")
        if result["environment"] != "local":
            raise ValueError("migration environment must be local")
        _require_sha256(result["migrationManifestSha256"], "migration manifest")
        _require_sha256(
            result["initialPolicyConfigurationHash"],
            "initial policy configuration",
        )
        if result["initialPolicyId"] != "forzy-live-window-v1":
            raise ValueError("initial policy literal is invalid")
        _require_count(result["appliedMigrationCount"], "applied migration count")
        _require_count(result["writesPerformed"], "writes performed")
        if type(result["policyInserted"]) is not bool:
            raise ValueError("policy inserted must be boolean")
        if result["mode"] == "dry-run" and result["writesPerformed"] != 0:
            raise ValueError("dry-run cannot report writes")
        return

    if command == "stage-history":
        if result["mode"] not in {"dry-run", "apply"}:
            raise ValueError("mode literal is invalid")
        for field in ("batchId", "sourceSha256", "manifestSha256"):
            _require_sha256(result[field], field)
        for field in (
            "rawRowCount",
            "sampleCount",
            "operatingCycleCount",
            "writesPerformed",
        ):
            _require_count(result[field], field)
        if type(result["inserted"]) is not bool:
            raise ValueError("inserted must be boolean")
        if (
            result["mode"] == "dry-run" or not result["inserted"]
        ) and result["writesPerformed"] != 0:
            raise ValueError("stage result write invariants failed")
        return

    if command == "activate-history":
        if result["mode"] not in {"dry-run", "apply"}:
            raise ValueError("mode literal is invalid")
        for field in (
            "batchId",
            "activeBatchId",
            "sourceSha256",
            "manifestSha256",
        ):
            _require_sha256(result[field], field)
        _require_sha256(
            result["previousActiveBatchId"],
            "previous active batch",
            nullable=True,
        )
        _require_sha256(
            result["assessmentManifestSha256"],
            "assessment manifest",
            nullable=True,
        )
        if result["activeBatchId"] != result["batchId"]:
            raise ValueError("activation batch identities diverge")
        for field in (
            "rawRowCount",
            "sampleCount",
            "operatingCycleCount",
            "assessmentCount",
            "writesPerformed",
        ):
            _require_count(result[field], field)
        if (
            result["assessmentManifestSha256"] is None
        ) != (result["assessmentCount"] == 0):
            raise ValueError("assessment manifest/count fields are inconsistent")
        if type(result["activated"]) is not bool:
            raise ValueError("activated must be boolean")
        if (
            result["mode"] == "dry-run" or not result["activated"]
        ) and result["writesPerformed"] != 0:
            raise ValueError("activation result write invariants failed")
        return

    _validate_active_fields(result)
    if command == "verify-active":
        if result["verified"] is not True or result["activeBatchId"] is None:
            raise ValueError("verification result is inconsistent")


def canonical_admin_result_bytes(result: Mapping[str, object]) -> bytes:
    validate_admin_result_v1(result)
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
        self._preflight_state: tuple[tuple[int, int], tuple[int, int] | None] | None = None
        self._root_descriptor: int | None = None
        self._windows_root_handle: int | None = None
        self._last_sha256: str | None = None

    @property
    def last_sha256(self) -> str | None:
        return self._last_sha256

    def _pin_result_root(self, root_identity: tuple[int, int]) -> None:
        if os.name == "nt":
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
                    str(self._result_root),
                    0x10000 | 0x80,
                    0x1 | 0x2,
                    None,
                    3,
                    0x02000000 | 0x00200000,
                    None,
                )
                invalid = ctypes.c_void_p(-1).value
                if handle in (None, invalid):
                    raise OSError("directory handle unavailable")
                self._windows_root_handle = int(handle)
            except BaseException as exc:
                raise AdminResultWriterError(
                    "result directory pinning failed"
                ) from exc
        else:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            try:
                descriptor = os.open(self._result_root, flags)
                if _identity(os.fstat(descriptor)) != root_identity:
                    raise AdminResultWriterError(
                        "result directory identity changed"
                    )
                self._root_descriptor = descriptor
            except BaseException:
                if "descriptor" in locals():
                    os.close(descriptor)
                raise

    def _release_result_root(self) -> None:
        if self._root_descriptor is not None:
            try:
                os.close(self._root_descriptor)
            finally:
                self._root_descriptor = None
        if self._windows_root_handle is not None:
            try:
                import ctypes
                from ctypes import wintypes

                close_handle = ctypes.windll.kernel32.CloseHandle
                close_handle.argtypes = (wintypes.HANDLE,)
                close_handle.restype = wintypes.BOOL
                close_handle(wintypes.HANDLE(self._windows_root_handle))
            finally:
                self._windows_root_handle = None
        self._preflight_state = None

    def __del__(self):
        try:
            self._release_result_root()
        except BaseException:
            pass

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
        if self._root_descriptor is not None:
            try:
                return _identity(self._child_stat(self.result_path.name))
            except FileNotFoundError:
                return None
        if not (self.result_path.exists() or self.result_path.is_symlink()):
            return None
        return _identity(_lstat_regular(self.result_path, directory=False))

    def _child_stat(self, name: str) -> os.stat_result:
        try:
            if self._root_descriptor is not None:
                value = os.stat(
                    name,
                    dir_fd=self._root_descriptor,
                    follow_symlinks=False,
                )
            else:
                value = os.lstat(self._result_root / name)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise AdminResultWriterError("result path attestation failed") from exc
        return _require_regular_stat(
            value,
            path=self._result_root / name,
            directory=False,
        )

    def _open_child(self, name: str, flags: int, mode: int = 0o600) -> int:
        if self._root_descriptor is not None:
            return os.open(
                name,
                flags,
                mode,
                dir_fd=self._root_descriptor,
            )
        return os.open(self._result_root / name, flags, mode)

    def _read_child_bytes(
        self,
        name: str,
        *,
        expected_identity: tuple[int, int],
        maximum_size: int,
    ) -> bytes:
        descriptor: int | None = None
        try:
            descriptor = self._open_child(
                name,
                os.O_RDONLY
                | getattr(os, "O_BINARY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            before = _require_regular_stat(
                os.fstat(descriptor),
                path=self._result_root / name,
                directory=False,
            )
            if _identity(before) != expected_identity or before.st_size > maximum_size:
                raise AdminResultWriterError("result file identity changed")
            chunks: list[bytes] = []
            remaining = maximum_size + 1
            while remaining > 0:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
            payload = b"".join(chunks)
            if (
                _identity(after) != expected_identity
                or after.st_size != before.st_size
                or len(payload) != before.st_size
                or len(payload) > maximum_size
            ):
                raise AdminResultWriterError("result file identity changed")
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if _identity(self._child_stat(name)) != expected_identity:
            raise AdminResultWriterError("result file identity changed")
        return payload

    def _replace_child(
        self,
        source_name: str,
        destination_name: str,
        *,
        operation,
    ) -> None:
        if self._root_descriptor is not None:
            operation(
                source_name,
                destination_name,
                src_dir_fd=self._root_descriptor,
                dst_dir_fd=self._root_descriptor,
            )
        else:
            operation(
                self._result_root / source_name,
                self._result_root / destination_name,
            )

    def _reattest_publication(
        self,
        root_identity: tuple[int, int],
        destination_identity: tuple[int, int] | None,
    ) -> None:
        self._reattest_launcher_and_worktree()
        root_stat = _lstat_regular(self._result_root, directory=True)
        if _identity(root_stat) != root_identity:
            raise AdminResultWriterError("result directory identity changed")
        if (
            self._root_descriptor is not None
            and _identity(os.fstat(self._root_descriptor)) != root_identity
        ):
            raise AdminResultWriterError("pinned result directory identity changed")
        current = self._destination_identity()
        if current != destination_identity:
            raise AdminResultWriterError("result destination identity changed")

    def preflight(self) -> None:
        """Attest and pin the publication boundary without creating a result."""

        if self._preflight_state is not None:
            self._reattest_publication(*self._preflight_state)
            return
        root_identity = self._ensure_result_root()
        destination_identity = self._destination_identity()
        self._reattest_publication(root_identity, destination_identity)
        try:
            self._pin_result_root(root_identity)
            self._reattest_publication(root_identity, destination_identity)
        except BaseException:
            self._release_result_root()
            raise
        self._preflight_state = (root_identity, destination_identity)

    def _fsync_directory(self) -> None:
        if self._root_descriptor is not None:
            os.fsync(self._root_descriptor)
            return
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

    def _cleanup_private_temp(
        self,
        private_name: str,
        expected_identity: tuple[int, int] | None,
    ) -> None:
        try:
            current = self._child_stat(private_name)
            if expected_identity is None or _identity(current) != expected_identity:
                return
            if self._root_descriptor is not None:
                os.unlink(private_name, dir_fd=self._root_descriptor)
            else:
                root = _lstat_regular(self._result_root, directory=True)
                if (
                    self._preflight_state is None
                    or _identity(root) != self._preflight_state[0]
                ):
                    return
                os.unlink(self._result_root / private_name)
        except (FileNotFoundError, OSError, AdminResultWriterError):
            return

    def _restore_previous_destination(
        self,
        *,
        root_identity: tuple[int, int],
        previous_bytes: bytes | None,
        published_identity: tuple[int, int] | None,
    ) -> None:
        """Best-effort rollback only inside the still-pinned result root."""

        restore_name: str | None = None
        restore_identity: tuple[int, int] | None = None
        try:
            if self._root_descriptor is None:
                root_stat = _lstat_regular(self._result_root, directory=True)
                if _identity(root_stat) != root_identity:
                    return
            if published_identity is None:
                return
            try:
                current = self._child_stat(self.result_path.name)
            except FileNotFoundError:
                return
            if _identity(current) != published_identity:
                return
            if previous_bytes is None:
                if self._root_descriptor is not None:
                    os.unlink(
                        self.result_path.name,
                        dir_fd=self._root_descriptor,
                    )
                else:
                    os.unlink(self.result_path)
                return
            restore_name = f".{secrets.token_hex(16)}.tmp"
            descriptor = self._open_child(
                restore_name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_BINARY", 0),
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb", closefd=True) as stream:
                    stream.write(previous_bytes)
                    stream.flush()
                    os.fsync(stream.fileno())
                    restored = os.fstat(stream.fileno())
                    restore_identity = _identity(restored)
            except BaseException:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
            if (
                restore_identity is None
                or _identity(self._child_stat(restore_name)) != restore_identity
            ):
                raise AdminResultWriterError("result restore identity changed")
            if _identity(self._child_stat(self.result_path.name)) != published_identity:
                return
            self._replace_child(
                restore_name,
                self.result_path.name,
                operation=_ORIGINAL_OS_REPLACE,
            )
            restore_name = None
        except BaseException:
            pass
        finally:
            if restore_name is not None:
                self._cleanup_private_temp(restore_name, restore_identity)

    def write(self, result: Mapping[str, object]) -> bytes:
        private_name: str | None = None
        private_identity: tuple[int, int] | None = None
        replaced = False
        root_identity: tuple[int, int] | None = None
        previous_bytes: bytes | None = None
        published_identity: tuple[int, int] | None = None
        try:
            self._last_sha256 = None
            payload = canonical_admin_result_bytes(result)
            self.preflight()
            if self._preflight_state is None:
                raise AdminResultWriterError("result preflight state is unavailable")
            root_identity, destination_identity = self._preflight_state
            self._reattest_publication(root_identity, destination_identity)
            if destination_identity is not None:
                previous_bytes = self._read_child_bytes(
                    self.result_path.name,
                    expected_identity=destination_identity,
                    maximum_size=1024 * 1024,
                )

            for _ in range(16):
                private_name = f".{secrets.token_hex(16)}.tmp"
                try:
                    descriptor = self._open_child(
                        private_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                        0o600,
                    )
                    opened_stat = _require_regular_stat(
                        os.fstat(descriptor),
                        path=self._result_root / private_name,
                        directory=False,
                    )
                    private_identity = _identity(opened_stat)
                    break
                except FileExistsError:
                    private_name = None
            else:
                raise AdminResultWriterError("exclusive result temp allocation failed")

            try:
                with os.fdopen(descriptor, "wb", closefd=True) as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                    written_stat = _require_regular_stat(
                        os.fstat(stream.fileno()),
                        path=self._result_root / private_name,
                        directory=False,
                    )
                    if _identity(written_stat) != private_identity:
                        raise AdminResultWriterError(
                            "result temp identity changed"
                        )
            except BaseException:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise

            if private_name is None or private_identity is None:
                raise AdminResultWriterError("result temp identity unavailable")
            temp_stat = self._child_stat(private_name)
            if (
                temp_stat.st_size != len(payload)
                or _identity(temp_stat) != private_identity
            ):
                raise AdminResultWriterError("result temp size verification failed")
            self._reattest_publication(root_identity, destination_identity)
            self._replace_child(
                private_name,
                self.result_path.name,
                operation=os.replace,
            )
            replaced = True
            private_name = None
            published_stat = self._child_stat(self.result_path.name)
            published_identity = _identity(published_stat)
            if _identity(published_stat) != _identity(temp_stat):
                raise AdminResultWriterError("published result identity mismatch")
            if self._read_child_bytes(
                self.result_path.name,
                expected_identity=published_identity,
                maximum_size=len(payload),
            ) != payload:
                raise AdminResultWriterError("published result bytes mismatch")
            self._fsync_directory()
            self._reattest_launcher_and_worktree()
            root_stat = _lstat_regular(self._result_root, directory=True)
            if _identity(root_stat) != root_identity:
                raise AdminResultWriterError("result directory identity changed")
            self._last_sha256 = "sha256:" + sha256(payload).hexdigest()
            return payload
        except AdminResultWriterError:
            raise
        except BaseException as exc:
            raise AdminResultWriterError("admin result publication failed") from exc
        finally:
            if replaced and root_identity is not None and self._last_sha256 is None:
                self._restore_previous_destination(
                    root_identity=root_identity,
                    previous_bytes=previous_bytes,
                    published_identity=published_identity,
                )
            if private_name is not None:
                self._cleanup_private_temp(private_name, private_identity)
            self._release_result_root()


__all__ = (
    "AdminResultWriterError",
    "AdminResultWriterV1",
    "canonical_admin_result_bytes",
    "validate_admin_result_v1",
)
