"""Closed, immutable registrations for audited historical source files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from twinops.contracts.timeline_v1_models import HistoricalSensorReadingV1, Sha256V1


@dataclass(frozen=True)
class HistoryProfileV1:
    profile_id: str
    source_size_bytes: int
    source_sha256: Sha256V1
    header_records: tuple[bytes, bytes, bytes]
    encoding: Literal["utf-8"]
    delimiter: Literal[";"]
    newline: Literal["CRLF"]
    final_crlf_required: bool
    data_record_count: int
    sample_count: int
    operating_cycle_count: int
    timezone_name: Literal["America/Sao_Paulo"]
    parser_version: str
    contract_version: Literal["1.0"]
    gap_seconds: float


@dataclass(frozen=True)
class HistoricalRawRowV1:
    batch_id: Sha256V1
    record_ordinal: int
    source_line_number: int
    byte_start: int
    byte_end: int
    source_timestamp_text: str
    canonical_values_json: str
    row_sha256: Sha256V1


@dataclass(frozen=True)
class HistoricalStoredSampleV1:
    batch_id: Sha256V1
    record_ordinal: int
    point_id: str
    reading: HistoricalSensorReadingV1


@dataclass(frozen=True)
class PreparedHistoricalBatchV1:
    batch_id: Sha256V1
    asset_id: Literal["forzy-motor-01"]
    source_bytes: bytes
    source_sha256: Sha256V1
    manifest_json: str
    manifest_sha256: Sha256V1
    imported_at: datetime
    raw_rows: tuple[HistoricalRawRowV1, ...]
    samples: tuple[HistoricalStoredSampleV1, ...]


_FORZY_HISTORY_2026_05_19_V1 = HistoryProfileV1(
    profile_id="forzy-history-2026-05-19-v1",
    source_size_bytes=1_096_042,
    source_sha256=(
        "sha256:f09a6613bf6ba3416555a15de6b381bd842474f5f3f33c20660416c7164f0be4"
    ),
    header_records=(
        (
            b";IOLM/Port 1/Attached Device/PDI Data Byte Array;"
            b"IOLM/Port 2/Attached Device/PDI Data Byte Array;4;5;6;7;8;9"
            + b"\r\n"
        ),
        (
            ";PDI Data Byte Array;PDI Data Byte Array;1.1. Velocidade;"
            "1.2. Aceleração;1.3. Temperatura;"
            "2.1. Velocidade;2.2. Aceleração;2.3. Temperatura"
        ).encode("utf-8")
        + b"\r\n",
        b";Byte[];Byte[];Double;Double;Double;Double;Double;Double\r\n",
    ),
    encoding="utf-8",
    delimiter=";",
    newline="CRLF",
    final_crlf_required=True,
    data_record_count=7_183,
    sample_count=14_366,
    operating_cycle_count=204,
    timezone_name="America/Sao_Paulo",
    parser_version="forzy-history-parser-v1",
    contract_version="1.0",
    gap_seconds=15.0,
)

_REGISTERED_PROFILES = {
    _FORZY_HISTORY_2026_05_19_V1.profile_id: _FORZY_HISTORY_2026_05_19_V1,
}


def registered_profile(profile_id: str) -> HistoryProfileV1:
    """Return an audited profile by exact ID, with no fallback behavior."""

    try:
        return _REGISTERED_PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"unknown history profile: {profile_id}") from exc
