"""Fail-closed preparation boundary for the official NASA IMS archives."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
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


NASA_IMS_RUN_1_SHA256 = "c25241571583948462a3916d97dc11c984a839f38a0da0907fff18c958c0a484"
NASA_IMS_RUN_2_SHA256 = "b154d5ba1ae5f7f01cdd4f1bde5b08cfdc2f3134d51ad2f6614b1270a86ab632"
NASA_IMS_RUN_3_SHA256 = "01e9ec83c6c55adc0300a20003a261f9a2ac2b714aae4984050325e589252bc8"

_TIMESTAMP_NAME = re.compile(
    r"^(?P<year>\d{4})\.(?P<month>\d{2})\.(?P<day>\d{2})\."
    r"(?P<hour>\d{2})\.(?P<minute>\d{2})\.(?P<second>\d{2})$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_README_SOURCE_REF = "nasa-ims-internal-readme-cf46d37c"
_QIU_SOURCE_REF = "qiu-et-al-jsv-2006"


@dataclass(frozen=True, slots=True)
class _RunSpec:
    number: int
    run_id: str
    archive_field: str
    prefix: str
    first_timestamp: str
    last_timestamp: str
    regular_file_count: int
    total_member_count: int
    samples_per_window: int
    column_count: int
    documented_file_count: int | None = None
    documented_prefix_last_timestamp: str | None = None
    first_extension_timestamp: str | None = None


_RUN_SPECS = (
    _RunSpec(
        number=1,
        run_id="ims-run-1",
        archive_field="run_1_archive",
        prefix="1st_test",
        first_timestamp="2003.10.22.12.06.24",
        last_timestamp="2003.11.25.23.39.56",
        regular_file_count=2_156,
        total_member_count=2_157,
        samples_per_window=20_480,
        column_count=8,
    ),
    _RunSpec(
        number=2,
        run_id="ims-run-2",
        archive_field="run_2_archive",
        prefix="2nd_test",
        first_timestamp="2004.02.12.10.32.39",
        last_timestamp="2004.02.19.06.22.39",
        regular_file_count=984,
        total_member_count=985,
        samples_per_window=20_480,
        column_count=4,
    ),
    _RunSpec(
        number=3,
        run_id="ims-run-3",
        archive_field="run_3_archive",
        prefix="4th_test/txt",
        first_timestamp="2004.03.04.09.27.46",
        last_timestamp="2004.04.18.02.42.55",
        regular_file_count=6_324,
        total_member_count=6_326,
        samples_per_window=20_480,
        column_count=4,
        documented_file_count=4_448,
        documented_prefix_last_timestamp="2004.04.04.19.01.57",
        first_extension_timestamp="2004.04.04.19.11.57",
    ),
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
class NasaImsPreparationConfig:
    """Caller-authorized inputs for one deterministic NASA IMS publication."""

    run_1_archive: ArchivePart
    run_2_archive: ArchivePart
    run_3_archive: ArchivePart
    seven_zip_executable: Path
    destination_root: Path
    extraction_limits: RarExtractionLimits = RarExtractionLimits()
    _seven_zip_attestation: _ExecutableAttestation = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        expected = (
            ("run 1", self.run_1_archive, NASA_IMS_RUN_1_SHA256),
            ("run 2", self.run_2_archive, NASA_IMS_RUN_2_SHA256),
            ("run 3", self.run_3_archive, NASA_IMS_RUN_3_SHA256),
        )
        archive_paths: list[Path] = []
        for label, archive, digest in expected:
            if not isinstance(archive, ArchivePart):
                raise TypeError(f"{label} archive must be an ArchivePart")
            if archive.sha256 != digest:
                raise ValueError(f"{label} archive SHA-256 does not match the official source")
            if not archive.path.is_absolute():
                raise ValueError(f"{label} archive path must be absolute")
            archive_paths.append(archive.path)
        if len({os.path.normcase(os.fspath(path)) for path in archive_paths}) != 3:
            raise ValueError("NASA IMS archive paths must be three distinct absolute paths")
        if not isinstance(self.extraction_limits, RarExtractionLimits):
            raise TypeError("extraction_limits must be a RarExtractionLimits value")

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


@dataclass(frozen=True, slots=True)
class NasaImsPreparationResult:
    """Local publication handles plus a path-free attestation serialization."""

    generation_id: str
    generation_root: Path
    run_1_raw_root: Path
    run_2_raw_root: Path
    run_1_metadata_path: Path
    run_2_metadata_path: Path
    run_1_inventory: RawInventory
    run_2_inventory: RawInventory
    run_1_metadata_sha256: str
    run_2_metadata_sha256: str
    attestation_sha256: str
    _attestation_json: str

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh, path-free JSON object suitable for ``sources.json``."""

        value = json.loads(self._attestation_json)
        if not isinstance(value, dict):  # pragma: no cover - constructor-owned invariant
            raise RuntimeError("NASA IMS attestation root is not an object")
        return value


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


