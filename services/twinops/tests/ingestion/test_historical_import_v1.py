from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from importlib.util import find_spec
import json
from typing import Iterable
from uuid import UUID

import pytest


_PROFILE_MODULE = "twinops.ingestion.history_profiles_v1"
_IMPORT_MODULE = "twinops.ingestion.historical_import_v1"
_IMPORTER_AVAILABLE = find_spec(_PROFILE_MODULE) is not None and find_spec(_IMPORT_MODULE) is not None

if _IMPORTER_AVAILABLE:
    from twinops.ingestion.historical_import_v1 import (
        _prepare_historical_batch_for_profile,
        prepare_historical_batch,
    )
    from twinops.ingestion.history_profiles_v1 import HistoryProfileV1, registered_profile


pytestmark = pytest.mark.skipif(
    not _IMPORTER_AVAILABLE,
    reason="registered importer is the intentional Task A3 RED",
)

HEADER_RECORDS = (
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
)
VALID_ROWS = (
    "2026-05-19T11:46:10.921;AQID;BAUG;0.04;0;27;0.05;0.01;34",
    "2026-05-19T11:46:25.921;AQID;BAUG;0.04;0;27;0.05;0.01;34",
    "2026-05-19T11:46:40.922;AQID;BAUG;0.06;0;27;0.05;0.01;34",
    "2026-05-19T11:46:40.922;CQoL;DA0O;0.06;0;27;0.05;0.01;34",
)
INGESTED_AT = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)


def _source(rows: Iterable[str] = VALID_ROWS) -> bytes:
    return b"".join(HEADER_RECORDS) + b"".join(
        row.encode("utf-8") + b"\r\n" for row in rows
    )


def _profile(
    source_bytes: bytes,
    *,
    data_record_count: int | None = None,
    sample_count: int | None = None,
    operating_cycle_count: int = 2,
) -> HistoryProfileV1:
    records = len(source_bytes.splitlines(keepends=True)[3:])
    expected_records = records if data_record_count is None else data_record_count
    expected_samples = 2 * expected_records if sample_count is None else sample_count
    return HistoryProfileV1(
        profile_id="synthetic-task-a3-v1",
        source_size_bytes=len(source_bytes),
        source_sha256="sha256:" + sha256(source_bytes).hexdigest(),
        header_records=HEADER_RECORDS,
        encoding="utf-8",
        delimiter=";",
        newline="CRLF",
        final_crlf_required=True,
        data_record_count=expected_records,
        sample_count=expected_samples,
        operating_cycle_count=operating_cycle_count,
        timezone_name="America/Sao_Paulo",
        parser_version="forzy-history-parser-v1",
        contract_version="1.0",
        gap_seconds=15.0,
    )


def _prepare(source_bytes: bytes, profile: HistoryProfileV1 | None = None):
    return _prepare_historical_batch_for_profile(
        source_bytes,
        profile=profile or _profile(source_bytes),
        asset_id="forzy-motor-01",
        ingested_at=INGESTED_AT,
    )


def _replace_row(source_bytes: bytes, old: bytes, new: bytes) -> bytes:
    assert old in source_bytes
    return source_bytes.replace(old, new, 1)


def test_public_preparation_requires_the_exact_registered_profile_before_parsing() -> None:
    source_bytes = _source()
    custom_profile = _profile(source_bytes)

    with pytest.raises(ValueError, match="exact registered profile"):
        prepare_historical_batch(
            b"\xef\xbb\xbfnot-a-csv",
            profile=custom_profile,
            asset_id="forzy-motor-01",
            ingested_at=INGESTED_AT,
        )
    with pytest.raises(ValueError, match="exact registered profile"):
        prepare_historical_batch(
            source_bytes,
            profile=custom_profile,
            asset_id="forzy-motor-01",
            ingested_at=INGESTED_AT,
        )

    with pytest.raises(ValueError, match="BOM"):
        prepare_historical_batch(
            b"\xef\xbb\xbfnot-a-csv",
            profile=registered_profile("forzy-history-2026-05-19-v1"),
            asset_id="forzy-motor-01",
            ingested_at=INGESTED_AT,
        )


