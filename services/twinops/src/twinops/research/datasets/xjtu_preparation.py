"""Fail-closed preparation boundary for the official XJTU-SY volumes."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from twinops.research.downloads import (
    ArchivePart,
    RarExtractionLimits,
    RawInventory,
    inspect_rar_archive,
    safe_extract_rar_archive,
)
from twinops.research.metadata import load_metadata


_OFFICIAL_PARTS = (
    (
        "XJTU-SY_Bearing_Datasets.part01.rar",
        744_488_960,
        "c500657353f089a4ab50212ff4ddfc7b982729e92e2b127440c8ad881d80b968",
    ),
    (
        "XJTU-SY_Bearing_Datasets.part02.rar",
        744_488_960,
        "4dfa6286a8e9c7cec1e925b347642349f36e27ab3f703c90d1d08977b7b4f61f",
    ),
    (
        "XJTU-SY_Bearing_Datasets.part03.rar",
        744_488_960,
        "6929f531284f79e0209246b4ee23b23dd8d4faac1c0c3ff8fb131cda4a18bd3a",
    ),
    (
        "XJTU-SY_Bearing_Datasets.part04.rar",
        744_488_960,
        "2245825acd29bed3b95e7a77879a3fbadf20f4ad4f99486384c714174621597d",
    ),
    (
        "XJTU-SY_Bearing_Datasets.part05.rar",
        744_488_960,
        "e1b0a41a32b865e48ea7981c56f952a960d94335f3496b72eb4a65932f1671bd",
    ),
    (
        "XJTU-SY_Bearing_Datasets.part06.rar",
        722_155_640,
        "df1854821a9d481104476379f7bc045ea1e101427c6e36145cd7677dc7c4a684",
    ),
)
_TASK_LIMITS = RarExtractionLimits(max_total_uncompressed_bytes=64 * 1024**3)
_ROOT = "XJTU-SY_Bearing_Datasets"
_PDF_PATH = f"{_ROOT}/Introduction_to_XJTU-SY_Bearing_Dataset.pdf"
_EXPECTED_TOTAL_BYTES = 12_220_812_451
_SAMPLES_PER_WINDOW = 32_768
_SAMPLING_HZ = 25_600
_PREPARATION_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SEQUENCE_NAME = re.compile(r"^[1-9][0-9]*\.csv$")
_AUTHOR_DOI = "10.3901/JME.2019.16.001"


@dataclass(frozen=True, slots=True)
class _BearingSpec:
    condition_index: int
    bearing_index: int
    condition_directory: str
    bearing_directory: str
    file_count: int
    rpm: int
    load_kn: int
    terminal_components: tuple[str, ...]

    @property
    def condition_id(self) -> str:
        return f"condition-{self.condition_index}"

    @property
    def bearing_id(self) -> str:
        return f"xjtu-sy-bearing-{self.condition_index}-{self.bearing_index}"

    @property
    def run_id(self) -> str:
        return f"xjtu-sy-run-to-failure-{self.condition_index}-{self.bearing_index}"


_BEARING_SPECS = (
    _BearingSpec(1, 1, "35Hz12kN", "Bearing1_1", 123, 2_100, 12, ("outer_race",)),
    _BearingSpec(1, 2, "35Hz12kN", "Bearing1_2", 161, 2_100, 12, ("outer_race",)),
    _BearingSpec(1, 3, "35Hz12kN", "Bearing1_3", 158, 2_100, 12, ("outer_race",)),
    _BearingSpec(1, 4, "35Hz12kN", "Bearing1_4", 122, 2_100, 12, ("cage",)),
    _BearingSpec(
        1,
        5,
        "35Hz12kN",
        "Bearing1_5",
        52,
        2_100,
        12,
        ("inner_race", "outer_race"),
    ),
    _BearingSpec(2, 1, "37.5Hz11kN", "Bearing2_1", 491, 2_250, 11, ("inner_race",)),
    _BearingSpec(2, 2, "37.5Hz11kN", "Bearing2_2", 161, 2_250, 11, ("outer_race",)),
    _BearingSpec(2, 3, "37.5Hz11kN", "Bearing2_3", 533, 2_250, 11, ("cage",)),
    _BearingSpec(2, 4, "37.5Hz11kN", "Bearing2_4", 42, 2_250, 11, ("outer_race",)),
    _BearingSpec(2, 5, "37.5Hz11kN", "Bearing2_5", 339, 2_250, 11, ("outer_race",)),
    _BearingSpec(3, 1, "40Hz10kN", "Bearing3_1", 2_538, 2_400, 10, ("outer_race",)),
    _BearingSpec(
        3,
        2,
        "40Hz10kN",
        "Bearing3_2",
        2_496,
        2_400,
        10,
        ("inner_race", "rolling_element", "cage", "outer_race"),
    ),
    _BearingSpec(3, 3, "40Hz10kN", "Bearing3_3", 371, 2_400, 10, ("inner_race",)),
    _BearingSpec(3, 4, "40Hz10kN", "Bearing3_4", 1_515, 2_400, 10, ("inner_race",)),
    _BearingSpec(3, 5, "40Hz10kN", "Bearing3_5", 114, 2_400, 10, ("outer_race",)),
)


@dataclass(frozen=True, slots=True)
class _PathObjectIdentity:
    path: Path
    device: int
    inode: int
    mode: int
    file_attributes: int
    reparse_tag: int


@dataclass(frozen=True, slots=True)
class _ExecutableAttestation:
    path: Path
    ancestors: tuple[_PathObjectIdentity, ...]
    file_identity: _PathObjectIdentity
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _OwnedDirectory:
    path: Path
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class _DirectoryCreationGuard:
    device: int
    inode: int
    mode: int
    file_attributes: int
    reparse_tag: int
    ctime_ns: int | None


@dataclass(frozen=True, slots=True)
class _InspectedMemberBinding:
    relative_path: str
    size_bytes: int
    kind: str


@dataclass(frozen=True, slots=True)
class _PublicationManifestEntry:
    relative_path: str
    kind: str
    size_bytes: int | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class _ReconstructedRawFile:
    relative_path: str
    size_bytes: int
    sha256: str


def _valid_identity_values(device: object, inode: object) -> tuple[int, int]:
    if (
        not isinstance(device, int)
        or isinstance(device, bool)
        or device <= 0
        or not isinstance(inode, int)
        or isinstance(inode, bool)
        or inode <= 0
    ):
        raise ValueError("XJTU-SY path has an invalid filesystem identity")
    return device, inode


def _valid_identity(metadata: object) -> tuple[int, int]:
    return _valid_identity_values(
        getattr(metadata, "st_dev", None), getattr(metadata, "st_ino", None)
    )


def _plain_directory_metadata(path: Path):
    metadata = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or (reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag)
    ):
        raise ValueError(f"XJTU-SY publication path must be a regular directory: {path.name}")
    return metadata


def _directory_identity(path: Path) -> tuple[int, int]:
    first = _valid_identity(_plain_directory_metadata(path))
    second = _valid_identity(_plain_directory_metadata(path))
    if first != second:
        raise ValueError("XJTU-SY publication path filesystem identity is unstable")
    return first


def _directory_creation_guard(path: Path) -> _DirectoryCreationGuard:
    def snapshot() -> _DirectoryCreationGuard:
        metadata = _plain_directory_metadata(path)
        device, inode = _valid_identity(metadata)
        return _DirectoryCreationGuard(
            device=device,
            inode=inode,
            mode=metadata.st_mode,
            file_attributes=getattr(metadata, "st_file_attributes", 0),
            reparse_tag=getattr(metadata, "st_reparse_tag", 0),
            ctime_ns=getattr(metadata, "st_ctime_ns", None),
        )

    first = snapshot()
    second = snapshot()
    if first != second:
        raise ValueError("XJTU-SY staging creation identity is unstable")
    return first


def _bind_owned_directory(
    path: Path,
    creation_guard: _DirectoryCreationGuard,
    acquired_identity: tuple[int, int],
) -> _OwnedDirectory:
    try:
        device, inode = acquired_identity
    except (TypeError, ValueError) as error:
        raise ValueError("XJTU-SY staging acquired an invalid filesystem identity") from error
    identity = _valid_identity_values(device, inode)
    observed_guard = _directory_creation_guard(path)
    if (
        observed_guard != creation_guard
        or identity != (creation_guard.device, creation_guard.inode)
    ):
        raise ValueError("XJTU-SY staging changed between creation and ownership")
    return _OwnedDirectory(path, *identity)


def _same_identity(path: Path, owned: _OwnedDirectory) -> bool:
    if not os.path.lexists(path):
        return False
    try:
        first = _valid_identity(_plain_directory_metadata(path))
        second = _valid_identity(_plain_directory_metadata(path))
        return first == second == (owned.device, owned.inode)
    except (OSError, ValueError):
        return False


def _plain_path_identity(path: Path, *, directory: bool) -> _PathObjectIdentity:
    metadata = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not expected_type(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or (reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag)
    ):
        kind = "directory" if directory else "file"
        raise ValueError(f"trusted 7z path component must be a regular {kind}")
    device, inode = _valid_identity(metadata)
    return _PathObjectIdentity(
        path=path,
        device=device,
        inode=inode,
        mode=metadata.st_mode,
        file_attributes=getattr(metadata, "st_file_attributes", 0),
        reparse_tag=getattr(metadata, "st_reparse_tag", 0),
    )


def _stable_plain_path_identity(path: Path, *, directory: bool) -> _PathObjectIdentity:
    first = _plain_path_identity(path, directory=directory)
    second = _plain_path_identity(path, directory=directory)
    if first != second:
        raise ValueError("trusted 7z path component identity is unstable")
    return first


def _executable_ancestors(path: Path) -> tuple[Path, ...]:
    ancestors = tuple(reversed(path.parent.parents)) + (path.parent,)
    return tuple(dict.fromkeys(ancestors))


def _hash_file(path: Path) -> tuple[int, str]:
    size = 0
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _attest_executable(path: Path) -> _ExecutableAttestation:
    ancestors_before = tuple(
        _stable_plain_path_identity(ancestor, directory=True)
        for ancestor in _executable_ancestors(path)
    )
    file_before = _stable_plain_path_identity(path, directory=False)
    size_bytes, sha256 = _hash_file(path)
    file_after = _stable_plain_path_identity(path, directory=False)
    ancestors_after = tuple(
        _stable_plain_path_identity(ancestor, directory=True)
        for ancestor in _executable_ancestors(path)
    )
    if file_before != file_after or ancestors_before != ancestors_after:
        raise ValueError("trusted 7z executable identity changed during attestation")
    return _ExecutableAttestation(
        path=path,
        ancestors=ancestors_before,
        file_identity=file_before,
        size_bytes=size_bytes,
        sha256=sha256,
    )


def _revalidate_executable(config: "XjtuSyPreparationConfig") -> Path:
    expected = config._seven_zip_attestation
    try:
        observed = _attest_executable(expected.path)
    except (OSError, ValueError) as error:
        raise ValueError("trusted 7z executable changed since config attestation") from error
    if observed != expected:
        raise ValueError("trusted 7z executable changed since config attestation")
    return expected.path


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_member_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("XJTU-SY archive inspection returned an invalid member path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.as_posix() != normalized or path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise ValueError("XJTU-SY archive member path is not canonical")
    return normalized


def _spec_value(spec: Any, name: str) -> Any:
    return getattr(spec, name)


def _condition_id(spec: Any) -> str:
    return f"condition-{int(_spec_value(spec, 'condition_index'))}"


def _bearing_id(spec: Any) -> str:
    return (
        f"xjtu-sy-bearing-{int(_spec_value(spec, 'condition_index'))}-"
        f"{int(_spec_value(spec, 'bearing_index'))}"
    )


def _run_id(spec: Any) -> str:
    return (
        f"xjtu-sy-run-to-failure-{int(_spec_value(spec, 'condition_index'))}-"
        f"{int(_spec_value(spec, 'bearing_index'))}"
    )


def _csv_path(spec: Any, sequence: int) -> str:
    return (
        f"{_ROOT}/{_spec_value(spec, 'condition_directory')}/"
        f"{_spec_value(spec, 'bearing_directory')}/{sequence}.csv"
    )


def _expected_directories() -> tuple[str, ...]:
    directories = {_ROOT}
    for spec in _BEARING_SPECS:
        condition = f"{_ROOT}/{_spec_value(spec, 'condition_directory')}"
        directories.add(condition)
        directories.add(f"{condition}/{_spec_value(spec, 'bearing_directory')}")
    return tuple(sorted(directories))


def _expected_csv_paths() -> tuple[str, ...]:
    paths = []
    for spec in _BEARING_SPECS:
        paths.extend(
            _csv_path(spec, sequence)
            for sequence in range(1, int(_spec_value(spec, "file_count")) + 1)
        )
    return tuple(sorted(paths))


def _inspection_parts_match(
    expected: tuple[ArchivePart, ...], observed: object
) -> bool:
    if not isinstance(observed, tuple) or len(observed) != len(expected):
        return False
    try:
        return all(
            isinstance(actual, ArchivePart)
            and actual.sha256 == supplied.sha256
            and actual.path.resolve(strict=True) == supplied.path.resolve(strict=True)
            for supplied, actual in zip(expected, observed, strict=True)
        )
    except OSError:
        return False


def _validate_inspection(
    config: "XjtuSyPreparationConfig", inspection: Any
) -> tuple[_InspectedMemberBinding, ...]:
    if not _inspection_parts_match(
        config.archive_parts, getattr(inspection, "parts", None)
    ):
        raise ValueError("XJTU-SY archive parts differ from the ordered official binding")
    if getattr(inspection, "total_bytes", None) != _EXPECTED_TOTAL_BYTES:
        raise ValueError("XJTU-SY archive uncompressed byte count is unexpected")
    members = getattr(inspection, "members", None)
    if not isinstance(members, tuple):
        raise ValueError("XJTU-SY archive members must be immutable")

    directories: list[str] = []
    files: list[str] = []
    file_sizes: dict[str, int] = {}
    observed_total = 0
    for member in members:
        path = _canonical_member_path(getattr(member, "relative_path", None))
        is_directory = getattr(member, "is_directory", None)
        size = getattr(member, "size_bytes", None)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError("XJTU-SY archive member has an invalid byte count")
        if is_directory is True:
            directories.append(path)
        elif is_directory is False:
            files.append(path)
            file_sizes[path] = size
            observed_total += size
        else:
            raise ValueError("XJTU-SY archive member type is unknown")
    if len(set(directories + files)) != len(directories) + len(files):
        raise ValueError("XJTU-SY archive contains a duplicate member path")
    if tuple(sorted(directories)) != _expected_directories():
        raise ValueError("XJTU-SY archive directory boundary is unexpected")
    if observed_total != _EXPECTED_TOTAL_BYTES:
        raise ValueError("XJTU-SY archive member bytes do not match the total")

    expected_csv = _expected_csv_paths()
    if len(files) != len(expected_csv) + 1:
        raise ValueError("XJTU-SY archive regular-file count is unexpected")
    if files.count(_PDF_PATH) != 1:
        raise ValueError("XJTU-SY archive must contain exactly one official PDF")

    spec_by_directory = {
        (
            str(_spec_value(spec, "condition_directory")),
            str(_spec_value(spec, "bearing_directory")),
        ): spec
        for spec in _BEARING_SPECS
    }
    sequences: dict[tuple[str, str], set[int]] = {
        key: set() for key in spec_by_directory
    }
    for path_text in files:
        if path_text == _PDF_PATH:
            continue
        path = PurePosixPath(path_text)
        if len(path.parts) != 4 or path.parts[0] != _ROOT:
            raise ValueError("XJTU-SY archive file escaped its source boundary")
        key = (path.parts[1], path.parts[2])
        spec = spec_by_directory.get(key)
        if spec is None or _SEQUENCE_NAME.fullmatch(path.name) is None:
            raise ValueError("XJTU-SY archive has an unexpected CSV boundary or sequence name")
        sequence = int(path.stem)
        if str(sequence) != path.stem or sequence in sequences[key]:
            raise ValueError("XJTU-SY archive sequence names must be unique and unpadded")
        sequences[key].add(sequence)
    for key, spec in spec_by_directory.items():
        expected = set(range(1, int(_spec_value(spec, "file_count")) + 1))
        if sequences[key] != expected:
            raise ValueError("XJTU-SY archive bearing sequence is not contiguous")
    if tuple(sorted(files)) != tuple(sorted((*expected_csv, _PDF_PATH))):
        raise ValueError("XJTU-SY archive file boundary is unexpected")
    return tuple(
        _InspectedMemberBinding(
            relative_path=path,
            size_bytes=file_sizes[path],
            kind="source_document" if path == _PDF_PATH else "signal_window",
        )
        for path in sorted(files)
    )


def _inventory_binding(inventory: RawInventory) -> list[dict[str, object]]:
    return [
        {
            "relativePath": item.relative_path,
            "sizeBytes": item.size_bytes,
            "sha256": item.sha256,
        }
        for item in sorted(inventory.files, key=lambda value: value.relative_path)
    ]


def _validate_inventory(
    inventory: RawInventory,
    expected_members: tuple[_InspectedMemberBinding, ...],
) -> None:
    if not isinstance(inventory, RawInventory):
        raise TypeError("XJTU-SY extraction must return RawInventory")
    binding = _inventory_binding(inventory)
    expected_sizes = {
        item.relative_path: item.size_bytes for item in expected_members
    }
    paths = tuple(item["relativePath"] for item in binding)
    if paths != tuple(sorted(expected_sizes)):
        raise ValueError("XJTU-SY raw inventory does not match archive inspection")
    for item in binding:
        if (
            not isinstance(item["sizeBytes"], int)
            or isinstance(item["sizeBytes"], bool)
            or item["sizeBytes"] < 0
            or not isinstance(item["sha256"], str)
            or _SHA256.fullmatch(item["sha256"]) is None
        ):
            raise ValueError("XJTU-SY raw inventory entry is invalid")
        if item["sizeBytes"] != expected_sizes[str(item["relativePath"])]:
            raise ValueError(
                "XJTU-SY raw inventory member size differs from archive inspection"
            )
    expected_hash = _sha256_bytes(_canonical_json_bytes(binding))
    if inventory.inventory_sha256 != expected_hash:
        raise ValueError("XJTU-SY raw inventory hash is invalid")
    if inventory.total_bytes != sum(int(item["sizeBytes"]) for item in binding):
        raise ValueError("XJTU-SY raw inventory byte count is invalid")
    if inventory.total_bytes != _EXPECTED_TOTAL_BYTES:
        raise ValueError("XJTU-SY raw inventory byte count differs from inspection")


def _filesystem_relative_files(root: Path) -> tuple[str, ...]:
    files: list[str] = []
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for directory, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        current = Path(directory)
        for name in directory_names:
            path = current / name
            metadata = path.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or (
                    reparse_flag
                    and getattr(metadata, "st_file_attributes", 0) & reparse_flag
                )
            ):
                raise ValueError("XJTU-SY prepared tree contains an unsafe directory")
        for name in file_names:
            path = current / name
            metadata = path.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or (
                    reparse_flag
                    and getattr(metadata, "st_file_attributes", 0) & reparse_flag
                )
            ):
                raise ValueError("XJTU-SY prepared tree contains an unsafe file")
            files.append(path.relative_to(root).as_posix())
    return tuple(sorted(files))


def _validate_numeric_csv(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> None:
    metadata = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or (reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag)
    ):
        raise ValueError(f"XJTU-SY CSV must be a regular file: {path.name}")

    digest = hashlib.sha256()
    size = 0
    rows = 0
    with path.open("rb") as stream:
        for raw_line in stream:
            digest.update(raw_line)
            size += len(raw_line)
            stripped = raw_line.strip()
            if not stripped:
                raise ValueError(f"XJTU-SY CSV contains a blank row: {path.name}")
            try:
                tokens = stripped.decode("ascii").split(",")
            except UnicodeDecodeError as error:
                raise ValueError(f"XJTU-SY CSV is not ASCII numeric data: {path.name}") from error
            if len(tokens) != 2 or any(not token.strip() for token in tokens):
                raise ValueError(f"XJTU-SY CSV column count must be 2: {path.name}")
            try:
                values = tuple(float(token) for token in tokens)
            except ValueError as error:
                raise ValueError(f"XJTU-SY CSV contains nonnumeric data: {path.name}") from error
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"XJTU-SY CSV contains non-finite data: {path.name}")
            rows += 1
    if rows != _SAMPLES_PER_WINDOW:
        raise ValueError(
            f"XJTU-SY CSV row count must be {_SAMPLES_PER_WINDOW}: {path.name}"
        )
    if size != expected_size or digest.hexdigest() != expected_sha256:
        raise ValueError(f"XJTU-SY CSV differs from its raw inventory: {path.name}")


def _validate_source_document(
    path: Path, *, expected_size: int, expected_sha256: str
) -> str:
    metadata = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or (reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag)
    ):
        raise ValueError("XJTU-SY source PDF must be a regular file")
    size, digest = _hash_file(path)
    if size != expected_size or digest != expected_sha256:
        raise ValueError("XJTU-SY source PDF differs from its raw inventory")
    return digest


def _validate_raw_tree(root: Path, inventory: RawInventory) -> str:
    root_identity = _directory_identity(root)
    inventory_files = {item.relative_path: item for item in inventory.files}
    if _filesystem_relative_files(root) != tuple(sorted(inventory_files)):
        raise ValueError("XJTU-SY filesystem differs from raw inventory")
    pdf_hash: str | None = None
    for relative_path in sorted(inventory_files):
        item = inventory_files[relative_path]
        path = root.joinpath(*PurePosixPath(relative_path).parts)
        if relative_path == _PDF_PATH:
            pdf_hash = _validate_source_document(
                path,
                expected_size=item.size_bytes,
                expected_sha256=item.sha256,
            )
        else:
            _validate_numeric_csv(
                path,
                expected_size=item.size_bytes,
                expected_sha256=item.sha256,
            )
    if pdf_hash is None:
        raise ValueError("XJTU-SY source PDF is absent from the raw inventory")
    if _directory_identity(root) != root_identity:
        raise ValueError("XJTU-SY raw root identity changed during validation")
    return pdf_hash


def _spec_by_csv_path() -> dict[str, tuple[Any, int]]:
    mapping: dict[str, tuple[Any, int]] = {}
    for spec in _BEARING_SPECS:
        for sequence in range(1, int(_spec_value(spec, "file_count")) + 1):
            mapping[_csv_path(spec, sequence)] = (spec, sequence)
    return mapping


def _condition_evidence() -> list[dict[str, object]]:
    conditions: dict[int, Any] = {}
    for spec in _BEARING_SPECS:
        conditions.setdefault(int(_spec_value(spec, "condition_index")), spec)
    return [
        {
            "conditionId": _condition_id(spec),
            "sourceDirectory": str(_spec_value(spec, "condition_directory")),
            "rotationalSpeedRpm": int(_spec_value(spec, "rpm")),
            "radialLoad": {
                "value": int(_spec_value(spec, "load_kn")),
                "unit": "kN",
            },
        }
        for _, spec in sorted(conditions.items())
    ]


def _bearing_evidence() -> list[dict[str, object]]:
    return [
        {
            "bearingId": _bearing_id(spec),
            "runId": _run_id(spec),
            "conditionId": _condition_id(spec),
            "sourceDirectory": str(_spec_value(spec, "bearing_directory")),
            "sourceFileCount": int(_spec_value(spec, "file_count")),
            "terminalOutcome": {
                "scope": "bearing_terminal_evidence",
                "description": "+".join(_spec_value(spec, "terminal_components")),
                "components": list(_spec_value(spec, "terminal_components")),
                "sourceDoi": _AUTHOR_DOI,
            },
        }
        for spec in _BEARING_SPECS
    ]


def _registry_binding() -> dict[str, object]:
    return {
        "samplingHz": _SAMPLING_HZ,
        "samplesPerWindow": _SAMPLES_PER_WINDOW,
        "observationCadence": {"value": 1, "unit": "minute"},
        "conditions": _condition_evidence(),
        "bearings": _bearing_evidence(),
    }


@dataclass(frozen=True, slots=True)
class XjtuSyPreparationConfig:
    """Caller-authorized inputs for one deterministic XJTU-SY publication."""

    archive_parts: tuple[ArchivePart, ...]
    seven_zip_executable: Path
    destination_root: Path
    extraction_limits: RarExtractionLimits = _TASK_LIMITS
    _seven_zip_attestation: _ExecutableAttestation = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.archive_parts, tuple) or len(self.archive_parts) != 6:
            raise ValueError("XJTU-SY requires the six ordered official archive parts")
        archive_paths: list[Path] = []
        for index, (archive, expected) in enumerate(
            zip(self.archive_parts, _OFFICIAL_PARTS, strict=True), start=1
        ):
            expected_name, _, expected_sha256 = expected
            if not isinstance(archive, ArchivePart):
                raise TypeError(f"XJTU-SY archive part {index} must be an ArchivePart")
            if not archive.path.is_absolute():
                raise ValueError(f"XJTU-SY archive part {index} path must be absolute")
            if archive.path.name != expected_name or archive.sha256 != expected_sha256:
                raise ValueError(
                    f"XJTU-SY archive part {index} does not match the official binding"
                )
            archive_paths.append(archive.path)
        if len({os.path.normcase(os.fspath(path)) for path in archive_paths}) != 6:
            raise ValueError("XJTU-SY archive paths must be six distinct absolute paths")
        if self.extraction_limits != _TASK_LIMITS:
            raise ValueError("XJTU-SY preparation requires the task-owned 64 GiB limits")

        executable = Path(self.seven_zip_executable)
        destination = Path(self.destination_root)
        if not executable.is_absolute() or not destination.is_absolute():
            raise ValueError("seven_zip_executable and destination_root must be absolute paths")
        try:
            executable_attestation = _attest_executable(executable)
        except (OSError, ValueError) as error:
            raise ValueError(
                "seven_zip_executable must identify a caller-trusted regular "
                "non-reparse file with regular non-reparse directory ancestors"
            ) from error
        object.__setattr__(self, "seven_zip_executable", executable)
        object.__setattr__(self, "destination_root", destination)
        object.__setattr__(self, "_seven_zip_attestation", executable_attestation)


def _metadata_payload(
    config: XjtuSyPreparationConfig,
    inventory: RawInventory,
    pdf_sha256: str,
) -> dict[str, object]:
    metadata_binding = {
        "schemaVersion": 1,
        "preparationSchemaVersion": _PREPARATION_SCHEMA_VERSION,
        "sourceArchiveSha256": [part.sha256 for part in config.archive_parts],
        "rawInventorySha256": inventory.inventory_sha256,
        "registry": _registry_binding(),
    }
    metadata_id = f"xjtu-sy-metadata-v1-{_sha256_bytes(_canonical_json_bytes(metadata_binding))}"
    spec_paths = _spec_by_csv_path()
    files: dict[str, dict[str, object]] = {}
    for item in sorted(inventory.files, key=lambda value: value.relative_path):
        if item.relative_path == _PDF_PATH:
            files[item.relative_path] = {
                "kind": "source_document",
                "mediaType": "application/pdf",
                "sha256": pdf_sha256,
            }
            continue
        try:
            spec, source_sequence = spec_paths[item.relative_path]
        except KeyError as error:  # pragma: no cover - inventory validation precedes metadata
            raise RuntimeError("validated XJTU-SY path has no registry entry") from error
        files[item.relative_path] = {
            "kind": "signal_window",
            "bearingId": _bearing_id(spec),
            "runId": _run_id(spec),
            "conditionId": _condition_id(spec),
            "sequenceIndex": source_sequence - 1,
            "sourceSequenceNumber": source_sequence,
            "startedAt": None,
            "timestampQuality": "unavailable",
            "windowStateLabel": "unknown",
            "terminalFailureMode": None,
            "lifeFraction": None,
            "columns": {"0": "horizontal", "1": "vertical"},
            "hasHeader": False,
            "rpm": int(_spec_value(spec, "rpm")),
            "load": None,
        }
    return {
        "schemaVersion": 1,
        "datasetId": "xjtu-sy",
        "metadataId": metadata_id,
        "samplingHz": _SAMPLING_HZ,
        "samplesPerWindow": _SAMPLES_PER_WINDOW,
        "accelerationUnit": "unknown",
        "observationCadence": {"value": 1, "unit": "minute"},
        "conditions": _condition_evidence(),
        "bearingEvidence": _bearing_evidence(),
        "files": files,
    }


def _generation_id(
    config: XjtuSyPreparationConfig,
    inventory: RawInventory,
    metadata_sha256: str,
) -> str:
    binding = {
        "datasetId": "xjtu-sy",
        "preparationSchemaVersion": _PREPARATION_SCHEMA_VERSION,
        "metadataSchemaVersion": 1,
        "sourceArchiveSha256": [part.sha256 for part in config.archive_parts],
        "rawInventorySha256": inventory.inventory_sha256,
        "metadataSha256": metadata_sha256,
        "registry": _registry_binding(),
    }
    return f"xjtu-sy-v1-{_sha256_bytes(_canonical_json_bytes(binding))}"


def _compact_inventory(inventory: RawInventory) -> dict[str, object]:
    ordered = sorted(inventory.files, key=lambda value: value.relative_path)
    return {
        "inventorySha256": inventory.inventory_sha256,
        "fileCount": len(ordered),
        "totalBytes": inventory.total_bytes,
        "csvFileCount": len(ordered) - 1,
        "sourceDocumentCount": 1,
        "firstPath": ordered[0].relative_path,
        "lastPath": ordered[-1].relative_path,
    }


def _attestation_payload(
    config: XjtuSyPreparationConfig,
    generation_id: str,
    inventory: RawInventory,
    metadata_sha256: str,
    pdf_sha256: str,
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "preparationSchemaVersion": _PREPARATION_SCHEMA_VERSION,
        "datasetId": "xjtu-sy",
        "status": "prepared_semantically_gated",
        "generationId": generation_id,
        "source": {
            "format": "rar5-multipart",
            "volumeCount": 6,
            "archiveParts": [
                {
                    "relativePath": name,
                    "sizeBytes": size,
                    "sha256": digest,
                }
                for name, size, digest in _OFFICIAL_PARTS
            ],
        },
        "rawInventory": _compact_inventory(inventory),
        "metadata": {"schemaVersion": 1, "sha256": metadata_sha256},
        "sourceDocument": {
            "relativePath": _PDF_PATH,
            "sha256": pdf_sha256,
            "kind": "source_document",
        },
        "conditions": _condition_evidence(),
        "bearingEvidence": _bearing_evidence(),
        "semanticGates": {
            "accelerationUnit": "unknown",
            "headerNames": "unknown",
            "axes": "horizontal_vertical_author_confirmed",
            "sourceTimezone": "unknown",
            "absoluteTimestamps": "unknown",
            "physicalFailureTime": "unknown",
            "windowState": "unknown",
            "faultOnset": "unknown",
            "severity": "unknown",
            "lifeFraction": None,
            "trueRul": "unknown",
            "confirmatoryMetricsEnabled": False,
            "supervisedMetricsEnabled": False,
            "transferMetricsEnabled": False,
            "rulMetricsEnabled": False,
        },
    }


def _write_new(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _sha256_bytes(payload)


def _expected_publication_manifest(
    inventory: RawInventory,
    metadata_bytes: bytes,
    attestation_bytes: bytes,
) -> tuple[_PublicationManifestEntry, ...]:
    directories = {"raw"}
    entries: list[_PublicationManifestEntry] = []
    for item in inventory.files:
        relative_path = PurePosixPath("raw", item.relative_path)
        directories.update(
            parent.as_posix()
            for parent in relative_path.parents
            if parent != PurePosixPath(".")
        )
        entries.append(
            _PublicationManifestEntry(
                relative_path=relative_path.as_posix(),
                kind="file",
                size_bytes=item.size_bytes,
                sha256=item.sha256,
            )
        )
    entries.extend(
        (
            _PublicationManifestEntry(
                relative_path="metadata.json",
                kind="file",
                size_bytes=len(metadata_bytes),
                sha256=_sha256_bytes(metadata_bytes),
            ),
            _PublicationManifestEntry(
                relative_path="attestation.json",
                kind="file",
                size_bytes=len(attestation_bytes),
                sha256=_sha256_bytes(attestation_bytes),
            ),
        )
    )
    entries.extend(
        _PublicationManifestEntry(relative_path=path, kind="directory")
        for path in directories
    )
    return tuple(sorted(entries, key=lambda item: (item.relative_path, item.kind)))


def _tree_manifest(root: Path) -> tuple[_PublicationManifestEntry, ...]:
    manifest: list[_PublicationManifestEntry] = []
    first_shape: list[tuple[str, str]] = []
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)

    def traverse(directory: Path) -> None:
        before = _stable_plain_path_identity(directory, directory=True)
        try:
            with os.scandir(directory) as iterator:
                children = sorted(tuple(iterator), key=lambda entry: entry.name)
        except OSError as error:
            raise ValueError(
                "XJTU-SY manifest traversal failed safely"
            ) from error

        for child in children:
            path = directory / child.name
            relative_path = path.relative_to(root).as_posix()
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as error:
                raise ValueError(
                    "XJTU-SY manifest traversal failed safely"
                ) from error
            is_reparse = bool(
                reparse_flag
                and getattr(metadata, "st_file_attributes", 0) & reparse_flag
            )
            if stat.S_ISLNK(metadata.st_mode) or is_reparse:
                raise ValueError("XJTU-SY manifest contains a link or reparse point")
            if stat.S_ISDIR(metadata.st_mode):
                first_shape.append((relative_path, "directory"))
                manifest.append(
                    _PublicationManifestEntry(
                        relative_path=relative_path,
                        kind="directory",
                    )
                )
                traverse(path)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("XJTU-SY manifest contains an unsafe filesystem object")
            first_shape.append((relative_path, "file"))
            try:
                file_before = _stable_plain_path_identity(path, directory=False)
                size, digest = _hash_file(path)
                file_after = _stable_plain_path_identity(path, directory=False)
            except OSError as error:
                raise ValueError(
                    "XJTU-SY manifest traversal failed safely"
                ) from error
            if file_before != file_after:
                raise ValueError("XJTU-SY manifest file identity changed during traversal")
            manifest.append(
                _PublicationManifestEntry(
                    relative_path=relative_path,
                    kind="file",
                    size_bytes=size,
                    sha256=digest,
                )
            )
        if _stable_plain_path_identity(directory, directory=True) != before:
            raise ValueError("XJTU-SY manifest directory changed during traversal")

    def reenumerate(directory: Path) -> list[tuple[str, str]]:
        before = _stable_plain_path_identity(directory, directory=True)
        try:
            with os.scandir(directory) as iterator:
                children = sorted(tuple(iterator), key=lambda entry: entry.name)
        except OSError as error:
            raise ValueError("XJTU-SY manifest traversal failed safely") from error
        shape: list[tuple[str, str]] = []
        for child in children:
            path = directory / child.name
            relative_path = path.relative_to(root).as_posix()
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as error:
                raise ValueError("XJTU-SY manifest traversal failed safely") from error
            is_reparse = bool(
                reparse_flag
                and getattr(metadata, "st_file_attributes", 0) & reparse_flag
            )
            if stat.S_ISLNK(metadata.st_mode) or is_reparse:
                raise ValueError("XJTU-SY manifest contains a link or reparse point")
            if stat.S_ISDIR(metadata.st_mode):
                shape.append((relative_path, "directory"))
                shape.extend(reenumerate(path))
            elif stat.S_ISREG(metadata.st_mode):
                shape.append((relative_path, "file"))
            else:
                raise ValueError("XJTU-SY manifest contains an unsafe filesystem object")
        if _stable_plain_path_identity(directory, directory=True) != before:
            raise ValueError("XJTU-SY manifest directory changed during traversal")
        return shape

    try:
        root_identity = _directory_identity(root)
        traverse(root)
        second_shape = reenumerate(root)
        if tuple(sorted(first_shape)) != tuple(sorted(second_shape)):
            raise ValueError("XJTU-SY manifest tree changed during re-enumeration")
        if _directory_identity(root) != root_identity:
            raise ValueError("XJTU-SY manifest root identity changed during traversal")
    except OSError as error:
        raise ValueError("XJTU-SY manifest traversal failed safely") from error
    return tuple(sorted(manifest, key=lambda item: (item.relative_path, item.kind)))


def _assert_publication_manifest(
    root: Path,
    expected: tuple[_PublicationManifestEntry, ...],
    *,
    context: str,
    expected_identity: tuple[int, int] | None = None,
) -> None:
    root_identity = _directory_identity(root)
    if expected_identity is not None and root_identity != expected_identity:
        raise ValueError(f"{context} identity differs from the validated root")
    first = _tree_manifest(root)
    second = _tree_manifest(root)
    if first != expected or second != expected or first != second:
        raise ValueError(f"{context} differs from the deterministic publication manifest")
    if _directory_identity(root) != root_identity:
        raise ValueError(f"{context} identity changed during manifest reconciliation")


def _locate_owned_directory(
    owned: _OwnedDirectory, candidates: tuple[Path, ...]
) -> Path | None:
    existing = tuple(
        path for path in dict.fromkeys(candidates) if os.path.lexists(path)
    )
    matching = tuple(path for path in existing if _same_identity(path, owned))
    if not existing:
        return None
    if len(matching) != 1:
        raise RuntimeError("refusing to remove an XJTU-SY directory whose identity changed")
    return matching[0]


def _fresh_cleanup_path(parent: Path) -> Path:
    for _ in range(16):
        candidate = parent / f".xjtu-sy-cleanup-{secrets.token_hex(16)}"
        if not os.path.lexists(candidate):
            return candidate
    raise RuntimeError("could not allocate an exclusive XJTU-SY cleanup quarantine")


def _quarantine_owned_directory(
    owned: _OwnedDirectory,
    *,
    alternate_paths: tuple[Path, ...] = (),
) -> Path | None:
    candidates = tuple(dict.fromkeys((owned.path, *alternate_paths)))
    source = _locate_owned_directory(owned, candidates)
    if source is None:
        return None
    quarantine = _fresh_cleanup_path(source.parent)
    all_candidates = (*candidates, quarantine)

    try:
        source.rename(quarantine)
    except BaseException:
        located = _locate_owned_directory(owned, all_candidates)
        if located == quarantine:
            return quarantine
        if located != source:
            raise RuntimeError(
                "XJTU-SY cleanup rename left the owned identity in an ambiguous state"
            )
        try:
            os.rename(source, quarantine)
        except BaseException as fallback_error:
            located = _locate_owned_directory(owned, all_candidates)
            if located != quarantine:
                raise RuntimeError(
                    "XJTU-SY cleanup could not quarantine the owned identity"
                ) from fallback_error
    else:
        located = _locate_owned_directory(owned, all_candidates)
        if located != quarantine:
            raise RuntimeError(
                "XJTU-SY cleanup rename did not quarantine the owned identity"
            )

    if not _same_identity(quarantine, owned):
        raise RuntimeError("XJTU-SY cleanup quarantine identity changed")
    return quarantine


def _cleanup_owned_directory(
    owned: _OwnedDirectory, *, alternate_paths: tuple[Path, ...] = ()
) -> None:
    quarantine = _quarantine_owned_directory(
        owned, alternate_paths=alternate_paths
    )
    if quarantine is None:
        return
    if not _same_identity(quarantine, owned):
        raise RuntimeError("XJTU-SY cleanup quarantine identity changed")
    raise RuntimeError(
        "XJTU-SY cleanup quarantine preserved because no identity-bound "
        "directory removal primitive is available"
    )


def _cleanup_new_empty_staging(path: Path, guard: _DirectoryCreationGuard) -> None:
    if _directory_creation_guard(path) != guard or any(path.iterdir()):
        raise RuntimeError("refusing to remove an unverified XJTU-SY staging path")
    if _directory_creation_guard(path) != guard:
        raise RuntimeError("refusing to remove an unverified XJTU-SY staging path")
    owned = _OwnedDirectory(path, guard.device, guard.inode)
    quarantine = _quarantine_owned_directory(owned)
    if quarantine is None:
        return
    if not _same_identity(quarantine, owned):
        raise RuntimeError("XJTU-SY empty cleanup quarantine identity changed")
    raise RuntimeError(
        "XJTU-SY cleanup quarantine preserved because no identity-bound "
        "directory removal primitive is available"
    )


def _add_cleanup_failure_note(error: BaseException, cleanup_error: BaseException) -> None:
    try:
        add_note = getattr(error, "add_note", None)
        if callable(add_note):
            add_note(
                "XJTU-SY owned staging cleanup failed safely "
                f"({cleanup_error.__class__.__name__})"
            )
    except BaseException:
        return


@dataclass(frozen=True, slots=True)
class XjtuSyPreparationResult:
    """Local publication handles plus a path-free attestation serialization."""

    generation_id: str
    generation_root: Path
    raw_root: Path
    metadata_path: Path
    raw_inventory: RawInventory
    metadata_sha256: str
    attestation_sha256: str
    _attestation_json: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self._attestation_json)
        if not isinstance(value, dict):  # pragma: no cover - constructor-owned invariant
            raise RuntimeError("XJTU-SY attestation root is not an object")
        return value


def _result(
    generation_root: Path,
    generation_id: str,
    inventory: RawInventory,
    metadata_sha256: str,
    attestation_sha256: str,
    attestation_json: str,
) -> XjtuSyPreparationResult:
    return XjtuSyPreparationResult(
        generation_id=generation_id,
        generation_root=generation_root,
        raw_root=generation_root / "raw",
        metadata_path=generation_root / "metadata.json",
        raw_inventory=inventory,
        metadata_sha256=metadata_sha256,
        attestation_sha256=attestation_sha256,
        _attestation_json=attestation_json,
    )


def _read_plain_file_bytes(path: Path) -> bytes:
    before = _stable_plain_path_identity(path, directory=False)
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ValueError("existing XJTU-SY publication file could not be read") from error
    after = _stable_plain_path_identity(path, directory=False)
    if before != after:
        raise ValueError("existing XJTU-SY publication file identity changed during read")
    return payload


def _existing_generation_candidate(destination_root: Path) -> Path | None:
    generation_name = re.compile(r"^xjtu-sy-v1-[0-9a-f]{64}$")

    def snapshot() -> tuple[str, ...]:
        try:
            with os.scandir(destination_root) as iterator:
                return tuple(
                    sorted(
                        entry.name
                        for entry in iterator
                        if generation_name.fullmatch(entry.name) is not None
                    )
                )
        except OSError as error:
            raise ValueError(
                "existing XJTU-SY publication root could not be enumerated"
            ) from error

    first = snapshot()
    second = snapshot()
    if first != second:
        raise ValueError("existing XJTU-SY publication set changed during enumeration")
    if len(first) > 1:
        raise ValueError("multiple existing XJTU-SY generations are ambiguous")
    return destination_root / first[0] if first else None


def _inventory_from_publication_manifest(
    manifest: tuple[_PublicationManifestEntry, ...],
) -> RawInventory:
    files: list[_ReconstructedRawFile] = []
    for entry in manifest:
        if entry.kind != "file" or not entry.relative_path.startswith("raw/"):
            continue
        if entry.size_bytes is None or entry.sha256 is None:
            raise ValueError("existing XJTU-SY raw manifest entry is incomplete")
        relative_path = entry.relative_path.removeprefix("raw/")
        files.append(
            _ReconstructedRawFile(
                relative_path=relative_path,
                size_bytes=entry.size_bytes,
                sha256=entry.sha256,
            )
        )
    ordered = tuple(sorted(files, key=lambda item: item.relative_path))
    binding = [
        {
            "relativePath": item.relative_path,
            "sizeBytes": item.size_bytes,
            "sha256": item.sha256,
        }
        for item in ordered
    ]
    return RawInventory(
        files=ordered,
        inventory_sha256=_sha256_bytes(_canonical_json_bytes(binding)),
        total_bytes=sum(item.size_bytes for item in ordered),
    )


def _try_existing_generation(
    config: XjtuSyPreparationConfig,
    inspected_members: tuple[_InspectedMemberBinding, ...],
    destination_root: Path,
) -> XjtuSyPreparationResult | None:
    final = _existing_generation_candidate(destination_root)
    if final is None:
        return None
    final_identity = _directory_identity(final)
    initial_manifest = _tree_manifest(final)
    inventory = _inventory_from_publication_manifest(initial_manifest)
    _validate_inventory(inventory, inspected_members)
    pdf_sha256 = _validate_raw_tree(final / "raw", inventory)

    metadata_bytes = _canonical_json_bytes(
        _metadata_payload(config, inventory, pdf_sha256)
    )
    metadata_sha256 = _sha256_bytes(metadata_bytes)
    if _read_plain_file_bytes(final / "metadata.json") != metadata_bytes:
        raise ValueError(
            "existing XJTU-SY generation differs from deterministic metadata"
        )
    load_metadata(
        final / "metadata.json",
        expected_sha256=metadata_sha256,
        dataset_id="xjtu-sy",
        raw_inventory=inventory,
    )
    generation_id = _generation_id(config, inventory, metadata_sha256)
    if final.name != generation_id:
        raise ValueError("existing XJTU-SY generation id differs from its evidence")
    attestation_bytes = _canonical_json_bytes(
        _attestation_payload(
            config,
            generation_id,
            inventory,
            metadata_sha256,
            pdf_sha256,
        )
    )
    if _read_plain_file_bytes(final / "attestation.json") != attestation_bytes:
        raise ValueError(
            "existing XJTU-SY generation differs from deterministic attestation"
        )
    expected_manifest = _expected_publication_manifest(
        inventory, metadata_bytes, attestation_bytes
    )
    attestation_sha256 = _sha256_bytes(attestation_bytes)
    result = _result(
        final,
        generation_id,
        inventory,
        metadata_sha256,
        attestation_sha256,
        attestation_bytes.decode("utf-8"),
    )
    _assert_publication_manifest(
        final,
        expected_manifest,
        context="existing XJTU-SY generation",
        expected_identity=final_identity,
    )
    return result


def prepare_xjtu_sy(config: XjtuSyPreparationConfig) -> XjtuSyPreparationResult:
    """Prepare one official multipart XJTU-SY generation."""

    if not isinstance(config, XjtuSyPreparationConfig):
        raise TypeError("config must be XjtuSyPreparationConfig")

    _revalidate_executable(config)
    inspection = inspect_rar_archive(
        config.archive_parts, limits=config.extraction_limits
    )
    inspected_members = _validate_inspection(config, inspection)

    destination_root = config.destination_root
    destination_root.mkdir(parents=True, exist_ok=True)
    _directory_identity(destination_root)
    existing = _try_existing_generation(
        config, inspected_members, destination_root
    )
    if existing is not None:
        return existing
    staging: Path | None = None
    owned: _OwnedDirectory | None = None
    creation_guard: _DirectoryCreationGuard | None = None
    final: Path | None = None
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=".xjtu-sy-generation-", dir=destination_root)
        )
        creation_guard = _directory_creation_guard(staging)
        acquired_identity = _directory_identity(staging)
        owned = _bind_owned_directory(staging, creation_guard, acquired_identity)
        device, inode = owned.device, owned.inode

        attested_executable = _revalidate_executable(config)
        inventory = safe_extract_rar_archive(
            config.archive_parts,
            staging / "raw",
            limits=config.extraction_limits,
            seven_zip_executable=attested_executable,
        )
        _validate_inventory(inventory, inspected_members)
        pdf_sha256 = _validate_raw_tree(staging / "raw", inventory)

        metadata_bytes = _canonical_json_bytes(
            _metadata_payload(config, inventory, pdf_sha256)
        )
        metadata_sha256 = _write_new(staging / "metadata.json", metadata_bytes)
        load_metadata(
            staging / "metadata.json",
            expected_sha256=metadata_sha256,
            dataset_id="xjtu-sy",
            raw_inventory=inventory,
        )
        generation_id = _generation_id(config, inventory, metadata_sha256)
        attestation_bytes = _canonical_json_bytes(
            _attestation_payload(
                config,
                generation_id,
                inventory,
                metadata_sha256,
                pdf_sha256,
            )
        )
        attestation_sha256 = _write_new(
            staging / "attestation.json", attestation_bytes
        )
        attestation_json = attestation_bytes.decode("utf-8")

        expected_manifest = _expected_publication_manifest(
            inventory, metadata_bytes, attestation_bytes
        )
        _assert_publication_manifest(
            staging,
            expected_manifest,
            context="XJTU-SY staging",
        )
        final = destination_root / generation_id
        if os.path.lexists(final):
            _assert_publication_manifest(
                final,
                expected_manifest,
                context="concurrently published XJTU-SY generation",
            )
            raise RuntimeError(
                "an XJTU-SY generation appeared concurrently during preparation"
            )

        _assert_publication_manifest(
            staging,
            expected_manifest,
            context="XJTU-SY staging immediately before promotion",
            expected_identity=(owned.device, owned.inode),
        )
        staging.rename(final)
        owned = _OwnedDirectory(final, device, inode)
        if not _same_identity(final, owned):
            raise RuntimeError("XJTU-SY atomic generation promotion could not be verified")
        result = _result(
            final,
            generation_id,
            inventory,
            metadata_sha256,
            attestation_sha256,
            attestation_json,
        )
        _assert_publication_manifest(
            final,
            expected_manifest,
            context="promoted XJTU-SY generation",
            expected_identity=(owned.device, owned.inode),
        )
        return result
    except BaseException as error:
        try:
            if owned is not None:
                alternate_paths = (final,) if final is not None else ()
                _cleanup_owned_directory(owned, alternate_paths=alternate_paths)
            elif staging is not None and os.path.lexists(staging):
                if creation_guard is None:
                    raise RuntimeError("XJTU-SY staging identity was never established")
                _cleanup_new_empty_staging(staging, creation_guard)
        except BaseException as cleanup_error:
            _add_cleanup_failure_note(error, cleanup_error)
        raise
