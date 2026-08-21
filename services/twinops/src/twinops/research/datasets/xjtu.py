"""Strict adapter for metadata-mapped XJTU-SY numeric CSV windows."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from twinops.research.contracts import SignalWindow
from twinops.research.datasets.common import nonempty, raw_path, sequence_index, started_at
from twinops.research.metadata import LoadedMetadata


def _read_axes(
    path: Path,
    entry: dict[str, Any],
    *,
    context: str,
    expected_rows: int,
) -> dict[str, object]:
    columns = entry.get("columns")
    has_header = entry.get("hasHeader")
    if not isinstance(columns, Mapping) or not columns:
        raise ValueError(f"{context}: columns must explicitly map every source column to an axis")
    if not isinstance(has_header, bool):
        raise ValueError(f"{context}: hasHeader must be boolean")
    if has_header:
        frame = pd.read_csv(path)
        source_columns: dict[object, str] = {}
        for source, raw_axis in columns.items():
            if not isinstance(source, str) or not source:
                raise ValueError(f"{context}: column names must be explicit strings")
            if not isinstance(raw_axis, str) or not raw_axis.strip():
                raise ValueError(f"{context}: axis names must be explicit non-empty strings")
            source_columns[source] = raw_axis.strip()
        if set(frame.columns) != set(source_columns):
            raise ValueError(
                f"{context}: column mapping differs from CSV columns; "
                f"mapped={sorted(source_columns)}, actual={sorted(map(str, frame.columns))}"
            )
    else:
        frame = pd.read_csv(path, header=None)
        source_columns = {}
        for source, raw_axis in columns.items():
            try:
                position = int(source)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{context}: headerless column keys must be integer positions"
                ) from exc
            if position in source_columns:
                raise ValueError(f"{context}: duplicate headerless column position {position}")
            if not isinstance(raw_axis, str) or not raw_axis.strip():
                raise ValueError(f"{context}: axis names must be explicit non-empty strings")
            source_columns[position] = raw_axis.strip()
        if set(source_columns) != set(range(frame.shape[1])):
            raise ValueError(f"{context}: column positions must map every CSV column exactly once")
    if frame.shape[0] != expected_rows:
        raise ValueError(
            f"{context}: row count differs from metadata samplesPerWindow={expected_rows}"
        )
    axes: dict[str, object] = {}
    for source, axis in source_columns.items():
        if not axis.strip() or axis in axes:
            raise ValueError(f"{context}: mapped axes must be unique non-empty strings")
        axes[axis] = pd.to_numeric(frame[source], errors="raise").to_numpy(dtype=float)
    return axes


def iter_xjtu(root: str | Path, metadata: LoadedMetadata) -> Iterator[SignalWindow]:
    root_path = Path(root)
    if metadata.dataset_id != "xjtu-sy":
        raise ValueError("XJTU adapter requires xjtu-sy metadata")
    payload = metadata.payload
    files = payload["files"]
    samples_per_window = payload.get("samplesPerWindow")
    if (
        isinstance(samples_per_window, bool)
        or not isinstance(samples_per_window, int)
        or samples_per_window <= 0
    ):
        raise ValueError("XJTU metadata samplesPerWindow must be a positive integer")
    signal_files: list[tuple[str, dict[str, Any]]] = []
    for relative_path, raw_entry in files.items():
        if not isinstance(raw_entry, dict):
            raise ValueError(f"{relative_path}: metadata entry must be an object")
        kind = raw_entry.get("kind")
        if kind == "source_document":
            continue
        if kind != "signal_window":
            raise ValueError(f"{relative_path}: unknown kind {kind!r}")
        signal_files.append((relative_path, raw_entry))
    ordered = sorted(
        signal_files,
        key=lambda item: (sequence_index(item[1], context=item[0]), item[0]),
    )
    seen_sequences: set[tuple[str, str, int]] = set()
    for relative_path, raw_entry in ordered:
        entry: dict[str, Any] = raw_entry
        bearing_id = nonempty(entry, "bearingId", context=relative_path)
        run_id = nonempty(entry, "runId", context=relative_path)
        sequence = sequence_index(entry, context=relative_path)
        sequence_key = (run_id, bearing_id, sequence)
        if sequence_key in seen_sequences:
            raise ValueError(
                f"{relative_path}: duplicate (runId, bearingId, sequenceIndex)"
            )
        seen_sequences.add(sequence_key)
        path = raw_path(root_path, relative_path)
        yield SignalWindow(
            dataset_id="xjtu-sy",
            bearing_id=bearing_id,
            run_id=run_id,
            sampling_hz=float(payload["samplingHz"]),
            acceleration=_read_axes(
                path,
                entry,
                context=relative_path,
                expected_rows=samples_per_window,
            ),
            acceleration_unit=str(payload["accelerationUnit"]),
            window_state_label=nonempty(entry, "windowStateLabel", context=relative_path),
            terminal_failure_mode=entry.get("terminalFailureMode"),
            sequence_index=sequence,
            started_at=started_at(entry, context=relative_path),
            timestamp_quality=nonempty(entry, "timestampQuality", context=relative_path),
            source_relative_path=relative_path,
            metadata_sha256=metadata.metadata_sha256,
            life_fraction=entry.get("lifeFraction"),
            temperature_c=entry.get("temperatureC"),
            rpm=entry.get("rpm"),
            load=entry.get("load"),
        )