def _plain_directory_metadata(path: Path):
    metadata = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or (reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag)
    ):
        raise ValueError(f"NASA IMS publication path must be a regular directory: {path.name}")
    return metadata


def _valid_identity_values(device: object, inode: object) -> tuple[int, int]:
    if (
        not isinstance(device, int)
        or isinstance(device, bool)
        or device <= 0
        or not isinstance(inode, int)
        or isinstance(inode, bool)
        or inode <= 0
    ):
        raise ValueError("NASA IMS publication path has an invalid filesystem identity")
    return device, inode


def _valid_identity(metadata: Any) -> tuple[int, int]:
    return _valid_identity_values(
        getattr(metadata, "st_dev", None), getattr(metadata, "st_ino", None)
    )


def _directory_identity(path: Path) -> tuple[int, int]:
    first = _valid_identity(_plain_directory_metadata(path))
    second = _valid_identity(_plain_directory_metadata(path))
    if first != second:
        raise ValueError("NASA IMS publication path filesystem identity is unstable")
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
        raise ValueError("NASA IMS staging creation identity is unstable")
    return first


def _bind_owned_directory(
    path: Path,
    creation_guard: _DirectoryCreationGuard,
    acquired_identity: tuple[int, int],
) -> _OwnedDirectory:
    try:
        device, inode = acquired_identity
    except (TypeError, ValueError) as error:
        raise ValueError("NASA IMS staging acquired an invalid filesystem identity") from error
    identity = _valid_identity_values(device, inode)
    observed_guard = _directory_creation_guard(path)
    if (
        observed_guard != creation_guard
        or identity != (creation_guard.device, creation_guard.inode)
    ):
        raise ValueError("NASA IMS staging changed between creation and ownership")
    return _OwnedDirectory(path, *identity)


def _same_identity(path: Path, owned: _OwnedDirectory) -> bool:
    if not os.path.lexists(path):
        return False
    try:
        return _directory_identity(path) == (owned.device, owned.inode)
    except (OSError, ValueError):
        return False


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hash_file(path: Path) -> tuple[int, str]:
    size = 0
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


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


def _revalidate_executable(config: NasaImsPreparationConfig) -> Path:
    expected = config._seven_zip_attestation
    try:
        observed = _attest_executable(expected.path)
    except (OSError, ValueError) as error:
        raise ValueError("trusted 7z executable changed since config attestation") from error
    if observed != expected:
        raise ValueError("trusted 7z executable changed since config attestation")
    return expected.path


