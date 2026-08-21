"""Archive integrity, safe extraction, and raw-file inventory helpers."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Sequence


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        "conin$",
        "conout$",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
        *(f"com{index}" for index in "¹²³"),
        *(f"lpt{index}" for index in "¹²³"),
    }
)


@dataclass(frozen=True, slots=True)
class RawFile:
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class RawInventory:
    files: tuple[RawFile, ...]
    inventory_sha256: str
    total_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "inventorySha256": self.inventory_sha256,
            "totalBytes": self.total_bytes,
            "files": [
                {
                    "relativePath": item.relative_path,
                    "sizeBytes": item.size_bytes,
                    "sha256": item.sha256,
                }
                for item in self.files
            ],
        }


@dataclass(frozen=True, slots=True)
class ArchivePart:
    """One caller-authorized RAR volume and its exact expected digest."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        if not isinstance(self.sha256, str) or not _SHA256.fullmatch(self.sha256):
            raise ValueError("archive part sha256 must be exactly 64 hexadecimal characters")
        object.__setattr__(self, "sha256", self.sha256.lower())


@dataclass(frozen=True, slots=True)
class RarExtractionLimits:
    """Conservative limits applied to RAR metadata before any output is written."""

    max_file_count: int = 10_000
    max_file_uncompressed_bytes: int = 1 * 1024**3
    max_total_uncompressed_bytes: int = 8 * 1024**3
    max_compression_ratio: float = 1_000.0
    member_timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        integer_limits = (
            ("max_file_count", self.max_file_count),
            ("max_file_uncompressed_bytes", self.max_file_uncompressed_bytes),
            ("max_total_uncompressed_bytes", self.max_total_uncompressed_bytes),
        )
        for name, value in integer_limits:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name, value in (
            ("max_compression_ratio", self.max_compression_ratio),
            ("member_timeout_seconds", self.member_timeout_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a positive finite number")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")


@dataclass(frozen=True, slots=True)
class RarMember:
    relative_path: str
    size_bytes: int
    compressed_bytes: int
    is_directory: bool


@dataclass(frozen=True, slots=True)
class RarInspection:
    parts: tuple[ArchivePart, ...]
    members: tuple[RarMember, ...]
    total_bytes: int
    total_compressed_bytes: int


def hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: str | Path, expected_sha256: str) -> str:
    archive = Path(path)
    if not archive.is_file():
        raise FileNotFoundError(f"dataset archive does not exist: {archive}")
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError("expected_sha256 must be exactly 64 hexadecimal characters")
    actual = hash_file(archive)
    if actual != expected_sha256.lower():
        raise ValueError(
            f"SHA-256 mismatch for {archive.name}: expected {expected_sha256.lower()}, got {actual}"
        )
    return actual


def _require_rarfile():
    install_action = (
        "install the research extra with "
        "python -m pip install -e 'services/twinops[research]' "
        "(requires rarfile>=4.5,<5)"
    )
    try:
        module = importlib.import_module("rarfile")
    except (ImportError, ModuleNotFoundError) as error:
        raise RuntimeError(f"RAR inspection unavailable; {install_action}") from error
    version = getattr(module, "__version__", "")
    match = re.match(r"^(\d+)\.(\d+)", str(version))
    if match is None or not ((4, 5) <= tuple(map(int, match.groups())) < (5, 0)):
        raise RuntimeError(f"incompatible rarfile version; {install_action}")
    return module


def _canonical_path(path: Path, *, relative_to: Path | None = None) -> Path:
    candidate = path
    if relative_to is not None and not candidate.is_absolute():
        candidate = relative_to / candidate
    return candidate.resolve(strict=False)


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path)).casefold()


def _validated_rar_parts(parts: Sequence[ArchivePart]) -> tuple[ArchivePart, ...]:
    if isinstance(parts, (str, bytes, Path)) or not isinstance(parts, Sequence) or not parts:
        raise ValueError("RAR parts must be a non-empty ordered sequence of ArchivePart values")
    normalized: list[ArchivePart] = []
    seen: set[str] = set()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for part in parts:
        if not isinstance(part, ArchivePart):
            raise TypeError("RAR parts must contain only ArchivePart values")
        supplied_path = part.path.absolute()
        try:
            metadata = supplied_path.lstat()
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"RAR archive part does not exist: {supplied_path.name}"
            ) from error
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or (reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag)
        ):
            raise ValueError(
                f"RAR archive part must be a regular non-link file: {supplied_path.name}"
            )
        path = supplied_path.resolve(strict=True)
        key = _path_key(path)
        if key in seen:
            raise ValueError(f"duplicate RAR archive part: {path.name}")
        seen.add(key)
        verify_archive(path, part.sha256)
        normalized.append(ArchivePart(path, part.sha256))
    return tuple(normalized)


