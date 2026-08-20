"""Archive integrity, safe extraction, and raw-file inventory helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO


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


def _safe_name(name: str) -> str:
    if not name or "\\" in name or ":" in name or name.startswith("/"):
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
    seen: dict[str, tuple[str, bool]] = {}
    file_paths: set[str] = set()
    for path, is_dir in paths:
        folded = path.casefold()
        if folded in seen:
            raise ValueError(f"archive member collision: {seen[folded][0]!r} and {path!r}")
        for parent in PurePosixPath(path).parents:
            if parent == PurePosixPath("."):
                continue
            if parent.as_posix().casefold() in file_paths:
                raise ValueError(f"archive file/directory collision at {path!r}")
        seen[folded] = (path, is_dir)
        if not is_dir:
            file_paths.add(folded)
    all_paths = set(seen)
    for file_path in file_paths:
        if any(other.startswith(f"{file_path}/") for other in all_paths):
            raise ValueError(f"archive file/directory collision at {seen[file_path][0]!r}")


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