def _canonical_member_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("RAR inspection returned an invalid member path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.as_posix() != normalized or path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise ValueError("RAR inspection returned a non-canonical member path")
    return normalized


def _expected_directories(prefix: str) -> tuple[str, ...]:
    parts = PurePosixPath(prefix).parts
    return tuple(PurePosixPath(*parts[:index]).as_posix() for index in range(1, len(parts) + 1))


def _validate_inspection(spec: Any, inspection: Any) -> tuple[str, ...]:
    members = getattr(inspection, "members", None)
    if not isinstance(members, tuple):
        raise ValueError(f"NASA IMS run {spec.number} inspection members must be immutable")
    if len(members) != spec.total_member_count:
        raise ValueError(
            f"NASA IMS run {spec.number} member count must be {spec.total_member_count}"
        )
    directories: list[str] = []
    files: list[str] = []
    for member in members:
        path = _canonical_member_path(getattr(member, "relative_path", None))
        if getattr(member, "is_directory", None) is True:
            directories.append(path)
        elif getattr(member, "is_directory", None) is False:
            files.append(path)
        else:
            raise ValueError(f"NASA IMS run {spec.number} has an unknown member type")
    if tuple(sorted(directories)) != tuple(sorted(_expected_directories(spec.prefix))):
        raise ValueError(f"NASA IMS run {spec.number} archive directory boundary is unexpected")
    if len(files) != spec.regular_file_count or len(set(files)) != len(files):
        raise ValueError(
            f"NASA IMS run {spec.number} regular-file count must be {spec.regular_file_count}"
        )
    ordered = tuple(sorted(files))
    names: list[str] = []
    for path_text in ordered:
        path = PurePosixPath(path_text)
        if path.parent.as_posix() != spec.prefix:
            raise ValueError(f"NASA IMS run {spec.number} file escaped its source boundary")
        if _TIMESTAMP_NAME.fullmatch(path.name) is None:
            raise ValueError(f"NASA IMS run {spec.number} filename is not a source timestamp")
        names.append(path.name)
    if names[0] != spec.first_timestamp or names[-1] != spec.last_timestamp:
        raise ValueError(f"NASA IMS run {spec.number} source boundary filenames do not match")
    if spec.number == 3:
        documented_count = spec.documented_file_count
        if not isinstance(documented_count, int) or documented_count <= 0:
            raise ValueError("NASA IMS run 3 documented prefix is unavailable")
        if names[documented_count - 1] != spec.documented_prefix_last_timestamp:
            raise ValueError("NASA IMS run 3 documented prefix boundary does not match")
        if names[documented_count] != spec.first_extension_timestamp:
            raise ValueError("NASA IMS run 3 undocumented extension boundary does not match")
    return ordered


def _inventory_binding(inventory: RawInventory) -> list[dict[str, object]]:
    return [
        {
            "relativePath": item.relative_path,
            "sizeBytes": item.size_bytes,
            "sha256": item.sha256,
        }
        for item in sorted(inventory.files, key=lambda value: value.relative_path)
    ]


def _validate_inventory(spec: Any, inventory: RawInventory, expected_paths: tuple[str, ...]) -> None:
    if not isinstance(inventory, RawInventory):
        raise TypeError(f"NASA IMS run {spec.number} extraction must return RawInventory")
    binding = _inventory_binding(inventory)
    paths = tuple(item["relativePath"] for item in binding)
    if paths != expected_paths or len(paths) != spec.regular_file_count:
        raise ValueError(f"NASA IMS run {spec.number} raw inventory does not match inspection")
    for item in binding:
        if (
            not isinstance(item["sizeBytes"], int)
            or isinstance(item["sizeBytes"], bool)
            or item["sizeBytes"] < 0
            or not isinstance(item["sha256"], str)
            or _SHA256.fullmatch(item["sha256"]) is None
        ):
            raise ValueError(f"NASA IMS run {spec.number} raw inventory entry is invalid")
    expected_inventory_hash = _sha256_bytes(_canonical_json_bytes(binding))
    if inventory.inventory_sha256 != expected_inventory_hash:
        raise ValueError(f"NASA IMS run {spec.number} raw inventory hash is invalid")
    if inventory.total_bytes != sum(int(item["sizeBytes"]) for item in binding):
        raise ValueError(f"NASA IMS run {spec.number} raw inventory byte count is invalid")


def _validate_numeric_file(
    path: Path,
    *,
    expected_rows: int,
    expected_columns: int,
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
        raise ValueError(f"NASA IMS numeric member must be a regular file: {path.name}")

    digest = hashlib.sha256()
    size = 0
    row_count = 0
    observed_columns: int | None = None
    with path.open("rb") as stream:
        for raw_line in stream:
            digest.update(raw_line)
            size += len(raw_line)
            stripped = raw_line.strip()
            if not stripped:
                raise ValueError(f"NASA IMS numeric file contains a blank row: {path.name}")
            try:
                tokens = stripped.decode("ascii").split()
            except UnicodeDecodeError as error:
                raise ValueError(f"NASA IMS numeric file is not ASCII numeric data: {path.name}") from error
            if observed_columns is None:
                observed_columns = len(tokens)
                if observed_columns != expected_columns:
                    raise ValueError(
                        f"NASA IMS numeric file column count must be {expected_columns}: {path.name}"
                    )
            elif len(tokens) != observed_columns:
                raise ValueError(f"NASA IMS numeric file is ragged: {path.name}")
            if len(tokens) != expected_columns:
                raise ValueError(
                    f"NASA IMS numeric file column count must be {expected_columns}: {path.name}"
                )
            try:
                values = (float(token) for token in tokens)
                if not all(math.isfinite(value) for value in values):
                    raise ValueError
            except ValueError as error:
                raise ValueError(
                    f"NASA IMS numeric file must contain only finite values: {path.name}"
                ) from error
            row_count += 1
    if row_count == 0:
        raise ValueError(f"NASA IMS numeric file is blank: {path.name}")
    if row_count != expected_rows:
        raise ValueError(
            f"NASA IMS numeric file row count must be {expected_rows}: {path.name}"
        )
    if size != expected_size or digest.hexdigest() != expected_sha256:
        raise ValueError(f"NASA IMS numeric file differs from its raw inventory: {path.name}")


def _filesystem_relative_files(root: Path) -> tuple[str, ...]:
    files: list[str] = []
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for directory, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        for name in directory_names:
            path = current / name
            metadata = path.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or (reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag)
            ):
                raise ValueError("NASA IMS prepared tree contains an unsafe directory")
        for name in file_names:
            path = current / name
            metadata = path.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or (reparse_flag and getattr(metadata, "st_file_attributes", 0) & reparse_flag)
            ):
                raise ValueError("NASA IMS prepared tree contains an unsafe file")
            files.append(path.relative_to(root).as_posix())
    return tuple(sorted(files))