def _open_rar(rarfile_module, first_part: Path):
    try:
        return rarfile_module.RarFile(
            first_part,
            mode="r",
            errors="strict",
            crc_check=True,
        )
    except Exception as error:
        if error.__class__.__name__ in {"PasswordRequired", "NoCrypto", "RarWrongPassword"}:
            raise ValueError("encrypted RAR headers are not supported") from error
        raise ValueError(
            f"RAR inspection failed safely ({error.__class__.__name__}); verify the first volume"
        ) from error


def _validate_rar_volume_list(container, parts: tuple[ArchivePart, ...]) -> None:
    expected = [_path_key(part.path) for part in parts]
    try:
        observed_paths = tuple(container.volumelist())
    except Exception as error:
        raise ValueError(
            f"RAR volume discovery failed safely ({error.__class__.__name__})"
        ) from error
    observed = [
        _path_key(_canonical_path(Path(path), relative_to=parts[0].path.parent))
        for path in observed_paths
    ]
    if observed != expected:
        raise ValueError(
            "RAR volume list does not exactly match the ordered caller-supplied archive parts"
        )


def _valid_archive_size(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def inspect_rar_archive(
    parts: Sequence[ArchivePart],
    *,
    limits: RarExtractionLimits = RarExtractionLimits(),
) -> RarInspection:
    """Inspect an exact caller-supplied RAR volume set without writing output."""

    if not isinstance(limits, RarExtractionLimits):
        raise TypeError("limits must be a RarExtractionLimits value")
    checked_parts = _validated_rar_parts(parts)
    rarfile_module = _require_rarfile()
    container = _open_rar(rarfile_module, checked_parts[0].path)
    with container:
        _validate_rar_volume_list(container, checked_parts)
        if container.needs_password():
            raise ValueError("password-protected RAR archives are not supported")
        members: list[RarMember] = []
        collision_paths: list[tuple[str, bool]] = []
        file_count = 0
        total_bytes = 0
        total_compressed = 0
        for info in container.infolist():
            name = _safe_name(info.filename)
            if info.is_symlink():
                raise ValueError(f"RAR symlink is not allowed: {name}")
            if getattr(info, "file_redir", None) is not None:
                raise ValueError(f"RAR redirected member is not allowed: {name}")
            if info.needs_password():
                raise ValueError("password-protected RAR members are not supported")
            is_directory = bool(info.is_dir())
            is_file = bool(info.is_file())
            if is_directory == is_file:
                raise ValueError(f"unsupported RAR member type: {name}")
            size = getattr(info, "file_size", None)
            compressed = getattr(info, "compress_size", None)
            if not _valid_archive_size(size) or not _valid_archive_size(compressed):
                raise ValueError(f"RAR member has an invalid size: {name}")
            collision_paths.append((name, is_directory))
            if is_file:
                file_count += 1
                if file_count > limits.max_file_count:
                    raise ValueError("RAR file count exceeds the configured safety limit")
                if size > limits.max_file_uncompressed_bytes:
                    raise ValueError(f"RAR member exceeds the per-file size limit: {name}")
                total_bytes += size
                total_compressed += compressed
                if total_bytes > limits.max_total_uncompressed_bytes:
                    raise ValueError("RAR total uncompressed size exceeds the configured safety limit")
                if size and (compressed == 0 or size / compressed > limits.max_compression_ratio):
                    raise ValueError(f"RAR member exceeds the compression-ratio limit: {name}")
            members.append(RarMember(name, size, compressed, is_directory))
        _check_collisions(collision_paths)
        if file_count == 0:
            raise ValueError("RAR archive contains no regular files")
        if total_bytes and (
            total_compressed == 0
            or total_bytes / total_compressed > limits.max_compression_ratio
        ):
            raise ValueError("RAR archive exceeds the total compression-ratio limit")
    for part in checked_parts:
        verify_archive(part.path, part.sha256)
    return RarInspection(
        parts=checked_parts,
        members=tuple(members),
        total_bytes=total_bytes,
        total_compressed_bytes=total_compressed,
    )


def _seven_zip_command(executable: str, archive: Path, member: RarMember) -> list[str]:
    return [
        executable,
        "x",
        "-so",
        "-bd",
        "-bb0",
        "-bsp0",
        "-bse1",
        "-spd",
        "--",
        str(archive),
        member.relative_path,
    ]


def _stream_rar_member(
    archive: Path,
    member: RarMember,
    target: Path,
    *,
    seven_zip_executable: str,
    timeout_seconds: float,
) -> RawFile:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    command = _seven_zip_command(seven_zip_executable, archive, member)
    with os.fdopen(descriptor, "wb") as output:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.PIPE,
                shell=False,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "7z executable is unavailable; install 7-Zip and pass "
                "seven_zip_executable with its trusted executable path"
            ) from error
        except OSError as error:
            raise RuntimeError(
                f"7z could not be started safely ({error.__class__.__name__})"
            ) from error
        try:
            _, _stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            try:
                process.kill()
            except BaseException:
                pass
            try:
                process.communicate()
            except BaseException:
                pass
            raise TimeoutError("7z exceeded the configured per-member timeout") from error
        except BaseException:
            try:
                process.kill()
            except BaseException:
                pass
            try:
                process.communicate()
            except BaseException:
                pass
            raise
        if process.returncode != 0:
            raise ValueError(
                f"7z failed while validating a RAR member (exit code {process.returncode})"
            )
        if _stderr:
            raise ValueError("7z emitted unexpected diagnostic output for a RAR member")
    with target.open("rb") as stream:
        size, sha256 = _hash_stream(stream)
    if size != member.size_bytes:
        raise ValueError(
            f"7z streamed byte count differs from RAR metadata for {member.relative_path!r}"
        )
    return RawFile(member.relative_path, size, sha256)


