"""Canonical telemetry curation without interpolation or physical diagnosis."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

import pandas as pd

from twinops.contracts.models import CanonicalSensorReading


CuratedFrame: TypeAlias = pd.DataFrame

_COLUMNS = [
    "received_at",
    "event_at",
    "reading_id",
    "source",
    "asset_tag",
    "sensor_id",
    "velocity_rms",
    "acceleration",
    "temperature",
    "payload_hash",
    "quality_flags",
    "is_new_information",
    "cadence_seconds",
    "cycle_id",
    "operating_state",
    "state_estimated",
]


def curate_samples(
    samples: Sequence[CanonicalSensorReading], *, gap_seconds: float
) -> CuratedFrame:
    """Order readings, mark acquisition quality, and estimate operating cycles.

    Operating state is only a vibration-derived proxy. Gaps are preserved rather
    than interpolated and reset the proxy state, so transition rows must never be
    used to calibrate the steady baseline.
    """

    if gap_seconds <= 0:
        raise ValueError("gap_seconds must be positive")

    rows = [_reading_row(sample) for sample in samples]
    if not rows:
        return pd.DataFrame(columns=_COLUMNS)

    rows.sort(key=lambda row: (row["event_at"], row["sensor_id"], row["reading_id"]))
    previous_payload_by_sensor: dict[str, str] = {}
    sensor_state: dict[str, dict[str, object]] = {}

    for row in rows:
        sensor_id = row["sensor_id"]
        state = sensor_state.setdefault(
            sensor_id, {"event_at": None, "active": None, "cycle_id": 0}
        )
        previous_at = state["event_at"]
        cadence = (
            None
            if previous_at is None
            else (row["event_at"] - previous_at).total_seconds()
        )
        has_gap = cadence is not None and cadence > gap_seconds
        if has_gap:
            state["cycle_id"] = int(state["cycle_id"]) + 1
            state["active"] = None

        flags = list(row["quality_flags"])
        if has_gap and "gap_before" not in flags:
            flags.append("gap_before")

        duplicate = previous_payload_by_sensor.get(sensor_id) == row["payload_hash"]
        if duplicate and "duplicate_payload" not in flags:
            flags.append("duplicate_payload")
        previous_payload_by_sensor[sensor_id] = str(row["payload_hash"])

        active = bool(row["velocity_rms"] > 0.05)
        row.update(
            quality_flags=tuple(flags),
            is_new_information=not duplicate,
            cadence_seconds=cadence,
            cycle_id=int(state["cycle_id"]),
            operating_state=_operating_state(state["active"], active),
            state_estimated=True,
        )
        state["active"] = active
        state["event_at"] = row["event_at"]

    return pd.DataFrame(rows, columns=_COLUMNS)


def _reading_row(sample: CanonicalSensorReading) -> dict[str, object]:
    received_at = pd.Timestamp(sample.received_at)
    event_at = pd.Timestamp(sample.observed_at or sample.received_at)
    return {
        "received_at": received_at,
        "event_at": event_at,
        "reading_id": sample.reading_id,
        "source": sample.source,
        "asset_tag": sample.asset_tag,
        "sensor_id": sample.sensor_id,
        "velocity_rms": sample.measurements.vibration_velocity_rms.value,
        # Acceleration is retained for audit only while statistic remains unknown.
        "acceleration": sample.measurements.vibration_acceleration.value,
        "temperature": sample.measurements.temperature.value,
        "payload_hash": sample.payload_hash,
        "quality_flags": tuple(sample.quality_flags),
    }


def _operating_state(previous_active: object, active: bool) -> str:
    if previous_active is None:
        return "startup" if active else "stopped"
    if bool(previous_active) and active:
        return "steady"
    if bool(previous_active) and not active:
        return "shutdown"
    if not bool(previous_active) and active:
        return "startup"
    return "stopped"