def test_preparation_preserves_exact_rows_and_builds_two_ordered_samples_per_row() -> None:
    source_bytes = _source()
    prepared = _prepare(source_bytes)

    reconstructed = b"".join(
        source_bytes[row.byte_start : row.byte_end] for row in prepared.raw_rows
    )
    expected_rows = b"".join(source_bytes.splitlines(keepends=True)[3:])

    assert prepared.source_bytes == source_bytes
    assert reconstructed == expected_rows
    assert len(prepared.raw_rows) == 4
    assert len(prepared.samples) == 8
    assert [sample.reading.sensor_id for sample in prepared.samples] == [
        "s1",
        "s2",
        "s1",
        "s2",
        "s1",
        "s2",
        "s1",
        "s2",
    ]
    assert prepared.samples[0].reading.sample_pair_id == prepared.samples[1].reading.sample_pair_id
    assert prepared.samples[0].record_ordinal == prepared.samples[1].record_ordinal == 1


def test_raw_row_boundaries_hashes_and_canonical_values_are_independently_reconstructable() -> None:
    source_bytes = _source()
    prepared = _prepare(source_bytes)
    first = prepared.raw_rows[0]
    first_bytes = VALID_ROWS[0].encode("utf-8") + b"\r\n"

    assert first.record_ordinal == 1
    assert first.source_line_number == 4
    assert first.byte_start == len(b"".join(HEADER_RECORDS))
    assert first.byte_end == first.byte_start + len(first_bytes)
    assert source_bytes[first.byte_start : first.byte_end] == first_bytes
    assert first.row_sha256 == "sha256:" + sha256(first_bytes).hexdigest()
    assert json.loads(first.canonical_values_json) == {
        "s1": {
            "temperature": 27.0,
            "vibrationAcceleration": 0.0,
            "vibrationVelocityRms": 0.04,
        },
        "s2": {
            "temperature": 34.0,
            "vibrationAcceleration": 0.01,
            "vibrationVelocityRms": 0.05,
        },
        "sourceTimestampText": "2026-05-19T11:46:10.921",
    }
    assert first.canonical_values_json == json.dumps(
        json.loads(first.canonical_values_json),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def test_timestamps_are_strictly_assumed_in_sao_paulo_and_persisted_as_utc() -> None:
    prepared = _prepare(_source())
    first_pair = prepared.samples[:2]

    assert {sample.reading.event_at for sample in first_pair} == {
        datetime(2026, 5, 19, 14, 46, 10, 921_000, tzinfo=timezone.utc)
    }
    assert {sample.reading.source_timestamp_text for sample in first_pair} == {
        "2026-05-19T11:46:10.921"
    }
    assert {
        sample.reading.model_dump_public()["eventAt"] for sample in first_pair
    } == {"2026-05-19T14:46:10.921Z"}
    assert {sample.reading.provenance.ingested_at for sample in first_pair} == {
        INGESTED_AT
    }


@pytest.mark.parametrize(
    ("timestamp", "message"),
    [
        ("2018-02-17T23:30:00.000", "ambiguous"),
        ("2018-11-04T00:30:00.000", "nonexistent"),
    ],
)
def test_sao_paulo_dst_transition_wall_times_fail_closed(
    timestamp: str, message: str
) -> None:
    row = VALID_ROWS[0].replace("2026-05-19T11:46:10.921", timestamp)
    source_bytes = _source((row,))

    with pytest.raises(ValueError, match=message):
        _prepare(
            source_bytes,
            _profile(source_bytes, operating_cycle_count=1),
        )


def test_sao_paulo_normal_historical_wall_time_resolves_to_one_utc_instant() -> None:
    timestamp = "2018-05-19T11:46:10.921"
    row = VALID_ROWS[0].replace("2026-05-19T11:46:10.921", timestamp)
    source_bytes = _source((row,))

    prepared = _prepare(
        source_bytes,
        _profile(source_bytes, operating_cycle_count=1),
    )

    assert {sample.reading.event_at for sample in prepared.samples} == {
        datetime(2018, 5, 19, 14, 46, 10, 921_000, tzinfo=timezone.utc)
    }
    assert {sample.reading.source_timestamp_text for sample in prepared.samples} == {
        timestamp
    }
    assert {
        sample.reading.model_dump_public()["eventAt"] for sample in prepared.samples
    } == {"2018-05-19T14:46:10.921Z"}


def test_pair_level_cycle_segmentation_is_strictly_greater_than_fifteen_seconds() -> None:
    prepared = _prepare(_source())
    cycle_ids = [sample.reading.operating_cycle_id for sample in prepared.samples]

    assert cycle_ids[0] == cycle_ids[1] == cycle_ids[2] == cycle_ids[3]
    assert cycle_ids[4] == cycle_ids[5] == cycle_ids[6] == cycle_ids[7]
    assert cycle_ids[0] != cycle_ids[4]
    assert len(set(cycle_ids)) == 2


def test_repeated_measurements_are_retained_and_flagged_per_sensor() -> None:
    prepared = _prepare(_source())
    flags = [sample.reading.quality_flags for sample in prepared.samples]

    assert flags == [
        [],
        [],
        ["unchanged_from_previous"],
        ["unchanged_from_previous"],
        [],
        ["unchanged_from_previous"],
        ["unchanged_from_previous"],
        ["unchanged_from_previous"],
    ]


def test_preparation_and_all_identities_are_deterministic_for_the_same_ingested_at() -> None:
    source_bytes = _source()
    profile = _profile(source_bytes)

    first = _prepare(source_bytes, profile)
    second = _prepare(source_bytes, profile)

    assert first == second
    assert first.batch_id == second.batch_id
    assert first.manifest_sha256 == second.manifest_sha256
    assert [sample.point_id for sample in first.samples] == [
        sample.point_id for sample in second.samples
    ]
    assert all(UUID(sample.point_id).version == 5 for sample in first.samples)
    assert all(UUID(str(sample.reading.sample_pair_id)).version == 5 for sample in first.samples)
    assert all(UUID(str(sample.reading.operating_cycle_id)).version == 5 for sample in first.samples)
    assert all(sample.point_id == str(sample.reading.reading_id) for sample in first.samples)
    assert len({sample.point_id for sample in first.samples}) == 8


def test_batch_and_manifest_hashes_bind_canonical_configuration_and_counts() -> None:
    source_bytes = _source()
    prepared = _prepare(source_bytes)
    source_hash = "sha256:" + sha256(source_bytes).hexdigest()
    batch_identity = json.dumps(
        {
            "assetId": "forzy-motor-01",
            "contractVersion": "1.0",
            "parserVersion": "forzy-history-parser-v1",
            "sourceSha256": source_hash,
            "timezone": "America/Sao_Paulo",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    assert prepared.source_sha256 == source_hash
    assert prepared.batch_id == "sha256:" + sha256(batch_identity).hexdigest()
    assert prepared.manifest_sha256 == "sha256:" + sha256(
        prepared.manifest_json.encode("utf-8")
    ).hexdigest()
    manifest = json.loads(prepared.manifest_json)
    assert manifest["batchId"] == prepared.batch_id
    assert manifest["rawRowCount"] == 4
    assert manifest["sampleCount"] == 8
    assert manifest["operatingCycleCount"] == 2
    assert manifest["sourceSizeBytes"] == len(source_bytes)


@pytest.mark.parametrize(
    ("source_bytes", "message"),
    [
        (b"\xef\xbb\xbf" + _source(), "BOM"),
        (_source().replace(b"\r\n", b"\n"), "CRLF"),
        (_source()[:-2], "final CRLF"),
    ],
)
def test_byte_framing_is_rejected_before_decoding(source_bytes: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _prepare(source_bytes, _profile(source_bytes))


def test_exact_header_bytes_are_required_even_when_size_and_hash_match() -> None:
    source_bytes = bytearray(_source())
    source_bytes[0] ^= 0x01
    source_bytes = bytes(source_bytes)

    with pytest.raises(ValueError, match="header"):
        _prepare(source_bytes, _profile(source_bytes))


def test_invalid_utf8_is_rejected_only_after_byte_checks_pass() -> None:
    source_bytes = _replace_row(_source(), b"AQID", b"\xffQID")

    with pytest.raises(ValueError, match="UTF-8"):
        _prepare(source_bytes, _profile(source_bytes))


def test_source_size_is_exact() -> None:
    source_bytes = _source()
    profile = replace(_profile(source_bytes), source_size_bytes=len(source_bytes) + 1)

    with pytest.raises(ValueError, match="size"):
        _prepare(source_bytes, profile)


def test_source_hash_is_exact() -> None:
    source_bytes = _source()
    profile = replace(_profile(source_bytes), source_sha256="sha256:" + "0" * 64)

    with pytest.raises(ValueError, match="SHA-256"):
        _prepare(source_bytes, profile)


def test_a_single_altered_data_byte_is_rejected_by_the_original_profile() -> None:
    source_bytes = _source()
    profile = _profile(source_bytes)
    altered = _replace_row(source_bytes, b";0.04;", b";0.14;")

    assert len(altered) == len(source_bytes)
    with pytest.raises(ValueError, match="SHA-256"):
        _prepare(altered, profile)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda rows: rows[:1] + ("",) + rows[1:], "empty"),
        (lambda rows: (rows[0] + ";unexpected",) + rows[1:], "columns"),
        (
            lambda rows: (
                rows[0].replace(";", ",", 1),
            )
            + rows[1:],
            "columns",
        ),
    ],
)
def test_rows_must_be_nonempty_and_use_the_registered_delimiter(mutate, message: str) -> None:
    source_bytes = _source(mutate(VALID_ROWS))

    with pytest.raises(ValueError, match=message):
        _prepare(source_bytes, _profile(source_bytes))


@pytest.mark.parametrize("token", ["NaN", "Inf", "-Infinity", "1e309"])
def test_measurements_must_be_finite_numeric_values(token: str) -> None:
    rows = (VALID_ROWS[0].replace(";0.04;", f";{token};"),) + VALID_ROWS[1:]
    source_bytes = _source(rows)

    with pytest.raises(ValueError, match="finite numeric"):
        _prepare(source_bytes, _profile(source_bytes))


def test_source_timestamps_must_be_non_decreasing() -> None:
    rows = (VALID_ROWS[1], VALID_ROWS[0]) + VALID_ROWS[2:]
    source_bytes = _source(rows)

    with pytest.raises(ValueError, match="timestamp order"):
        _prepare(source_bytes, _profile(source_bytes))


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-05-19T11:46:10.921-03:00",
        "2026-05-19T14:46:10.921Z",
        "2026-02-30T11:46:10.921",
        "2026-05-19 11:46:10.921",
    ],
)
def test_source_timestamps_require_exact_offset_free_millisecond_lexemes(timestamp: str) -> None:
    rows = (VALID_ROWS[0].replace("2026-05-19T11:46:10.921", timestamp),) + VALID_ROWS[1:]
    source_bytes = _source(rows)

    with pytest.raises(ValueError, match="source timestamp"):
        _prepare(source_bytes, _profile(source_bytes))