def _expected_rar_directories(inspection: RarInspection) -> set[str]:
    expected: set[str] = set()
    for member in inspection.members:
        path = PurePosixPath(member.relative_path)
        if member.is_directory:
            expected.add(member.relative_path)
        for parent in path.parents:
            if parent != PurePosixPath("."):
                expected.add(parent.as_posix())
    return expected


def _validate_rar_filesystem(
    root: Path,
    inspection: RarInspection,
    streamed: RawInventory,
) -> RawInventory:
    actual = _filesystem_inventory(root)
    if actual != streamed:
        raise ValueError("extracted filesystem inventory differs from streamed RAR inventory")
    expected_files = {
        member.relative_path: member.size_bytes
        for member in inspection.members
        if not member.is_directory
    }
    actual_files = {item.relative_path: item.size_bytes for item in actual.files}
    if actual_files != expected_files:
        raise ValueError("extracted filesystem files differ from inspected RAR inventory")
    actual_directories: set[str] = set()
    for directory, directory_names, _file_names in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        for name in directory_names:
            actual_directories.add(_safe_name((current / name).relative_to(root).as_posix()))
    if actual_directories != _expected_rar_directories(inspection):
        raise ValueError("extracted filesystem directories differ from inspected RAR inventory")
    return actual


def _destination_exists_and_is_empty(destination: Path, *, promotion: bool = False) -> bool:
    if not os.path.lexists(destination):
        return False
    metadata = destination.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or (reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag)
        or not stat.S_ISDIR(metadata.st_mode)
        or any(destination.iterdir())
    ):
        state = "remain empty" if promotion else "be empty"
        raise ValueError(f"extraction destination must {state}: {destination}")
    return True