def _validate_run_tree(spec: Any, root: Path, inventory: RawInventory) -> None:
    inventory_files = {item.relative_path: item for item in inventory.files}
    if _filesystem_relative_files(root) != tuple(sorted(inventory_files)):
        raise ValueError(f"NASA IMS run {spec.number} filesystem differs from raw inventory")
    for relative_path in sorted(inventory_files):
        item = inventory_files[relative_path]
        _validate_numeric_file(
            root.joinpath(*PurePosixPath(relative_path).parts),
            expected_rows=spec.samples_per_window,
            expected_columns=spec.column_count,
            expected_size=item.size_bytes,
            expected_sha256=item.sha256,
        )


def _source_timestamp_evidence(filename: str) -> dict[str, object]:
    match = _TIMESTAMP_NAME.fullmatch(filename)
    if match is None:  # pragma: no cover - inspection guarantees this
        raise RuntimeError("validated NASA IMS timestamp filename became invalid")
    return {
        "filenameText": filename,
        "timezone": "unknown",
        "components": {name: int(value) for name, value in match.groupdict().items()},
    }


def _channels(spec: Any) -> list[dict[str, object]]:
    if spec.column_count not in {4, 8}:
        raise ValueError(f"NASA IMS run {spec.number} column mapping is unsupported")
    channels_per_bearing = spec.column_count // 4
    channels = []
    for bearing_number in range(1, 5):
        for source_channel in range(1, channels_per_bearing + 1):
            channels.append(
                {
                    "columnIndex": (bearing_number - 1) * channels_per_bearing
                    + source_channel
                    - 1,
                    "bearingId": f"{spec.run_id}-bearing-{bearing_number}",
                    "axis": f"source-channel-{source_channel}",
                    "windowStateLabel": "unknown",
                    "terminalFailureMode": None,
                    "lifeFraction": None,
                }
            )
    return channels


