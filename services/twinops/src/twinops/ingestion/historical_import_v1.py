"""Byte-exact preparation of the registered Forzy historical archive."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from twinops.contracts.timeline_v1_models import HistoricalSensorReadingV1
from twinops.ingestion.history_profiles_v1 import (
    HistoricalRawRowV1,
    HistoricalStoredSampleV1,
    HistoryProfileV1,
    PreparedHistoricalBatchV1,
    registered_profile,
)


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOURCE_TIMESTAMP_RE = re.compile(
    r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r"T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d\.\d{3}$"
)
_EXPECTED_ASSET_ID = "forzy-motor-01"
_EXPECTED_PROFILE = registered_profile("forzy-history-2026-05-19-v1")
_TWINOPS_HISTORY_NAMESPACE = uuid5(NAMESPACE_URL, "forzy://twinops/history/v1")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_prefixed(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _identity(kind: str, *parts: object) -> UUID:
    name = _canonical_json({"kind": kind, "parts": list(parts)})
    return uuid5(_TWINOPS_HISTORY_NAMESPACE, name)


def _validate_profile(profile: HistoryProfileV1) -> None:
    if not isinstance(profile, HistoryProfileV1):
        raise ValueError("profile must be HistoryProfileV1")
    if not profile.profile_id:
        raise ValueError("profile ID must be non-empty")
    if profile.source_size_bytes <= 0:
        raise ValueError("profile source size must be positive")
    if not _SHA256_RE.fullmatch(profile.source_sha256):
        raise ValueError("profile source SHA-256 is invalid")
    if profile.header_records != _EXPECTED_PROFILE.header_records:
        raise ValueError("profile header records do not match the v1 byte contract")
    if profile.encoding != "utf-8":
        raise ValueError("profile encoding must be utf-8")
    if profile.delimiter != ";":
        raise ValueError("profile delimiter must be semicolon")
    if profile.newline != "CRLF":
        raise ValueError("profile newline must be CRLF")
    if profile.final_crlf_required is not True:
        raise ValueError("profile must require a final CRLF")
    if profile.data_record_count <= 0:
        raise ValueError("profile data record count must be positive")
    if profile.sample_count != 2 * profile.data_record_count:
        raise ValueError("profile sample count must equal twice the data record count")
    if profile.operating_cycle_count <= 0:
        raise ValueError("profile operating cycle count must be positive")
    if profile.timezone_name != "America/Sao_Paulo":
        raise ValueError("profile timezone must be America/Sao_Paulo")
    if profile.parser_version != "forzy-history-parser-v1":
        raise ValueError("profile parser version must be forzy-history-parser-v1")
    if profile.contract_version != "1.0":
        raise ValueError("profile contract version must be 1.0")
    if not math.isfinite(profile.gap_seconds) or profile.gap_seconds != 15.0:
        raise ValueError("profile gap seconds must be exactly 15.0")


def _validate_ingested_at(ingested_at: datetime) -> datetime:
    if not isinstance(ingested_at, datetime):
        raise ValueError("ingested_at must be a timezone-aware datetime")
    if ingested_at.tzinfo is None or ingested_at.utcoffset() is None:
        raise ValueError("ingested_at must be a timezone-aware datetime")
    normalized = ingested_at.astimezone(timezone.utc)
    if normalized.microsecond % 1_000:
        raise ValueError("ingested_at must have exact millisecond precision")
    return normalized


def _validate_source_bytes(source_bytes: bytes, profile: HistoryProfileV1) -> str:
    if not isinstance(source_bytes, bytes):
        raise ValueError("historical source must be bytes")

    bom_signatures = (
        b"\x00\x00\xfe\xff",
        b"\xff\xfe\x00\x00",
        b"\xef\xbb\xbf",
        b"\xfe\xff",
        b"\xff\xfe",
    )
    if any(source_bytes.startswith(signature) for signature in bom_signatures):
        raise ValueError("historical source must not contain a BOM")

    for index, byte in enumerate(source_bytes):
        if byte == 0x0A and (index == 0 or source_bytes[index - 1] != 0x0D):
            raise ValueError("historical source must use CRLF-only newlines")
        if byte == 0x0D and (
            index + 1 == len(source_bytes) or source_bytes[index + 1] != 0x0A
        ):
            raise ValueError("historical source must use CRLF-only newlines")
    if not source_bytes.endswith(b"\r\n"):
        raise ValueError("historical source must have a final CRLF")

    header_bytes = b"".join(profile.header_records)
    if not source_bytes.startswith(header_bytes):
        raise ValueError("historical source header bytes do not match the profile")
    if len(source_bytes) != profile.source_size_bytes:
        raise ValueError("historical source size does not match the profile")

    source_sha256 = _sha256_prefixed(source_bytes)
    if source_sha256 != profile.source_sha256:
        raise ValueError("historical source SHA-256 does not match the profile")

    try:
        source_bytes.decode(profile.encoding, errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("historical source is not valid UTF-8") from exc
    return source_sha256


def _parse_source_timestamp(value: str, timezone_name: str) -> datetime:
    if not _SOURCE_TIMESTAMP_RE.fullmatch(value):
        raise ValueError(f"invalid source timestamp: {value!r}")
    try:
        local = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError as exc:
        raise ValueError(f"invalid source timestamp: {value!r}") from exc
    return local.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(timezone.utc)


def _finite_measurement(value: str, *, source_line_number: int) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"expected finite numeric measurement at source line {source_line_number}"
        ) from exc
    if not math.isfinite(parsed):
        raise ValueError(
            f"expected finite numeric measurement at source line {source_line_number}"
        )
    return parsed


def _measurement_payload(values: tuple[float, float, float]) -> dict[str, object]:
    velocity, acceleration, temperature = values
    return {
        "vibrationVelocityRms": {
            "value": velocity,
            "unit": "mm/s",
            "semanticConfidence": "inferred_from_datasheet",
        },
        "vibrationAcceleration": {
            "value": acceleration,
            "unit": "g",
            "statistic": "unknown",
            "semanticConfidence": "unconfirmed",
        },
        "temperature": {
            "value": temperature,
            "unit": "degC",
            "semanticConfidence": "inferred_from_datasheet",
        },
    }


def prepare_historical_batch(
    source_bytes: bytes,
    *,
    profile: HistoryProfileV1,
    asset_id: str,
    ingested_at: datetime,
) -> PreparedHistoricalBatchV1:
    """Validate and deterministically prepare one immutable historical batch."""

    _validate_profile(profile)
    if asset_id != _EXPECTED_ASSET_ID:
        raise ValueError(f"unsupported historical asset: {asset_id}")
    imported_at = _validate_ingested_at(ingested_at)
    source_sha256 = _validate_source_bytes(source_bytes, profile)

    batch_identity = _canonical_json(
        {
            "assetId": asset_id,
            "contractVersion": profile.contract_version,
            "parserVersion": profile.parser_version,
            "sourceSha256": source_sha256,
            "timezone": profile.timezone_name,
        }
    ).encode("utf-8")
    batch_id = _sha256_prefixed(batch_identity)

    header_size = len(b"".join(profile.header_records))
    row_payloads = source_bytes[header_size:].split(b"\r\n")
    if not row_payloads or row_payloads[-1] != b"":
        raise ValueError("historical source must have a final CRLF")
    row_payloads = row_payloads[:-1]
    if len(row_payloads) != profile.data_record_count:
        raise ValueError("historical source data record count does not match the profile")

    raw_rows: list[HistoricalRawRowV1] = []
    samples: list[HistoricalStoredSampleV1] = []
    previous_event_at: datetime | None = None
    previous_measurements: dict[str, tuple[float, float, float]] = {}
    byte_start = header_size
    operating_cycle_index = 0

    for record_ordinal, row_payload in enumerate(row_payloads, start=1):
        source_line_number = record_ordinal + 3
        if not row_payload or not row_payload.strip():
            raise ValueError(f"empty historical data row at source line {source_line_number}")
        row_bytes = row_payload + b"\r\n"
        byte_end = byte_start + len(row_bytes)
        row_sha256 = _sha256_prefixed(row_bytes)
        row_text = row_payload.decode("utf-8")
        try:
            columns = next(csv.reader([row_text], delimiter=";", strict=True))
        except csv.Error as exc:
            raise ValueError(
                f"invalid historical columns at source line {source_line_number}"
            ) from exc
        if len(columns) != 9:
            raise ValueError(
                f"historical row must contain exactly 9 columns at source line "
                f"{source_line_number}"
            )

        source_timestamp_text = columns[0]
        event_at = _parse_source_timestamp(
            source_timestamp_text, profile.timezone_name
        )
        if previous_event_at is not None and event_at < previous_event_at:
            raise ValueError(
                f"historical timestamp order decreases at source line {source_line_number}"
            )
        if previous_event_at is None or (
            event_at - previous_event_at
        ).total_seconds() > profile.gap_seconds:
            operating_cycle_index += 1
        operating_cycle_id = _identity(
            "operating-cycle-v1", batch_id, operating_cycle_index
        )
        sample_pair_id = _identity("sample-pair-v1", batch_id, record_ordinal)

        parsed_values = tuple(
            _finite_measurement(value, source_line_number=source_line_number)
            for value in columns[3:9]
        )
        s1_values = (parsed_values[0], parsed_values[1], parsed_values[2])
        s2_values = (parsed_values[3], parsed_values[4], parsed_values[5])
        canonical_values_json = _canonical_json(
            {
                "s1": {
                    "temperature": s1_values[2],
                    "vibrationAcceleration": s1_values[1],
                    "vibrationVelocityRms": s1_values[0],
                },
                "s2": {
                    "temperature": s2_values[2],
                    "vibrationAcceleration": s2_values[1],
                    "vibrationVelocityRms": s2_values[0],
                },
                "sourceTimestampText": source_timestamp_text,
            }
        )
        raw_rows.append(
            HistoricalRawRowV1(
                batch_id=batch_id,
                record_ordinal=record_ordinal,
                source_line_number=source_line_number,
                byte_start=byte_start,
                byte_end=byte_end,
                source_timestamp_text=source_timestamp_text,
                canonical_values_json=canonical_values_json,
                row_sha256=row_sha256,
            )
        )

        for sensor_id, values in (("s1", s1_values), ("s2", s2_values)):
            quality_flags = (
                ["unchanged_from_previous"]
                if previous_measurements.get(sensor_id) == values
                else []
            )
            reading_id = _identity(
                "historical-reading-v1", batch_id, record_ordinal, sensor_id
            )
            reading = HistoricalSensorReadingV1.model_validate(
                {
                    "schemaVersion": "1.0",
                    "readingId": str(reading_id),
                    "samplePairId": str(sample_pair_id),
                    "operatingCycleId": str(operating_cycle_id),
                    "assetId": asset_id,
                    "sensorId": sensor_id,
                    "eventAt": event_at,
                    "sourceTimestampText": source_timestamp_text,
                    "sourceKind": "historical_archive",
                    "timestampQuality": "source_without_offset_assumed_timezone",
                    "measurements": _measurement_payload(values),
                    "qualityFlags": quality_flags,
                    "provenance": {
                        "sourceSystem": "forzy-csv",
                        "batchId": batch_id,
                        "sourceFileSha256": source_sha256,
                        "recordOrdinal": record_ordinal,
                        "sourceLineNumber": source_line_number,
                        "rowSha256": row_sha256,
                        "ingestedAt": imported_at,
                    },
                }
            )
            samples.append(
                HistoricalStoredSampleV1(
                    batch_id=batch_id,
                    record_ordinal=record_ordinal,
                    point_id=str(reading_id),
                    reading=reading,
                )
            )
            previous_measurements[sensor_id] = values

        previous_event_at = event_at
        byte_start = byte_end

    if byte_start != len(source_bytes):
        raise ValueError("historical source row byte reconstruction is incomplete")
    if len(samples) != profile.sample_count:
        raise ValueError("historical source sample count does not match the profile")
    if operating_cycle_index != profile.operating_cycle_count:
        raise ValueError("historical source operating cycle count does not match the profile")

    manifest_json = _canonical_json(
        {
            "assetId": asset_id,
            "batchId": batch_id,
            "contractVersion": profile.contract_version,
            "dataRecordCount": len(raw_rows),
            "delimiter": profile.delimiter,
            "encoding": profile.encoding,
            "finalCrlfRequired": profile.final_crlf_required,
            "gapSeconds": profile.gap_seconds,
            "headerRecordsSha256": [
                _sha256_prefixed(record) for record in profile.header_records
            ],
            "newline": profile.newline,
            "operatingCycleCount": operating_cycle_index,
            "parserVersion": profile.parser_version,
            "profileId": profile.profile_id,
            "rawRowCount": len(raw_rows),
            "sampleCount": len(samples),
            "sourceSha256": source_sha256,
            "sourceSizeBytes": len(source_bytes),
            "timezone": profile.timezone_name,
        }
    )
    manifest_sha256 = _sha256_prefixed(manifest_json.encode("utf-8"))

    return PreparedHistoricalBatchV1(
        batch_id=batch_id,
        asset_id="forzy-motor-01",
        source_bytes=source_bytes,
        source_sha256=source_sha256,
        manifest_json=manifest_json,
        manifest_sha256=manifest_sha256,
        imported_at=imported_at,
        raw_rows=tuple(raw_rows),
        samples=tuple(samples),
    )