def test_profile_row_sample_and_cycle_counts_are_all_enforced() -> None:
    source_bytes = _source()

    with pytest.raises(ValueError, match="data record count"):
        _prepare(source_bytes, _profile(source_bytes, data_record_count=5, sample_count=10))
    with pytest.raises(ValueError, match="sample count"):
        _prepare(source_bytes, _profile(source_bytes, sample_count=9))
    with pytest.raises(ValueError, match="operating cycle count"):
        _prepare(source_bytes, _profile(source_bytes, operating_cycle_count=3))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("encoding", "latin-1"),
        ("delimiter", ","),
        ("newline", "LF"),
        ("final_crlf_required", False),
        ("gap_seconds", 0),
    ],
)
def test_injected_profiles_cannot_loosen_the_v1_byte_contract(field: str, value: object) -> None:
    profile = replace(_profile(_source()), **{field: value})

    with pytest.raises(ValueError, match="profile"):
        _prepare(_source(), profile)


def test_asset_and_ingestion_timestamp_are_strict() -> None:
    source_bytes = _source()
    profile = _profile(source_bytes)

    with pytest.raises(ValueError, match="asset"):
        _prepare_historical_batch_for_profile(
            source_bytes,
            profile=profile,
            asset_id="another-asset",
            ingested_at=INGESTED_AT,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        _prepare_historical_batch_for_profile(
            source_bytes,
            profile=profile,
            asset_id="forzy-motor-01",
            ingested_at=INGESTED_AT.replace(tzinfo=None),
        )
    with pytest.raises(ValueError, match="millisecond"):
        _prepare_historical_batch_for_profile(
            source_bytes,
            profile=profile,
            asset_id="forzy-motor-01",
            ingested_at=INGESTED_AT + timedelta(microseconds=1),
        )
