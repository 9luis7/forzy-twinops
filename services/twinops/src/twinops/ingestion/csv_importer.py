"""Strict, idempotent CSV import into the canonical telemetry contract."""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import uuid

from twinops.contracts.models import CanonicalSensorReading
from twinops.storage.repository import TelemetryRepository


@dataclass(frozen=True)
class CsvImportReport:
    file_hash: str
    rows_read: int
    samples_inserted: int
    duplicates: int
    rejected: int


def _utc(value: datetime, field: str) -> str:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def import_csv(
    path: Path,
    repository: TelemetryRepository,
    asset_tag: str,
    received_at: datetime,
) -> CsvImportReport:
    content = path.read_bytes()
    file_hash = hashlib.sha256(content).hexdigest()
    received = _utc(received_at, "received_at")
    inserted = duplicates = rejected = rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for line_number, row in enumerate(csv.DictReader(stream), start=2):
            rows += 1
            try:
                sensor = row["sensor_id"].lower()
                if sensor not in {"s1", "s2"}:
                    raise ValueError("sensor_id")
                values = [
                    float(row[key])
                    for key in (
                        "vibration_velocity_rms",
                        "vibration_acceleration",
                        "temperature",
                    )
                ]
                if not all(math.isfinite(value) for value in values):
                    raise ValueError("measurements must be finite")
                observed_value = row["observed_at"]
                observed = datetime.fromisoformat(
                    observed_value.replace("Z", "+00:00")
                )
                observed_at = _utc(observed, "observed_at")
                row_identity = f"{file_hash}:{line_number}:{sensor}".encode("utf-8")
                row_hash = f"sha256:{hashlib.sha256(row_identity).hexdigest()}"
                sample = CanonicalSensorReading.model_validate(
                    {
                        "schemaVersion": "1.0",
                        "readingId": str(uuid.uuid4()),
                        "source": "forzy-csv",
                        "assetTag": asset_tag,
                        "sensorId": sensor,
                        "scheduledAt": None,
                        "observedAt": observed_at,
                        "receivedAt": received,
                        "measurements": {
                            "vibrationVelocityRms": {
                                "value": values[0],
                                "unit": "mm/s",
                                "semanticConfidence": "inferred_from_datasheet",
                            },
                            "vibrationAcceleration": {
                                "value": values[1],
                                "unit": "g",
                                "statistic": "unknown",
                                "semanticConfidence": "unconfirmed",
                            },
                            "temperature": {
                                "value": values[2],
                                "unit": "degC",
                                "semanticConfidence": "inferred_from_datasheet",
                            },
                        },
                        "qualityFlags": [],
                        "payloadHash": row_hash,
                        "raw": dict(row),
                        "provenance": {
                            "sourceSystem": "forzy-csv-import",
                            "ingestedAt": received,
                        },
                    }
                )
                inserted_now = repository.insert_sample(sample)
                inserted += int(inserted_now)
                duplicates += int(not inserted_now)
            except (KeyError, TypeError, ValueError):
                rejected += 1
    return CsvImportReport(
        file_hash=file_hash,
        rows_read=rows,
        samples_inserted=inserted,
        duplicates=duplicates,
        rejected=rejected,
    )
