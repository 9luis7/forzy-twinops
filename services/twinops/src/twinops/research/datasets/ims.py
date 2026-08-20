"""Strict adapter for metadata-mapped NASA IMS numeric vibration files."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

from twinops.research.contracts import SignalWindow
from twinops.research.datasets.common import nonempty, raw_path, sequence_index, started_at
from twinops.research.metadata import LoadedMetadata


def _channel_context(channel: dict[str, Any], *, context: str) -> tuple[object, ...]:
    return (
        nonempty(channel, "windowStateLabel", context=context),
        channel.get("terminalFailureMode"),
        channel.get("lifeFraction"),
        channel.get("temperatureC"),
        channel.get("rpm"),
        channel.get("load"),
    )


def iter_ims(root: str | Path, metadata: LoadedMetadata) -> Iterator[SignalWindow]:
    root_path = Path(root)
    if metadata.dataset_id != "nasa-ims":
        raise ValueError("IMS adapter requires nasa-ims metadata")
    payload = metadata.payload
    files = payload["files"]
    ordered = sorted(
        files.items(),
        key=lambda item: (sequence_index(item[1], context=item[0]), item[0]),
    )
    seen_sequences: set[tuple[str, int]] = set()
    for relative_path, raw_entry in ordered:
        if not isinstance(raw_entry, dict):
            raise ValueError(f"{relative_path}: metadata entry must be an object")
        entry: dict[str, Any] = raw_entry
        run_id = nonempty(entry, "runId", context=relative_path)
        sequence = sequence_index(entry, context=relative_path)
        acquisition_time = started_at(entry, context=relative_path)
        channels = entry.get("channels")
        if not isinstance(channels, list) or not channels:
            raise ValueError(f"{relative_path}: channels must be a non-empty list")
        matrix = np.loadtxt(raw_path(root_path, relative_path), dtype=float, ndmin=2)
        positions: list[int] = []
        bearing_axes: dict[str, dict[str, np.ndarray]] = defaultdict(dict)
        bearing_context: dict[str, tuple[object, ...]] = {}
        for channel_number, raw_channel in enumerate(channels):
            if not isinstance(raw_channel, dict):
                raise ValueError(f"{relative_path}: channel {channel_number} must be an object")
            channel: dict[str, Any] = raw_channel
            index = channel.get("columnIndex")
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise ValueError(f"{relative_path}: columnIndex must be a non-negative integer")
            positions.append(index)
            bearing_id = nonempty(channel, "bearingId", context=relative_path)
            axis = nonempty(channel, "axis", context=relative_path)
            if axis in bearing_axes[bearing_id]:
                raise ValueError(f"{relative_path}: duplicate axis {axis!r} for {bearing_id}")
            context = _channel_context(channel, context=relative_path)
            if bearing_id in bearing_context and bearing_context[bearing_id] != context:
                raise ValueError(f"{relative_path}: channels disagree on per-window state for {bearing_id}")
            bearing_context[bearing_id] = context
            if index >= matrix.shape[1]:
                raise ValueError(f"{relative_path}: columnIndex {index} is outside the raw matrix")
            bearing_axes[bearing_id][axis] = matrix[:, index]
        if sorted(positions) != list(range(matrix.shape[1])):
            raise ValueError(
                f"{relative_path}: columnIndex values must map every raw column exactly once"
            )

        for bearing_id in sorted(bearing_axes):
            sequence_key = (bearing_id, sequence)
            if sequence_key in seen_sequences:
                raise ValueError(f"{relative_path}: duplicate sequenceIndex for bearing {bearing_id}")
            seen_sequences.add(sequence_key)
            state, terminal, life, temperature, rpm, load = bearing_context[bearing_id]
            yield SignalWindow(
                dataset_id="nasa-ims",
                bearing_id=bearing_id,
                run_id=run_id,
                sampling_hz=float(payload["samplingHz"]),
                acceleration=bearing_axes[bearing_id],
                acceleration_unit=str(payload["accelerationUnit"]),
                window_state_label=str(state),
                terminal_failure_mode=terminal,
                sequence_index=sequence,
                started_at=acquisition_time,
                timestamp_quality=nonempty(entry, "timestampQuality", context=relative_path),
                source_relative_path=relative_path,
                metadata_sha256=metadata.metadata_sha256,
                life_fraction=life,
                temperature_c=temperature,
                rpm=rpm,
                load=load,
            )