def _terminal_outcomes(spec: Any) -> dict[str, object]:
    if spec.number == 1:
        bearings = {
            "ims-run-1-bearing-3": {
                "observations": [
                    {"outcome": "inner_race", "sourceRef": _README_SOURCE_REF}
                ]
            },
            "ims-run-1-bearing-4": {
                "status": "conflicting_primary_source_descriptions",
                "observations": [
                    {"outcome": "rolling_element", "sourceRef": _README_SOURCE_REF},
                    {
                        "outcome": "rolling_element_plus_outer_race",
                        "sourceRef": _QIU_SOURCE_REF,
                    },
                ],
            },
        }
    else:
        bearings = {
            "ims-run-2-bearing-1": {
                "observations": [
                    {"outcome": "outer_race", "sourceRef": _README_SOURCE_REF}
                ]
            }
        }
    sources: dict[str, object] = {
        _README_SOURCE_REF: {
            "localRelativePath": "IMS/Readme Document for IMS Bearing Data.pdf",
            "sha256": "cf46d37c21f7f292c11bbbdd4695d876c417ed1d6425e3d87c962ae2182ae6ed",
        }
    }
    if spec.number == 1:
        sources[_QIU_SOURCE_REF] = {
            "citation": "Qiu et al., Journal of Sound and Vibration",
            "doi": "10.1016/j.jsv.2005.03.007",
            "url": "https://doi.org/10.1016/j.jsv.2005.03.007",
        }
    return {
        "scope": "terminal_run_inspection_only_not_window_labels",
        "sources": sources,
        "bearings": bearings,
    }


def _metadata_payload(
    spec: Any,
    archive: ArchivePart,
    inventory: RawInventory,
    generation_id: str,
) -> dict[str, object]:
    channels = _channels(spec)
    files: dict[str, object] = {}
    for sequence, item in enumerate(sorted(inventory.files, key=lambda value: value.relative_path)):
        files[item.relative_path] = {
            "runId": spec.run_id,
            "sequenceIndex": sequence,
            "startedAt": None,
            "timestampQuality": "unavailable",
            "sourceLocalTimestampEvidence": _source_timestamp_evidence(
                PurePosixPath(item.relative_path).name
            ),
            "channels": channels,
        }
    return {
        "schemaVersion": 1,
        "datasetId": "nasa-ims",
        "metadataId": (
            f"nasa-ims-run-{spec.number}-schema-v1-source-{archive.sha256}-"
            f"raw-{inventory.inventory_sha256}"
        ),
        "generationId": generation_id,
        "sourceArchiveSha256": archive.sha256,
        "rawInventorySha256": inventory.inventory_sha256,
        "samplingHz": 20_000,
        "samplesPerWindow": spec.samples_per_window,
        "accelerationUnit": "unknown",
        "rigContextEvidence": {
            "shaftSpeed": {"value": 2_000, "unit": "rpm", "scope": "rig"},
            "radialLoad": {"value": 6_000, "unit": "lb", "scope": "rig"},
            "sourceRef": _README_SOURCE_REF,
        },
        "terminalOutcomeEvidence": _terminal_outcomes(spec),
        "semanticGates": {
            "sourceTimezone": "unknown",
            "windowState": "unknown",
            "faultOnset": "unknown",
            "severity": "unknown",
            "trueRul": "unknown",
        },
        "files": files,
    }


