"""Fail-closed local SQLite path and staged-handoff attestation."""

from __future__ import annotations

from dataclasses import dataclass
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

from twinops.storage.schema_migrations import (
    registered_migration_specs,
    verify_schema_version,
)


_CHECKED_IN_LAUNCHER = Path(__file__).resolve().parents[5] / "scripts" / "history_admin.py"
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^[0-9]{3}$")
_REPARSE_ATTRIBUTE = 0x400


class LocalWriteGuardError(RuntimeError):
    """Raised without path-bearing details when local attestation fails."""


@dataclass(frozen=True)
class AttestedTempDirectoryV1:
    path: Path
    _token: str
    _creator_pid: int
    _identity: tuple[int, int]


@dataclass(frozen=True)
class LocalDatabasePermitV1:
    path: Path
    expected_schema_version: str
    target_fingerprint: str
    root: Path
    root_identity: tuple[int, int]
    parent_identity: tuple[int, int]
    target_identity: tuple[int, int] | None
    creator_pid: int
    _token: str
    _temp_permit_id: int | None


_TEMP_PERMITS: dict[int, tuple[str, int, Path, tuple[int, int]]] = {}
_DATABASE_PERMITS: dict[int, str] = {}


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
    if raw.startswith(("\\\\", "\\?\\", "\\.\\")):
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
    record = _TEMP_PERMITS.get(id(permit))
    if record is None:
        raise LocalWriteGuardError("temporary directory permit is forged or stale")
    token, creator_pid, root, expected_identity = record
    if (
        token != permit._token
        or creator_pid != permit._creator_pid
        or root != permit.path
        or expected_identity != permit._identity
        or creator_pid != os.getpid()
    ):
        raise LocalWriteGuardError("temporary directory permit is forged or stale")
    value = _guarded_lstat(root)
    if not stat_module.S_ISDIR(value.st_mode) or _identity(value) != expected_identity:
        raise LocalWriteGuardError("temporary directory identity changed")
    return root, expected_identity


def _automatic_temp_permit(
    path: Path,
) -> tuple[int, Path, tuple[int, int]] | None:
    for permit_id, (token, creator_pid, root, identity) in tuple(_TEMP_PERMITS.items()):
        if creator_pid != os.getpid():
            continue
        try:
            path.absolute().relative_to(root.absolute())
        except ValueError:
            continue
        value = _guarded_lstat(root)
        if _identity(value) != identity:
            raise LocalWriteGuardError("temporary directory identity changed")
        return permit_id, root, identity
    return None


def create_attested_temp_dir() -> AttestedTempDirectoryV1:
    root = Path(tempfile.mkdtemp(prefix="twinops-history-admin-"))
    value = _guarded_lstat(root)
    token = secrets.token_hex(32)
    permit = AttestedTempDirectoryV1(
        path=root.resolve(strict=True),
        _token=token,
        _creator_pid=os.getpid(),
        _identity=_identity(value),
    )
    _TEMP_PERMITS[id(permit)] = (
        token,
        permit._creator_pid,
        permit.path,
        permit._identity,
    )
    return permit


def remove_attested_temp_dir(permit: AttestedTempDirectoryV1) -> None:
    root, expected_identity = _registered_temp_permit(permit)
    value = _guarded_lstat(root)
    if _identity(value) != expected_identity:
        raise LocalWriteGuardError("temporary directory identity changed")
    _TEMP_PERMITS.pop(id(permit), None)
    shutil.rmtree(root)


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
) -> tuple[Path, tuple[int, int], int | None]:
    if temp_permit is not None:
        root, root_identity = _registered_temp_permit(temp_permit)
        return root, root_identity, id(temp_permit)
    worktree = _launcher_worktree_root()
    try:
        path.absolute().relative_to(worktree.absolute())
        return worktree, _identity(_guarded_lstat(worktree)), None
    except ValueError:
        automatic = _automatic_temp_permit(path)
        if automatic is None:
            raise LocalWriteGuardError("local path is outside an allowed root")
        permit_id, root, root_identity = automatic
        return root, root_identity, permit_id


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
    root, root_identity, temp_id = _allowed_root(candidate, temp_permit)
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
        if not stat_module.S_ISREG(target_stat.st_mode):
            raise LocalWriteGuardError("local database is not a regular file")
        target_identity = _identity(target_stat)

    fingerprint = compute_local_target_fingerprint(
        canonical,
        expected_schema_version=expected_schema_version,
        migration_hashes=_registered_hashes(),
    )
    token = secrets.token_hex(32)
    permit = LocalDatabasePermitV1(
        path=canonical,
        expected_schema_version=expected_schema_version,
        target_fingerprint=fingerprint,
        root=root.resolve(strict=True),
        root_identity=root_identity,
        parent_identity=_identity(parent_stat),
        target_identity=target_identity,
        creator_pid=os.getpid(),
        _token=token,
        _temp_permit_id=temp_id,
    )
    _DATABASE_PERMITS[id(permit)] = token
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
    if (
        not isinstance(permit, LocalDatabasePermitV1)
        or _DATABASE_PERMITS.get(id(permit)) != permit._token
        or permit.creator_pid != os.getpid()
    ):
        raise LocalWriteGuardError("local database permit is forged or stale")
    if permit._temp_permit_id is not None:
        record = _TEMP_PERMITS.get(permit._temp_permit_id)
        if record is None or record[1] != os.getpid():
            raise LocalWriteGuardError("temporary directory permit is stale")
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
            or _identity(target_stat) != permit.target_identity
        ):
            raise LocalWriteGuardError("local database identity changed")
    if opened_connection is not None:
        row = opened_connection.execute("PRAGMA database_list").fetchone()
        if row is None or Path(row[2]).resolve(strict=False) != permit.path:
            raise LocalWriteGuardError("opened SQLite target identity mismatch")


def _readonly_connection(path: Path) -> sqlite3.Connection:
    uri = "file:" + quote(path.as_posix(), safe="/:" ) + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
        connection.close()
        raise LocalWriteGuardError("SQLite query-only mode is unavailable")
    return connection


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
    connection = _readonly_connection(permit.path)
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
            connection_factory=lambda ignored: _readonly_connection(permit.path),
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
