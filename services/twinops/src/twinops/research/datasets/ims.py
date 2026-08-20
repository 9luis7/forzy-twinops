"""Adapter for original NASA IMS numeric vibration files."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from twinops.research.contracts import SignalWindow


_TIMESTAMP_FORMAT = "%Y.%m.%d.%H.%M.%S"


def _load_metadata(root: Path) -> dict[str, Any]:
    path = root / "metadata.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"IMS adapter requires curated metadata at {path}; channel identity is never guessed"
        )
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(metadata.get("tests"), dict):
        raise ValueError("IMS metadata must contain a tests mapping")
    return metadata


def _timestamp(path: Path) -> datetime:
    try:
        return datetime.strptime(path.name, _TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"IMS run filename is not an acquisition timestamp: {path.name}") from exc


def iter_ims(root: str | Path) -> Iterator[SignalWindow]:
    """Yield IMS windows using an explicit test/channel metadata map."""

    root_path = Path(root)
    metadata = _load_metadata(root_path)
    try:
        sampling_hz = float(metadata["samplingHz"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("IMS metadata requires numeric samplingHz") from exc
    unit = str(metadata.get("accelerationUnit", "g"))

    for test_name, test_meta in sorted(metadata["tests"].items()):
        if not isinstance(test_meta, dict):
            raise ValueError(f"IMS metadata for {test_name} must be an object")
        channels = test_meta.get("channels")
        labels = test_meta.get("faultLabels")
        if not isinstance(channels, list) or not channels:
            raise ValueError(f"IMS metadata for {test_name} requires a non-empty channel map")
        if not isinstance(labels, dict):
            raise ValueError(f"IMS metadata for {test_name} requires fault label metadata")

        test_dir = root_path / test_name
        if not test_dir.is_dir():
            raise FileNotFoundError(f"IMS test directory does not exist: {test_dir}")
        files = sorted((path for path in test_dir.iterdir() if path.is_file()), key=_timestamp)
        for path in files:
            matrix = np.loadtxt(path, dtype=float, ndmin=2)
            if matrix.ndim != 2 or matrix.shape[1] != len(channels):
                raise ValueError(
                    f"IMS channel count mismatch in {path.name}: metadata={len(channels)}, file={matrix.shape[1]}"
                )

            bearing_axes: dict[str, dict[str, np.ndarray]] = defaultdict(dict)
            for index, channel in enumerate(channels):
                if not isinstance(channel, dict) or not channel.get("bearingId") or not channel.get("axis"):
                    raise ValueError(f"invalid IMS channel metadata at index {index} for {test_name}")
                bearing_id = str(channel["bearingId"])
                axis = str(channel["axis"])
                if axis in bearing_axes[bearing_id]:
                    raise ValueError(f"duplicate IMS axis {axis!r} for bearing {bearing_id}")
                bearing_axes[bearing_id][axis] = matrix[:, index]

            started_at = _timestamp(path)
            for bearing_id in sorted(bearing_axes):
                fault_label = labels.get(bearing_id)
                if not fault_label:
                    raise ValueError(f"missing fault label metadata for IMS bearing {bearing_id}")
                yield SignalWindow(
                    dataset_id="nasa-ims",
                    bearing_id=bearing_id,
                    run_id=path.name,
                    started_at=started_at,
                    sampling_hz=sampling_hz,
                    acceleration=bearing_axes[bearing_id],
                    fault_label=str(fault_label),
                    acceleration_unit=unit,
                )