def _generation_id(
    config: NasaImsPreparationConfig,
    run_1_inventory: RawInventory,
    run_2_inventory: RawInventory,
) -> str:
    binding = {
        "schemaVersion": 1,
        "datasetId": "nasa-ims",
        "run1": {
            "archiveSha256": config.run_1_archive.sha256,
            "rawInventorySha256": run_1_inventory.inventory_sha256,
        },
        "run2": {
            "archiveSha256": config.run_2_archive.sha256,
            "rawInventorySha256": run_2_inventory.inventory_sha256,
        },
        "run3": {
            "archiveSha256": config.run_3_archive.sha256,
            "status": "quarantined_source_contradiction",
        },
    }
    return f"nasa-ims-v1-{_sha256_bytes(_canonical_json_bytes(binding))}"


def _quarantine(spec: Any, archive: ArchivePart) -> dict[str, object]:
    documented_count = int(spec.documented_file_count)
    extension_count = spec.regular_file_count - documented_count
    return {
        "runId": spec.run_id,
        "status": "quarantined_source_contradiction",
        "sourceArchiveSha256": archive.sha256,
        "documentedFileCount": documented_count,
        "observedFileCount": spec.regular_file_count,
        "documentedPrefixLastPath": f"{spec.prefix}/{spec.documented_prefix_last_timestamp}",
        "undocumentedExtensionCount": extension_count,
        "firstExtensionPath": f"{spec.prefix}/{spec.first_extension_timestamp}",
        "lastObservedPath": f"{spec.prefix}/{spec.last_timestamp}",
        "includedInConfirmatoryMetrics": False,
        "includedInSupervisedMetrics": False,
        "includedInRulMetrics": False,
    }


def _compact_inventory(inventory: RawInventory) -> dict[str, object]:
    ordered = sorted(inventory.files, key=lambda value: value.relative_path)
    return {
        "inventorySha256": inventory.inventory_sha256,
        "fileCount": len(ordered),
        "totalBytes": inventory.total_bytes,
        "firstPath": ordered[0].relative_path,
        "lastPath": ordered[-1].relative_path,
    }


def _attestation_payload(
    config: NasaImsPreparationConfig,
    generation_id: str,
    run_1_inventory: RawInventory,
    run_2_inventory: RawInventory,
    run_1_metadata_sha256: str,
    run_2_metadata_sha256: str,
    quarantine: dict[str, object],
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "datasetId": "nasa-ims",
        "status": "prepared_semantically_gated",
        "generationId": generation_id,
        "runs": {
            "run-1": {
                "status": "prepared",
                "sourceArchiveSha256": config.run_1_archive.sha256,
                "rawInventory": _compact_inventory(run_1_inventory),
                "metadata": {
                    "schemaVersion": 1,
                    "sha256": run_1_metadata_sha256,
                },
            },
            "run-2": {
                "status": "prepared",
                "sourceArchiveSha256": config.run_2_archive.sha256,
                "rawInventory": _compact_inventory(run_2_inventory),
                "metadata": {
                    "schemaVersion": 1,
                    "sha256": run_2_metadata_sha256,
                },
            },
        },
        "semanticGates": {
            "accelerationUnit": "unknown",
            "sourceTimezone": "unknown",
            "axes": "opaque_source_channels",
            "windowState": "unknown",
            "faultOnset": "unknown",
            "severity": "unknown",
            "lifeFraction": None,
            "trueRul": "unknown",
            "confirmatoryMetricsEnabled": False,
            "supervisedMetricsEnabled": False,
            "rulMetricsEnabled": False,
        },
        "quarantine": quarantine,
    }