def safe_extract_rar_archive(
    parts: Sequence[ArchivePart],
    destination: str | Path,
    *,
    limits: RarExtractionLimits = RarExtractionLimits(),
    seven_zip_executable: str | Path = "7z",
) -> RawInventory:
    """Safely stream an exact RAR volume set into an atomic destination tree."""

    destination_path = Path(destination)
    _destination_exists_and_is_empty(destination_path)
    executable = os.fspath(seven_zip_executable)
    if (
        not isinstance(executable, str)
        or not executable
        or any(unicodedata.category(character) == "Cc" for character in executable)
    ):
        raise ValueError("seven_zip_executable must be a non-empty filesystem path")
    inspection = inspect_rar_archive(parts, limits=limits)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination_path.name}-rar-extract-", dir=destination_path.parent)
    )
    try:
        for directory in sorted(
            _expected_rar_directories(inspection),
            key=lambda item: (len(PurePosixPath(item).parts), item),
        ):
            temporary.joinpath(*PurePosixPath(directory).parts).mkdir(exist_ok=True)
        files: list[RawFile] = []
        for member in inspection.members:
            if member.is_directory:
                continue
            target = temporary.joinpath(*PurePosixPath(member.relative_path).parts)
            files.append(
                _stream_rar_member(
                    inspection.parts[0].path,
                    member,
                    target,
                    seven_zip_executable=executable,
                    timeout_seconds=limits.member_timeout_seconds,
                )
            )
        streamed = _inventory(files)
        actual = _validate_rar_filesystem(temporary, inspection, streamed)
        for part in inspection.parts:
            verify_archive(part.path, part.sha256)
        if _destination_exists_and_is_empty(destination_path, promotion=True):
            destination_path.rmdir()
        temporary.replace(destination_path)
        return actual
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _safe_name(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError(f"unsafe archive member path: {name!r}")
    raw_name = name[:-1] if name.endswith("/") else name
    raw_parts = raw_name.split("/")
    if (
        not raw_name
        or "\\" in name
        or name.startswith("/")
        or any(part in {"", ".", ".."} for part in raw_parts)
        or any(unicodedata.category(character) == "Cc" for character in name)
        or any(character in '<>:"|?*[]' for character in name)
        or any(part.startswith("@") for part in raw_parts)
    ):
        raise ValueError(f"unsafe archive member path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe archive member path: {name!r}")
    for part in path.parts:
        if part.rstrip(" .") != part:
            raise ValueError(f"unsafe archive member path: {name!r}")
        device_name = part.split(".", 1)[0].rstrip(" .").casefold()
        if device_name in _WINDOWS_RESERVED_NAMES:
            raise ValueError(f"unsafe archive member path: {name!r}")
    normalized = path.as_posix().rstrip("/")
    if not normalized:
        raise ValueError(f"unsafe archive member path: {name!r}")
    return normalized


def _check_collisions(paths: list[tuple[str, bool]]) -> None:
    seen: dict[str, tuple[str, bool, bool]] = {}
    for path, is_dir in paths:
        parts = PurePosixPath(path).parts
        for length in range(1, len(parts)):
            parent = PurePosixPath(*parts[:length]).as_posix()
            parent_key = parent.casefold()
            existing_parent = seen.get(parent_key)
            if existing_parent is None:
                seen[parent_key] = (parent, True, False)
            elif not existing_parent[1] or existing_parent[0] != parent:
                raise ValueError(f"archive file/directory collision at {path!r}")
        folded = path.casefold()
        existing = seen.get(folded)
        if existing is not None:
            existing_path, existing_is_dir, existing_is_explicit = existing
            promotes_same_implicit_directory = (
                is_dir
                and existing_is_dir
                and not existing_is_explicit
                and existing_path == path
            )
            if not promotes_same_implicit_directory:
                raise ValueError(f"archive member collision: {existing_path!r} and {path!r}")
        seen[folded] = (path, is_dir, True)
        if not is_dir and any(key.startswith(f"{folded}/") for key in seen if key != folded):
            raise ValueError(f"archive file/directory collision at {path!r}")


def _inventory(files: list[RawFile]) -> RawInventory:
    ordered = tuple(sorted(files, key=lambda item: item.relative_path))
    canonical = json.dumps(
        [
            {"relativePath": item.relative_path, "sizeBytes": item.size_bytes, "sha256": item.sha256}
            for item in ordered
        ],
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return RawInventory(
        files=ordered,
        inventory_sha256=hashlib.sha256(canonical).hexdigest(),
        total_bytes=sum(item.size_bytes for item in ordered),
    )


def _hash_stream(stream: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def _consume_stream(stream: BinaryIO, target: Path | None) -> RawFile:
    digest = hashlib.sha256()
    size = 0
    output = None
    try:
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            output = os.fdopen(descriptor, "wb")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
    finally:
        if output is not None:
            output.close()
    relative_path = target.name if target is not None else ""
    return RawFile(relative_path, size, digest.hexdigest())


def _scan_zip(archive: Path, destination: Path | None) -> RawInventory:
    files: list[RawFile] = []
    with zipfile.ZipFile(archive) as container:
        members: list[tuple[zipfile.ZipInfo, str, bool]] = []
        for info in container.infolist():
            name = _safe_name(info.filename)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"archive symlink is not allowed: {name}")
            members.append((info, name, info.is_dir()))
        _check_collisions([(name, is_dir) for _, name, is_dir in members])
        for info, name, is_dir in members:
            target = destination.joinpath(*PurePosixPath(name).parts) if destination else None
            if is_dir:
                if target is not None:
                    target.mkdir(parents=True, exist_ok=True)
                continue
            with container.open(info, "r") as stream:
                raw_file = _consume_stream(stream, target)
            files.append(RawFile(name, raw_file.size_bytes, raw_file.sha256))
    if not files:
        raise ValueError("archive contains no regular files")
    return _inventory(files)


def _scan_tar(archive: Path, destination: Path | None) -> RawInventory:
    files: list[RawFile] = []
    with tarfile.open(archive, "r:*") as container:
        members: list[tuple[tarfile.TarInfo, str, bool]] = []
        for info in container.getmembers():
            name = _safe_name(info.name)
            if info.issym() or info.islnk():
                raise ValueError(f"archive symlink is not allowed: {name}")
            if not (info.isdir() or info.isfile()):
                raise ValueError(f"unsupported archive member type: {name}")
            members.append((info, name, info.isdir()))
        _check_collisions([(name, is_dir) for _, name, is_dir in members])
        for info, name, is_dir in members:
            target = destination.joinpath(*PurePosixPath(name).parts) if destination else None
            if is_dir:
                if target is not None:
                    target.mkdir(parents=True, exist_ok=True)
                continue
            stream = container.extractfile(info)
            if stream is None:
                raise ValueError(f"archive member cannot be read: {name}")
            with stream:
                raw_file = _consume_stream(stream, target)
            files.append(RawFile(name, raw_file.size_bytes, raw_file.sha256))
    if not files:
        raise ValueError("archive contains no regular files")
    return _inventory(files)


def _scan_archive(archive: Path, destination: Path | None = None) -> RawInventory:
    if zipfile.is_zipfile(archive):
        return _scan_zip(archive, destination)
    if tarfile.is_tarfile(archive):
        return _scan_tar(archive, destination)
    raise ValueError(f"unsupported archive format: {archive.name}")


def _filesystem_inventory(root: Path) -> RawInventory:
    files: list[RawFile] = []
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for directory, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        for name in directory_names:
            path = current / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or (
                reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag
            ):
                raise ValueError(f"extracted filesystem contains a link: {path}")
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValueError(f"extracted filesystem contains unsupported entry: {path}")
        for name in file_names:
            path = current / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or (
                reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag
            ):
                raise ValueError(f"extracted filesystem contains a link: {path}")
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"extracted filesystem contains unsupported entry: {path}")
            relative_path = _safe_name(path.relative_to(root).as_posix())
            with path.open("rb") as stream:
                size, sha256 = _hash_stream(stream)
            files.append(RawFile(relative_path, size, sha256))
    if not files:
        raise ValueError("extracted filesystem contains no regular files")
    return _inventory(files)


def inspect_archive(path: str | Path) -> RawInventory:
    archive = Path(path)
    if not archive.is_file():
        raise FileNotFoundError(f"dataset archive does not exist: {archive}")
    return _scan_archive(archive)


def safe_extract_archive(
    path: str | Path,
    destination: str | Path,
    *,
    expected_sha256: str | None = None,
) -> RawInventory:
    """Safely extract ZIP/TAR into an absent or empty destination atomically."""

    archive = Path(path)
    destination_path = Path(destination)
    if destination_path.exists():
        if not destination_path.is_dir() or any(destination_path.iterdir()):
            raise ValueError(f"extraction destination must be empty: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    archive_hash_before = (
        verify_archive(archive, expected_sha256)
        if expected_sha256 is not None
        else hash_file(archive)
    )
    expected = inspect_archive(archive)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination_path.name}-extract-", dir=destination_path.parent))
    try:
        streamed = _scan_archive(archive, temporary)
        if streamed != expected:
            raise ValueError("extracted raw inventory differs from inspected archive")
        actual = _filesystem_inventory(temporary)
        if actual != streamed:
            raise ValueError("extracted filesystem inventory differs from archive stream inventory")
        if hash_file(archive) != archive_hash_before:
            raise ValueError("archive changed during extraction")
        if destination_path.exists():
            destination_path.rmdir()
        temporary.replace(destination_path)
        return actual
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
