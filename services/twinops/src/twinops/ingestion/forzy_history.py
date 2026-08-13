"""Adapter for the native multiline Forzy history export."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import math
from pathlib import Path
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from twinops.contracts.models import CanonicalSensorReading
from twinops.storage.repository import TelemetryRepository


_EXPECTED_COLUMNS = (
    "1.1. Velocidade",
    "1.2. Aceleração",
    "1.3. Temperatura",
    "2.1. Velocidade",
    "2.2. Aceleração",
    "2.3. Temperatura",
)


@dataclass(frozen=True)
class ForzyHistoryImportReport:
    file_hash: str
    rows_read: int
    samples_inserted: int
    duplicates: int


def import_forzy_history(
    path: str | Path,
    repository: TelemetryRepository,
    *,
    asset_tag: str,
    timezone_name: str,
    received_at: datetime,
) -> ForzyHistoryImportReport:
    """Persist a native export through the canonical, idempotent repository."""

    source = Path(path)
    content = source.read_bytes()
    samples = read_forzy_history(
        source,
        asset_tag=asset_tag,
        timezone_name=timezone_name,
        received_at=received_at,
    )
    inserted = 0
    for sample in samples:
        inserted += int(repository.insert_sample(sample))
    return ForzyHistoryImportReport(
        file_hash=sha256(content).hexdigest(),
        rows_read=len(samples) // 2,
        samples_inserted=inserted,
        duplicates=len(samples) - inserted,
    )


def read_forzy_history(
    path: str | Path,
    asset_tag: str,
    timezone_name: str,
    received_at: datetime,
) -> list[CanonicalSensorReading]:
    """Read both sensor streams without changing the source history file.

    The native export has three header rows and timestamps without an offset.
    `timezone_name` is therefore explicit and the assumption is retained as a
    quality flag on every affected sample.
    """

    source = Path(path)
    file_bytes = source.read_bytes()
    file_hash = sha256(file_bytes).hexdigest()
    try:
        source_timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown history timezone: {timezone_name}") from None
    received = _utc(received_at, "received_at")
    samples: list[CanonicalSensorReading] = []

    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=";")
        try:
            first_header = next(reader)
            semantic_header = next(reader)
            unit_header = next(reader)
        except StopIteration:
            raise ValueError("Forzy history header requires three rows") from None
        if (
            len(first_header) != 9
            or len(semantic_header) != 9
            or len(unit_header) != 9
            or tuple(semantic_header[3:9]) != _EXPECTED_COLUMNS
            or tuple(unit_header[3:9]) != ("Double",) * 6
        ):
            raise ValueError("unrecognized Forzy history header")

        for line_number, row in enumerate(reader, start=4):
            if not row or all(not value.strip() for value in row):
                continue
            if len(row) != 9:
                raise ValueError(f"invalid Forzy history row {line_number}")
            observed, timezone_was_assumed = _observed_timestamp(
                row[0], source_timezone
            )
            values = [_finite(value, line_number) for value in row[3:9]]
            for sensor_index, sensor_id in enumerate(("s1", "s2")):
                offset = sensor_index * 3
                identity = f"{file_hash}:{line_number}:{sensor_id}"
                payload_hash = f"sha256:{sha256(identity.encode()).hexdigest()}"
                quality_flags = (
                    [f"observed_timezone_assumed:{timezone_name}"]
                    if timezone_was_assumed
                    else []
                )
                samples.append(
                    CanonicalSensorReading.model_validate(
                        {
                            "schemaVersion": "1.0",
                            "readingId": str(uuid.uuid5(uuid.NAMESPACE_URL, identity)),
                            "source": "forzy-csv",
                            "assetTag": asset_tag,
                            "sensorId": sensor_id,
                            "scheduledAt": None,
                            "observedAt": observed,
                            "receivedAt": received,
                            "measurements": {
                                "vibrationVelocityRms": {
                                    "value": values[offset],
                                    "unit": "mm/s",
                                    "semanticConfidence": "inferred_from_datasheet",
                                },
                                "vibrationAcceleration": {
                                    "value": values[offset + 1],
                                    "unit": "g",
                                    "statistic": "unknown",
                                    "semanticConfidence": "unconfirmed",
                                },
                                "temperature": {
                                    "value": values[offset + 2],
                                    "unit": "degC",
                                    "semanticConfidence": "inferred_from_datasheet",
                                },
                            },
                            "qualityFlags": quality_flags,
                            "payloadHash": payload_hash,
                            "raw": {
                                "sourceFile": source.name,
                                "sourceLine": line_number,
                                "pdiByteArray": row[1 + sensor_index],
                                "values": row[3 + offset : 6 + offset],
                            },
                            "provenance": {
                                "sourceSystem": "forzy-history-export",
                                "ingestedAt": received,
                            },
                        }
                    )
                )
    return samples


def _finite(value: str, line_number: int) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"non-numeric measurement at row {line_number}") from None
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite measurement at row {line_number}")
    return parsed


def _observed_timestamp(value: str, source_timezone: ZoneInfo) -> tuple[str, bool]:
    try:
        observed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"invalid observed timestamp: {value}") from None
    assumed = observed.tzinfo is None or observed.utcoffset() is None
    if assumed:
        observed = observed.replace(tzinfo=source_timezone)
    return _utc(observed, "observed_at"), assumed


def _utc(value: datetime, field: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