def _write_new(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return _sha256_bytes(payload)


def _tree_manifest(root: Path) -> tuple[tuple[str, int, str], ...]:
    manifest = []
    for relative_path in _filesystem_relative_files(root):
        path = root.joinpath(*PurePosixPath(relative_path).parts)
        size, digest = _hash_file(path)
        manifest.append((relative_path, size, digest))
    return tuple(manifest)


def _cleanup_owned_directory(
    owned: _OwnedDirectory, *, alternate_paths: tuple[Path, ...] = ()
) -> None:
    candidates = tuple(dict.fromkeys((owned.path, *alternate_paths)))
    existing = tuple(path for path in candidates if os.path.lexists(path))
    matching = tuple(path for path in existing if _same_identity(path, owned))
    if not existing:
        return
    if len(matching) != 1:
        raise RuntimeError("refusing to remove a NASA IMS directory whose identity changed")
    target = matching[0]
    shutil.rmtree(target)
    if os.path.lexists(target):
        raise RuntimeError("NASA IMS staging cleanup did not remove the owned directory")


def _cleanup_new_empty_staging(path: Path, guard: _DirectoryCreationGuard) -> None:
    """Clean the just-created empty path before a stable identity was acquired."""

    if _directory_creation_guard(path) != guard or any(path.iterdir()):
        raise RuntimeError("refusing to remove an unverified NASA IMS staging path")
    if _directory_creation_guard(path) != guard:
        raise RuntimeError("refusing to remove an unverified NASA IMS staging path")
    path.rmdir()
    if os.path.lexists(path):
        raise RuntimeError("NASA IMS empty staging cleanup did not remove the directory")


def _add_cleanup_failure_note(error: BaseException, cleanup_error: BaseException) -> None:
    try:
        note = (
            "NASA IMS owned staging cleanup failed safely "
            f"({cleanup_error.__class__.__name__})"
        )
        add_note = getattr(error, "add_note", None)
        if callable(add_note):
            add_note(note)
    except BaseException:
        return


def _result(
    generation_root: Path,
    generation_id: str,
    run_1_inventory: RawInventory,
    run_2_inventory: RawInventory,
    run_1_metadata_sha256: str,
    run_2_metadata_sha256: str,
    attestation_sha256: str,
    attestation_json: str,
) -> NasaImsPreparationResult:
    return NasaImsPreparationResult(
        generation_id=generation_id,
        generation_root=generation_root,
        run_1_raw_root=generation_root / "run-1" / "raw",
        run_2_raw_root=generation_root / "run-2" / "raw",
        run_1_metadata_path=generation_root / "run-1" / "metadata.json",
        run_2_metadata_path=generation_root / "run-2" / "metadata.json",
        run_1_inventory=run_1_inventory,
        run_2_inventory=run_2_inventory,
        run_1_metadata_sha256=run_1_metadata_sha256,
        run_2_metadata_sha256=run_2_metadata_sha256,
        attestation_sha256=attestation_sha256,
        _attestation_json=attestation_json,
    )


def prepare_nasa_ims(config: NasaImsPreparationConfig) -> NasaImsPreparationResult:
    """Prepare official runs 1/2 atomically and quarantine contradictory run 3."""

    if not isinstance(config, NasaImsPreparationConfig):
        raise TypeError("config must be NasaImsPreparationConfig")

    _revalidate_executable(config)
    inspected_paths: dict[int, tuple[str, ...]] = {}
    for spec in _RUN_SPECS:
        archive = getattr(config, spec.archive_field)
        inspection = inspect_rar_archive([archive], limits=config.extraction_limits)
        inspected_paths[spec.number] = _validate_inspection(spec, inspection)

    destination_root = config.destination_root
    destination_root.mkdir(parents=True, exist_ok=True)
    _directory_identity(destination_root)
    staging: Path | None = None
    owned: _OwnedDirectory | None = None
    creation_guard: _DirectoryCreationGuard | None = None
    final: Path | None = None
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=".nasa-ims-generation-", dir=destination_root)
        )
        creation_guard = _directory_creation_guard(staging)
        acquired_identity = _directory_identity(staging)
        owned = _bind_owned_directory(staging, creation_guard, acquired_identity)
        device, inode = owned.device, owned.inode
        run_1_spec, run_2_spec, run_3_spec = _RUN_SPECS
        attested_executable = _revalidate_executable(config)
        run_1_inventory = safe_extract_rar_archive(
            [config.run_1_archive],
            staging / "run-1" / "raw",
            limits=config.extraction_limits,
            seven_zip_executable=attested_executable,
        )
        _validate_inventory(run_1_spec, run_1_inventory, inspected_paths[1])
        _validate_run_tree(run_1_spec, staging / "run-1" / "raw", run_1_inventory)

        attested_executable = _revalidate_executable(config)
        run_2_inventory = safe_extract_rar_archive(
            [config.run_2_archive],
            staging / "run-2" / "raw",
            limits=config.extraction_limits,
            seven_zip_executable=attested_executable,
        )
        _validate_inventory(run_2_spec, run_2_inventory, inspected_paths[2])
        _validate_run_tree(run_2_spec, staging / "run-2" / "raw", run_2_inventory)

        generation_id = _generation_id(config, run_1_inventory, run_2_inventory)
        run_1_metadata = _canonical_json_bytes(
            _metadata_payload(run_1_spec, config.run_1_archive, run_1_inventory, generation_id)
        )
        run_2_metadata = _canonical_json_bytes(
            _metadata_payload(run_2_spec, config.run_2_archive, run_2_inventory, generation_id)
        )
        run_1_metadata_path = staging / "run-1" / "metadata.json"
        run_2_metadata_path = staging / "run-2" / "metadata.json"
        run_1_metadata_sha256 = _write_new(run_1_metadata_path, run_1_metadata)
        run_2_metadata_sha256 = _write_new(run_2_metadata_path, run_2_metadata)
        load_metadata(
            run_1_metadata_path,
            expected_sha256=run_1_metadata_sha256,
            dataset_id="nasa-ims",
            raw_inventory=run_1_inventory,
        )
        load_metadata(
            run_2_metadata_path,
            expected_sha256=run_2_metadata_sha256,
            dataset_id="nasa-ims",
            raw_inventory=run_2_inventory,
        )

        quarantine = _quarantine(run_3_spec, config.run_3_archive)
        attestation = _attestation_payload(
            config,
            generation_id,
            run_1_inventory,
            run_2_inventory,
            run_1_metadata_sha256,
            run_2_metadata_sha256,
            quarantine,
        )
        attestation_bytes = _canonical_json_bytes(attestation)
        attestation_sha256 = _write_new(staging / "attestation.json", attestation_bytes)
        attestation_json = attestation_bytes.decode("utf-8")

        expected_manifest = _tree_manifest(staging)
        final = destination_root / generation_id
        if os.path.lexists(final):
            existing_identity = _directory_identity(final)
            existing_manifest = _tree_manifest(final)
            if _directory_identity(final) != existing_identity:
                raise ValueError("existing generation root identity is unstable")
            if existing_manifest != expected_manifest:
                raise ValueError("existing generation differs from the deterministic publication")
            _cleanup_owned_directory(owned)
            return _result(
                final,
                generation_id,
                run_1_inventory,
                run_2_inventory,
                run_1_metadata_sha256,
                run_2_metadata_sha256,
                attestation_sha256,
                attestation_json,
            )

        staging.rename(final)
        owned = _OwnedDirectory(final, device, inode)
        if not _same_identity(final, owned) or _tree_manifest(final) != expected_manifest:
            raise RuntimeError("NASA IMS atomic generation promotion could not be verified")
        return _result(
            final,
            generation_id,
            run_1_inventory,
            run_2_inventory,
            run_1_metadata_sha256,
            run_2_metadata_sha256,
            attestation_sha256,
            attestation_json,
        )
    except BaseException as error:
        try:
            if owned is not None:
                alternate_paths = (final,) if final is not None else ()
                _cleanup_owned_directory(owned, alternate_paths=alternate_paths)
            elif staging is not None and os.path.lexists(staging):
                if creation_guard is None:
                    raise RuntimeError("NASA IMS staging identity was never established")
                _cleanup_new_empty_staging(staging, creation_guard)
        except BaseException as cleanup_error:
            _add_cleanup_failure_note(error, cleanup_error)
        raise
