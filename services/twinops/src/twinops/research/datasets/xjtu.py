"""Adapter for original XJTU-SY numeric CSV windows."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd

from twinops.research.contracts import SignalWindow


def _natural_key(path: Path) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name))


def _load_metadata(root: Path) -> dict[str, Any]:
    path = root / "metadata.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"XJTU adapter requires curated metadata at {path}; labels are never guessed from paths"
        )
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(metadata.get("bearings"), dict):
        raise ValueError("XJTU metadata must contain a bearings mapping")
    return metadata


def _read_axes(path: Path) -> dict[str, object]:
    frame = pd.read_csv(path)
    normalized = {str(column).strip().lower(): column for column in frame.columns}
    horizontal = next((original for name, original in normalized.items() if "horizontal" in name), None)
    vertical = next((original for name, original in normalized.items() if "vertical" in name), None)
    if horizontal is None or vertical is None:
        frame = pd.read_csv(path, header=None)
        if frame.shape[1] != 2:
            raise ValueError(f"XJTU file {path} must contain horizontal and vertical channels")
        horizontal, vertical = 0, 1
    return {
        "horizontal": pd.to_numeric(frame[horizontal], errors="raise").to_numpy(dtype=float),
        "vertical": pd.to_numeric(frame[vertical], errors="raise").to_numpy(dtype=float),
    }


def iter_xjtu(root: str | Path) -> Iterator[SignalWindow]:
    """Yield XJTU windows in deterministic chronological order.

    A local ``metadata.json`` is mandatory because bearing labels and operating
    context must come from a curated dataset map, never from a filename.
    """

    root_path = Path(root)
    metadata = _load_metadata(root_path)
    try:
        sampling_hz = float(metadata["samplingHz"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("XJTU metadata requires numeric samplingHz") from exc
    unit = str(metadata.get("accelerationUnit", "g"))

    csv_paths = sorted(root_path.rglob("*.csv"), key=lambda path: (str(path.parent).lower(), _natural_key(path)))
    for path in csv_paths:
        bearing_id = path.parent.name
        bearing_meta = metadata["bearings"].get(bearing_id)
        if not isinstance(bearing_meta, dict) or not bearing_meta.get("faultLabel"):
            raise ValueError(f"missing fault label metadata for XJTU bearing {bearing_id}")
        yield SignalWindow(
            dataset_id="xjtu-sy",
            bearing_id=bearing_id,
            run_id=path.stem,
            sampling_hz=sampling_hz,
            acceleration=_read_axes(path),
            fault_label=str(bearing_meta["faultLabel"]),
            rpm=bearing_meta.get("rpm"),
            load=bearing_meta.get("load"),
            temperature_c=bearing_meta.get("temperatureC"),
            acceleration_unit=unit,
        )
