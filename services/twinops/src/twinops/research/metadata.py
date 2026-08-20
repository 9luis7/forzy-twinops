"""Versioned metadata validation tied to a verified raw inventory."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from twinops.research.downloads import RawInventory, verify_archive


@dataclass(frozen=True, slots=True)
class LoadedMetadata:
    payload: Mapping[str, Any]
    schema_version: int
    dataset_id: str
    metadata_id: str
    metadata_sha256: str


def load_metadata(
    path: str | Path,
    *,
    expected_sha256: str,
    dataset_id: str,
    raw_inventory: RawInventory,
) -> LoadedMetadata:
    metadata_path = Path(path)
    actual_hash = verify_archive(metadata_path, expected_sha256)
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"metadata is not valid UTF-8 JSON: {metadata_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("metadata root must be an object")
    if payload.get("schemaVersion") != 1:
        raise ValueError("metadata schemaVersion must be 1")
    if payload.get("datasetId") != dataset_id:
        raise ValueError(f"metadata datasetId must equal {dataset_id}")
    metadata_id = payload.get("metadataId")
    if not isinstance(metadata_id, str) or not metadata_id.strip():
        raise ValueError("metadataId must be a non-empty string")
    sampling_hz = payload.get("samplingHz")
    if isinstance(sampling_hz, bool) or not isinstance(sampling_hz, (int, float)) or sampling_hz <= 0:
        raise ValueError("metadata samplingHz must be positive numeric")
    unit = payload.get("accelerationUnit")
    if not isinstance(unit, str) or not unit.strip():
        raise ValueError("metadata accelerationUnit must be explicit")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("metadata files do not match raw inventory: mapping is empty")
    mapped_paths = set(files)
    inventory_paths = {item.relative_path for item in raw_inventory.files}
    if mapped_paths != inventory_paths:
        missing = sorted(inventory_paths - mapped_paths)
        extra = sorted(mapped_paths - inventory_paths)
        raise ValueError(f"metadata files do not match raw inventory; missing={missing}, extra={extra}")
    return LoadedMetadata(
        payload=payload,
        schema_version=1,
        dataset_id=dataset_id,
        metadata_id=metadata_id.strip(),
        metadata_sha256=actual_hash,
    )
