"""SQLite implementation of the immutable historical repository boundary."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sqlite3

from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    HistoricalAssessmentV1,
    HistoricalSensorReadingV1,
    parse_public_utc_millis_v1,
    serialize_public_utc_millis_v1,
)
from twinops.ingestion.history_profiles_v1 import (
    HistoricalRawRowV1,
    HistoricalStoredSampleV1,
    PreparedHistoricalBatchV1,
)
from twinops.storage.historical_repository_v1 import (
    ActivateHistoryResultV1,
    AssessmentStoreResultV1,
    HistoricalBatchConflict,
    HistoricalBatchSummaryV1,
    StageHistoryResultV1,
    StoredHistoricalAssessmentV1,
)
from twinops.storage.schema_migrations import (
    read_deployment_identity,
    verify_schema_version,
)


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ASSET_ID = "forzy-motor-01"
_MANIFEST_KEYS = frozenset(
    {
        "assetId",
        "batchId",
        "contractVersion",
        "dataRecordCount",
        "delimiter",
        "encoding",
        "finalCrlfRequired",
        "gapSeconds",
        "headerRecordsSha256",
        "newline",
        "operatingCycleCount",
        "parserVersion",
        "profileId",
        "rawRowCount",
        "sampleCount",
        "sourceSha256",
        "sourceSizeBytes",
        "timezone",
    }
)
_BATCH_COLUMNS = (
    "batch_id",
    "asset_id",
    "source_name",
    "source_sha256",
    "source_bytes",
    "source_size_bytes",
    "encoding",
    "delimiter",
    "newline",
    "raw_row_count",
    "sample_count",
    "operating_cycle_count",
    "timezone_name",
    "parser_version",
    "contract_version",
    "imported_at",
    "status",
    "manifest_json",
    "manifest_sha256",
    "assessment_count",
    "assessment_manifest_sha256",
    "staged_at",
    "activated_at",
)
_RAW_COLUMNS = (
    "batch_id",
    "record_ordinal",
    "source_line_number",
    "byte_start",
    "byte_end",
    "source_timestamp_text",
    "canonical_values_json",
    "row_sha256",
)
_SAMPLE_COLUMNS = (
    "reading_id",
    "batch_id",
    "record_ordinal",
    "source_line_number",
    "sample_pair_id",
    "operating_cycle_id",
    "asset_id",
    "sensor_id",
    "observed_at",
    "vibration_velocity_rms",
    "vibration_acceleration",
    "temperature",
    "quality_flags_json",
    "payload_sha256",
    "canonical_json",
)
_ASSESSMENT_COLUMNS = (
    "assessment_id",
    "batch_id",
    "fold_id",
    "sensor_id",
    "operating_cycle_id",
    "training_window_start",
    "training_window_end",
    "window_start",
    "window_end",
    "assessment_at",
    "anchor_point_id",
    "status",
    "anomaly_score",
    "deterioration_score",
    "model_family",
    "model_version",
    "model_hash",
    "fold_hash",
    "report_hash",
    "canonical_json",
)
_POLICY_COLUMNS = (
    "schema_version",
    "policy_id",
    "asset_id",
    "timezone_name",
    "active_weekdays_json",
    "window_start_local",
    "window_end_local",
    "poll_interval_seconds",
    "gap_threshold_seconds",
    "effective_from",
    "effective_to",
    "configuration_hash",
)
_BATCH_SELECT = ",".join(_BATCH_COLUMNS)
_RAW_SELECT = ",".join(_RAW_COLUMNS)
_SAMPLE_SELECT = ",".join(_SAMPLE_COLUMNS)
_ASSESSMENT_SELECT = ",".join(_ASSESSMENT_COLUMNS)
_POLICY_SELECT = ",".join(_POLICY_COLUMNS)

ConnectionFactory = Callable[[Path], sqlite3.Connection]


@dataclass(frozen=True)
class _PreparedFacts:
    batch: PreparedHistoricalBatchV1
    manifest: dict[str, object]
    source_name: str
    imported_at_text: str
    operating_cycle_count: int
    raw_values: tuple[tuple[object, ...], ...]
    sample_values: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class _StoredBatch:
    summary: HistoricalBatchSummaryV1
    prepared: PreparedHistoricalBatchV1


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


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise HistoricalBatchConflict(f"{label} is not canonical sha256")
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _decode_canonical_json(value: object, label: str) -> object:
    if not isinstance(value, str) or not value:
        raise HistoricalBatchConflict(f"{label} is not non-empty JSON text")
    try:
        parsed = json.loads(value, parse_constant=_reject_json_constant)
        canonical = _canonical_json(parsed)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HistoricalBatchConflict(f"{label} is invalid canonical JSON") from exc
    if canonical != value:
        raise HistoricalBatchConflict(f"{label} is not canonical JSON")
    return parsed


def _utc_millis(value: datetime, label: str) -> str:
    try:
        return serialize_public_utc_millis_v1(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalBatchConflict(f"{label} is not an exact UTC millisecond") from exc


def _parse_stored_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise HistoricalBatchConflict(f"stored {label} is not text")
    try:
        return parse_public_utc_millis_v1(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalBatchConflict(f"stored {label} is invalid") from exc


def _now_utc_millis() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=(now.microsecond // 1_000) * 1_000)


def _manifest_int(manifest: dict[str, object], key: str) -> int:
    value = manifest[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoricalBatchConflict(f"manifest {key} is not a non-negative integer")
    return value


def _measurement_values(body: dict[str, object]) -> tuple[float, float, float]:
    measurements = body["measurements"]
    if not isinstance(measurements, dict):
        raise HistoricalBatchConflict("historical reading measurements are malformed")
    try:
        values = (
            measurements["vibrationVelocityRms"]["value"],
            measurements["vibrationAcceleration"]["value"],
            measurements["temperature"]["value"],
        )
    except (KeyError, TypeError) as exc:
        raise HistoricalBatchConflict(
            "historical reading measurements are incomplete"
        ) from exc
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in values
    ):
        raise HistoricalBatchConflict("historical reading measurements are not finite")
    return tuple(float(value) for value in values)


def _validate_prepared_batch_inner(batch: PreparedHistoricalBatchV1) -> _PreparedFacts:
    if not isinstance(batch, PreparedHistoricalBatchV1):
        raise HistoricalBatchConflict("batch must be PreparedHistoricalBatchV1")
    if batch.asset_id != _ASSET_ID:
        raise HistoricalBatchConflict("historical batch asset is unsupported")
    _require_sha256(batch.batch_id, "batch ID")
    _require_sha256(batch.source_sha256, "source hash")
    _require_sha256(batch.manifest_sha256, "manifest hash")
    if type(batch.source_bytes) is not bytes:
        raise HistoricalBatchConflict("historical source must be exact bytes")
    if _sha256_prefixed(batch.source_bytes) != batch.source_sha256:
        raise HistoricalBatchConflict("historical source hash mismatch")
    imported_at_text = _utc_millis(batch.imported_at, "imported_at")

    manifest_value = _decode_canonical_json(batch.manifest_json, "batch manifest")
    if not isinstance(manifest_value, dict) or set(manifest_value) != _MANIFEST_KEYS:
        raise HistoricalBatchConflict("historical manifest shape mismatch")
    manifest = manifest_value
    if _sha256_prefixed(batch.manifest_json.encode("utf-8")) != batch.manifest_sha256:
        raise HistoricalBatchConflict("historical manifest hash mismatch")

    source_lines = batch.source_bytes.splitlines(keepends=True)
    if len(source_lines) != len(batch.raw_rows) + 3 or any(
        not line.endswith(b"\r\n") for line in source_lines
    ):
        raise HistoricalBatchConflict("historical source framing mismatch")
    header_records = tuple(source_lines[:3])
    header_hashes = [_sha256_prefixed(record) for record in header_records]

    source_name = manifest["profileId"]
    if not isinstance(source_name, str) or not source_name:
        raise HistoricalBatchConflict("historical profile ID is invalid")
    fixed_manifest_values = {
        "assetId": batch.asset_id,
        "batchId": batch.batch_id,
        "contractVersion": "1.0",
        "dataRecordCount": len(batch.raw_rows),
        "delimiter": ";",
        "encoding": "utf-8",
        "finalCrlfRequired": True,
        "gapSeconds": 15.0,
        "headerRecordsSha256": header_hashes,
        "newline": "CRLF",
        "parserVersion": "forzy-history-parser-v1",
        "rawRowCount": len(batch.raw_rows),
        "sampleCount": len(batch.samples),
        "sourceSha256": batch.source_sha256,
        "sourceSizeBytes": len(batch.source_bytes),
        "timezone": "America/Sao_Paulo",
    }
    for key, expected in fixed_manifest_values.items():
        if manifest[key] != expected or type(manifest[key]) is not type(expected):
            raise HistoricalBatchConflict(f"historical manifest {key} mismatch")
    for key in (
        "dataRecordCount",
        "rawRowCount",
        "sampleCount",
        "operatingCycleCount",
        "sourceSizeBytes",
    ):
        _manifest_int(manifest, key)

    batch_identity = _canonical_json(
        {
            "assetId": batch.asset_id,
            "contractVersion": manifest["contractVersion"],
            "parserVersion": manifest["parserVersion"],
            "sourceSha256": batch.source_sha256,
            "timezone": manifest["timezone"],
        }
    ).encode("utf-8")
    if _sha256_prefixed(batch_identity) != batch.batch_id:
        raise HistoricalBatchConflict("historical batch identity mismatch")

    if type(batch.raw_rows) is not tuple or type(batch.samples) is not tuple:
        raise HistoricalBatchConflict("prepared historical rows must be immutable tuples")

    raw_values: list[tuple[object, ...]] = []
    raw_by_ordinal: dict[int, tuple[HistoricalRawRowV1, dict[str, object]]] = {}
    byte_start = sum(len(record) for record in header_records)
    for expected_ordinal, row in enumerate(batch.raw_rows, start=1):
        if not isinstance(row, HistoricalRawRowV1):
            raise HistoricalBatchConflict("prepared historical row type mismatch")
        if (
            row.batch_id != batch.batch_id
            or row.record_ordinal != expected_ordinal
            or row.source_line_number != expected_ordinal + 3
            or row.byte_start != byte_start
            or row.byte_end <= row.byte_start
            or row.byte_end > len(batch.source_bytes)
        ):
            raise HistoricalBatchConflict("historical raw row identity/offset mismatch")
        exact_row_bytes = batch.source_bytes[row.byte_start : row.byte_end]
        if exact_row_bytes != source_lines[expected_ordinal + 2]:
            raise HistoricalBatchConflict("historical raw row bytes mismatch")
        if _sha256_prefixed(exact_row_bytes) != row.row_sha256:
            raise HistoricalBatchConflict("historical raw row hash mismatch")
        try:
            source_timestamp = exact_row_bytes[:-2].decode("utf-8").split(";", 1)[0]
        except UnicodeDecodeError as exc:
            raise HistoricalBatchConflict("historical raw row is not UTF-8") from exc
        if source_timestamp != row.source_timestamp_text:
            raise HistoricalBatchConflict("historical raw row timestamp mismatch")
        canonical_values = _decode_canonical_json(
            row.canonical_values_json,
            "historical raw values",
        )
        if not isinstance(canonical_values, dict) or (
            canonical_values.get("sourceTimestampText") != row.source_timestamp_text
        ):
            raise HistoricalBatchConflict("historical raw values mismatch")
        _require_sha256(row.row_sha256, "raw row hash")
        raw_by_ordinal[row.record_ordinal] = (row, canonical_values)
        raw_values.append(
            (
                row.batch_id,
                row.record_ordinal,
                row.source_line_number,
                row.byte_start,
                row.byte_end,
                row.source_timestamp_text,
                row.canonical_values_json,
                row.row_sha256,
            )
        )
        byte_start = row.byte_end
    if byte_start != len(batch.source_bytes):
        raise HistoricalBatchConflict("historical raw rows do not reconstruct source")

    sample_values: list[tuple[object, ...]] = []
    pair_members: dict[int, dict[str, dict[str, object]]] = {}
    seen_point_ids: set[str] = set()
    expected_order = [
        (ordinal, sensor_id)
        for ordinal in range(1, len(batch.raw_rows) + 1)
        for sensor_id in ("s1", "s2")
    ]
    actual_order: list[tuple[int, str]] = []
    for sample in batch.samples:
        if not isinstance(sample, HistoricalStoredSampleV1):
            raise HistoricalBatchConflict("prepared historical sample type mismatch")
        if sample.batch_id != batch.batch_id or sample.record_ordinal not in raw_by_ordinal:
            raise HistoricalBatchConflict("historical sample batch/ordinal mismatch")
        body = sample.reading.model_dump_public()
        try:
            reading = HistoricalSensorReadingV1.model_validate(body)
        except Exception as exc:
            raise HistoricalBatchConflict(
                "historical sample failed closed Pydantic validation"
            ) from exc
        body = reading.model_dump_public()
        canonical_json = _canonical_json(body)
        if str(reading.reading_id) != sample.point_id or sample.point_id in seen_point_ids:
            raise HistoricalBatchConflict("historical sample reading identity mismatch")
        seen_point_ids.add(sample.point_id)
        raw_row, raw_body = raw_by_ordinal[sample.record_ordinal]
        provenance = body["provenance"]
        if not isinstance(provenance, dict):
            raise HistoricalBatchConflict("historical sample provenance is malformed")
        if (
            reading.asset_id != batch.asset_id
            or reading.source_timestamp_text != raw_row.source_timestamp_text
            or reading.provenance.batch_id != batch.batch_id
            or reading.provenance.source_file_sha256 != batch.source_sha256
            or reading.provenance.record_ordinal != raw_row.record_ordinal
            or reading.provenance.source_line_number != raw_row.source_line_number
            or reading.provenance.row_sha256 != raw_row.row_sha256
            or _utc_millis(reading.provenance.ingested_at, "sample ingestedAt")
            != imported_at_text
        ):
            raise HistoricalBatchConflict("historical sample provenance mismatch")
        sensor_values = raw_body.get(reading.sensor_id)
        if not isinstance(sensor_values, dict):
            raise HistoricalBatchConflict("historical raw sensor values are missing")
        expected_measurements = (
            sensor_values.get("vibrationVelocityRms"),
            sensor_values.get("vibrationAcceleration"),
            sensor_values.get("temperature"),
        )
        if _measurement_values(body) != tuple(
            float(value) for value in expected_measurements
        ):
            raise HistoricalBatchConflict("historical sample measurements mismatch")
        quality_flags_json = _canonical_json(body["qualityFlags"])
        sample_values.append(
            (
                sample.point_id,
                sample.batch_id,
                sample.record_ordinal,
                reading.provenance.source_line_number,
                str(reading.sample_pair_id),
                str(reading.operating_cycle_id),
                reading.asset_id,
                reading.sensor_id,
                _utc_millis(reading.event_at, "sample eventAt"),
                *_measurement_values(body),
                quality_flags_json,
                _sha256_prefixed(canonical_json.encode("utf-8")),
                canonical_json,
            )
        )
        actual_order.append((sample.record_ordinal, reading.sensor_id))
        pair_members.setdefault(sample.record_ordinal, {})[reading.sensor_id] = body

    if actual_order != expected_order:
        raise HistoricalBatchConflict("historical samples are not exact ordered pairs")
    for members in pair_members.values():
        if set(members) != {"s1", "s2"}:
            raise HistoricalBatchConflict("historical sample pair is incomplete")
        left = members["s1"]
        right = members["s2"]
        for key in (
            "samplePairId",
            "operatingCycleId",
            "eventAt",
            "sourceTimestampText",
        ):
            if left[key] != right[key]:
                raise HistoricalBatchConflict("historical sample pair identity mismatch")

    operating_cycle_count = len(
        {sample.reading.operating_cycle_id for sample in batch.samples}
    )
    if manifest["operatingCycleCount"] != operating_cycle_count:
        raise HistoricalBatchConflict("historical operating-cycle count mismatch")

    return _PreparedFacts(
        batch=batch,
        manifest=manifest,
        source_name=source_name,
        imported_at_text=imported_at_text,
        operating_cycle_count=operating_cycle_count,
        raw_values=tuple(raw_values),
        sample_values=tuple(sample_values),
    )


def _validate_prepared_batch(batch: PreparedHistoricalBatchV1) -> _PreparedFacts:
    try:
        return _validate_prepared_batch_inner(batch)
    except HistoricalBatchConflict:
        raise
    except Exception as exc:
        raise HistoricalBatchConflict("prepared historical batch is invalid") from exc


def _row_values(row: sqlite3.Row, columns: tuple[str, ...]) -> tuple[object, ...]:
    return tuple(row[column] for column in columns)


def _assessment_values(
    stored: StoredHistoricalAssessmentV1,
) -> tuple[object, ...]:
    if not isinstance(stored, StoredHistoricalAssessmentV1):
        raise HistoricalBatchConflict("assessment must be StoredHistoricalAssessmentV1")
    body = stored.assessment.model_dump_public()
    try:
        assessment = HistoricalAssessmentV1.model_validate(body)
    except Exception as exc:
        raise HistoricalBatchConflict(
            "historical assessment failed closed Pydantic validation"
        ) from exc
    body = assessment.model_dump_public()
    canonical_json = _canonical_json(body)
    return (
        str(assessment.assessment_id),
        stored.batch_id,
        assessment.fold_id,
        assessment.sensor_id,
        str(assessment.operating_cycle_id),
        body["trainingWindow"]["start"],
        body["trainingWindow"]["end"],
        body["assessmentWindow"]["start"],
        body["assessmentWindow"]["end"],
        body["assessmentAt"],
        str(assessment.anchor_point_id),
        assessment.status,
        assessment.anomaly_score,
        assessment.deterioration_score,
        assessment.model_family,
        assessment.model_version,
        assessment.model_hash,
        assessment.fold_hash,
        assessment.report_hash,
        canonical_json,
    )


def _assessment_manifest_hash(
    batch_id: str,
    values: Sequence[tuple[object, ...]],
) -> str:
    entries = [
        {
            "assessmentId": value[0],
            "payloadSha256": _sha256_prefixed(str(value[-1]).encode("utf-8")),
        }
        for value in sorted(values, key=lambda item: str(item[0]))
    ]
    manifest = _canonical_json(
        {
            "assessmentCount": len(entries),
            "assessments": entries,
            "batchId": batch_id,
        }
    )
    return _sha256_prefixed(manifest.encode("utf-8"))


def _policy_from_row(row: sqlite3.Row) -> CollectionPolicyV1:
    weekdays_text = row["active_weekdays_json"]
    if not isinstance(weekdays_text, str):
        raise ValueError("stored collection policy weekdays are not text")
    try:
        weekdays = json.loads(weekdays_text, parse_constant=_reject_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("stored collection policy weekdays are invalid") from exc
    if json.dumps(weekdays, separators=(",", ":")) != weekdays_text:
        raise ValueError("stored collection policy weekdays are not canonical")
    payload = {
        "schemaVersion": row["schema_version"],
        "collectionPolicyId": row["policy_id"],
        "assetId": row["asset_id"],
        "timezone": row["timezone_name"],
        "activeWeekdays": weekdays,
        "windowStartLocal": row["window_start_local"],
        "windowEndLocal": row["window_end_local"],
        "pollIntervalSeconds": row["poll_interval_seconds"],
        "gapThresholdSeconds": row["gap_threshold_seconds"],
        "effectiveFrom": row["effective_from"],
        "effectiveTo": row["effective_to"],
        "configurationHash": row["configuration_hash"],
    }
    try:
        return CollectionPolicyV1.model_validate(payload)
    except Exception as exc:
        raise ValueError("stored collection policy failed closed validation") from exc


class SQLiteHistoricalRepositoryV1:
    """Stage, verify, and activate immutable historical batches in SQLite."""

    def __init__(
        self,
        path: Path,
        *,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self.path = Path(path)
        self._connection_factory = connection_factory

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(f"historical SQLite database does not exist: {self.path}")
        connection = (
            self._connection_factory(self.path)
            if self._connection_factory is not None
            else sqlite3.connect(self.path, timeout=5)
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        if enabled != 1:
            connection.close()
            raise RuntimeError("SQLite foreign keys could not be enabled")
        if connection.in_transaction:
            connection.close()
            raise RuntimeError("historical repository requires transaction ownership")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _stored_assessment_values(
        connection: sqlite3.Connection,
        prepared: PreparedHistoricalBatchV1,
    ) -> tuple[tuple[object, ...], ...]:
        rows = connection.execute(
            f"SELECT {_ASSESSMENT_SELECT} FROM historical_assessments_v1 "
            "WHERE batch_id=? ORDER BY assessment_id",
            (prepared.batch_id,),
        ).fetchall()
        sample_by_id = {sample.point_id: sample.reading for sample in prepared.samples}
        values: list[tuple[object, ...]] = []
        for row in rows:
            canonical = _decode_canonical_json(
                row["canonical_json"],
                "stored historical assessment",
            )
            if not isinstance(canonical, dict):
                raise HistoricalBatchConflict(
                    "stored historical assessment is not an object"
                )
            try:
                assessment = HistoricalAssessmentV1.model_validate(canonical)
            except Exception as exc:
                raise HistoricalBatchConflict(
                    "stored historical assessment failed closed validation"
                ) from exc
            expected = _assessment_values(
                StoredHistoricalAssessmentV1(
                    batch_id=prepared.batch_id,
                    assessment=assessment,
                )
            )
            if _row_values(row, _ASSESSMENT_COLUMNS) != expected:
                raise HistoricalBatchConflict(
                    "stored historical assessment projection mismatch"
                )
            anchor = sample_by_id.get(str(assessment.anchor_point_id))
            if anchor is None or (
                anchor.sensor_id != assessment.sensor_id
                or anchor.operating_cycle_id != assessment.operating_cycle_id
                or assessment.assessment_at > anchor.event_at
            ):
                raise HistoricalBatchConflict(
                    "stored historical assessment anchor mismatch"
                )
            values.append(expected)
        return tuple(values)

    def _stored_batch(
        self,
        connection: sqlite3.Connection,
        batch_id: str,
        *,
        expected: _PreparedFacts | None = None,
    ) -> _StoredBatch:
        row = connection.execute(
            f"SELECT {_BATCH_SELECT} FROM historical_import_batches_v1 "
            "WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        if row is None:
            raise HistoricalBatchConflict("historical batch does not exist")
        source_bytes = row["source_bytes"]
        if isinstance(source_bytes, memoryview):
            source_bytes = source_bytes.tobytes()
        if type(source_bytes) is not bytes:
            raise HistoricalBatchConflict("stored historical source is not bytes")

        raw_rows = tuple(
            HistoricalRawRowV1(
                batch_id=raw["batch_id"],
                record_ordinal=raw["record_ordinal"],
                source_line_number=raw["source_line_number"],
                byte_start=raw["byte_start"],
                byte_end=raw["byte_end"],
                source_timestamp_text=raw["source_timestamp_text"],
                canonical_values_json=raw["canonical_values_json"],
                row_sha256=raw["row_sha256"],
            )
            for raw in connection.execute(
                f"SELECT {_RAW_SELECT} FROM historical_raw_rows_v1 "
                "WHERE batch_id=? ORDER BY record_ordinal",
                (batch_id,),
            ).fetchall()
        )

        sample_rows = connection.execute(
            f"SELECT {_SAMPLE_SELECT} FROM historical_samples_v1 "
            "WHERE batch_id=? ORDER BY record_ordinal,sensor_id,reading_id",
            (batch_id,),
        ).fetchall()
        samples: list[HistoricalStoredSampleV1] = []
        for sample_row in sample_rows:
            canonical = _decode_canonical_json(
                sample_row["canonical_json"],
                "stored historical sample",
            )
            if not isinstance(canonical, dict):
                raise HistoricalBatchConflict("stored historical sample is not an object")
            try:
                reading = HistoricalSensorReadingV1.model_validate(canonical)
            except Exception as exc:
                raise HistoricalBatchConflict(
                    "stored historical sample failed closed validation"
                ) from exc
            samples.append(
                HistoricalStoredSampleV1(
                    batch_id=sample_row["batch_id"],
                    record_ordinal=sample_row["record_ordinal"],
                    point_id=sample_row["reading_id"],
                    reading=reading,
                )
            )

        prepared = PreparedHistoricalBatchV1(
            batch_id=row["batch_id"],
            asset_id=row["asset_id"],
            source_bytes=source_bytes,
            source_sha256=row["source_sha256"],
            manifest_json=row["manifest_json"],
            manifest_sha256=row["manifest_sha256"],
            imported_at=_parse_stored_timestamp(row["imported_at"], "imported_at"),
            raw_rows=raw_rows,
            samples=tuple(samples),
        )
        facts = _validate_prepared_batch(prepared)
        if expected is not None and prepared != expected.batch:
            raise HistoricalBatchConflict("existing historical batch diverges")

        actual_raw_values = tuple(
            _row_values(raw, _RAW_COLUMNS)
            for raw in connection.execute(
                f"SELECT {_RAW_SELECT} FROM historical_raw_rows_v1 "
                "WHERE batch_id=? ORDER BY record_ordinal",
                (batch_id,),
            ).fetchall()
        )
        actual_sample_values = tuple(
            _row_values(sample, _SAMPLE_COLUMNS)
            for sample in sample_rows
        )
        if actual_raw_values != facts.raw_values:
            raise HistoricalBatchConflict("stored historical raw rows diverge")
        if actual_sample_values != facts.sample_values:
            raise HistoricalBatchConflict("stored historical samples diverge")

        expected_batch_projection = {
            "batch_id": prepared.batch_id,
            "asset_id": prepared.asset_id,
            "source_name": facts.source_name,
            "source_sha256": prepared.source_sha256,
            "source_size_bytes": len(prepared.source_bytes),
            "encoding": "utf-8",
            "delimiter": ";",
            "newline": "CRLF",
            "raw_row_count": len(prepared.raw_rows),
            "sample_count": len(prepared.samples),
            "operating_cycle_count": facts.operating_cycle_count,
            "timezone_name": "America/Sao_Paulo",
            "parser_version": "forzy-history-parser-v1",
            "contract_version": "1.0",
            "imported_at": facts.imported_at_text,
            "manifest_json": prepared.manifest_json,
            "manifest_sha256": prepared.manifest_sha256,
        }
        for column, expected_value in expected_batch_projection.items():
            if row[column] != expected_value:
                raise HistoricalBatchConflict(
                    f"stored historical batch {column} mismatch"
                )
        if row["source_bytes"] != prepared.source_bytes:
            raise HistoricalBatchConflict("stored historical source bytes mismatch")

        status = row["status"]
        if status not in {"staged", "active", "superseded"}:
            raise HistoricalBatchConflict("stored historical batch status is invalid")
        staged_at = _parse_stored_timestamp(row["staged_at"], "staged_at")
        activated_at = (
            None
            if row["activated_at"] is None
            else _parse_stored_timestamp(row["activated_at"], "activated_at")
        )
        if (status == "staged") != (activated_at is None):
            raise HistoricalBatchConflict(
                "stored historical status/activation timestamp mismatch"
            )

        assessment_values = self._stored_assessment_values(connection, prepared)
        assessment_count = row["assessment_count"]
        assessment_manifest_sha256 = row["assessment_manifest_sha256"]
        if assessment_count != len(assessment_values):
            raise HistoricalBatchConflict("historical assessment count mismatch")
        if assessment_values:
            expected_assessment_manifest = _assessment_manifest_hash(
                batch_id,
                assessment_values,
            )
            if assessment_manifest_sha256 != expected_assessment_manifest:
                raise HistoricalBatchConflict(
                    "historical assessment manifest hash mismatch"
                )
        elif assessment_manifest_sha256 is not None:
            raise HistoricalBatchConflict(
                "empty historical assessment set must have no manifest hash"
            )

        return _StoredBatch(
            summary=HistoricalBatchSummaryV1(
                batch_id=prepared.batch_id,
                asset_id=prepared.asset_id,
                status=status,
                source_sha256=prepared.source_sha256,
                manifest_sha256=prepared.manifest_sha256,
                raw_row_count=len(prepared.raw_rows),
                sample_count=len(prepared.samples),
                operating_cycle_count=facts.operating_cycle_count,
                assessment_count=assessment_count,
                assessment_manifest_sha256=assessment_manifest_sha256,
                staged_at=staged_at,
                activated_at=activated_at,
            ),
            prepared=prepared,
        )

    def verify_schema(self, expected_version: str):
        with self._connection() as connection:
            return verify_schema_version(connection, expected_version)

    def target_identity(self):
        with self._connection() as connection:
            return read_deployment_identity(connection)

    def stage_batch(self, batch: PreparedHistoricalBatchV1) -> StageHistoryResultV1:
        facts = _validate_prepared_batch(batch)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM historical_import_batches_v1 WHERE batch_id=?",
                (batch.batch_id,),
            ).fetchone()
            if existing is not None:
                stored = self._stored_batch(
                    connection,
                    batch.batch_id,
                    expected=facts,
                )
                connection.commit()
                return StageHistoryResultV1(
                    batch=stored.summary,
                    inserted=False,
                    writes_performed=0,
                )

            staged_at = _utc_millis(_now_utc_millis(), "staged_at")
            connection.execute(
                "INSERT INTO historical_import_batches_v1 ("
                + _BATCH_SELECT
                + ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    batch.batch_id,
                    batch.asset_id,
                    facts.source_name,
                    batch.source_sha256,
                    sqlite3.Binary(batch.source_bytes),
                    len(batch.source_bytes),
                    "utf-8",
                    ";",
                    "CRLF",
                    len(batch.raw_rows),
                    len(batch.samples),
                    facts.operating_cycle_count,
                    "America/Sao_Paulo",
                    "forzy-history-parser-v1",
                    "1.0",
                    facts.imported_at_text,
                    "staged",
                    batch.manifest_json,
                    batch.manifest_sha256,
                    0,
                    None,
                    staged_at,
                    None,
                ),
            )
            connection.executemany(
                "INSERT INTO historical_raw_rows_v1 ("
                + _RAW_SELECT
                + ") VALUES (?,?,?,?,?,?,?,?)",
                facts.raw_values,
            )
            connection.executemany(
                "INSERT INTO historical_samples_v1 ("
                + _SAMPLE_SELECT
                + ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                facts.sample_values,
            )
            stored = self._stored_batch(
                connection,
                batch.batch_id,
                expected=facts,
            )
            connection.commit()
            return StageHistoryResultV1(
                batch=stored.summary,
                inserted=True,
                writes_performed=1 + len(batch.raw_rows) + len(batch.samples),
            )
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def store_assessments(
        self,
        batch_id: str,
        assessments: Sequence[StoredHistoricalAssessmentV1],
    ) -> AssessmentStoreResultV1:
        _require_sha256(batch_id, "batch ID")
        if not assessments:
            raise ValueError("at least one historical assessment is required")
        expected_values = tuple(_assessment_values(item) for item in assessments)
        if any(value[1] != batch_id for value in expected_values):
            raise HistoricalBatchConflict("historical assessment batch mismatch")
        assessment_ids = [str(value[0]) for value in expected_values]
        if len(assessment_ids) != len(set(assessment_ids)):
            raise HistoricalBatchConflict("duplicate historical assessment identity")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            stored_before = self._stored_batch(connection, batch_id)
            if stored_before.summary.status != "staged":
                raise HistoricalBatchConflict(
                    "historical assessments require a staged batch"
                )
            markers = ",".join("?" for _ in assessment_ids)
            existing_rows = connection.execute(
                f"SELECT assessment_id,canonical_json FROM historical_assessments_v1 "
                f"WHERE assessment_id IN ({markers})",
                assessment_ids,
            ).fetchall()
            existing = {
                row["assessment_id"]: row["canonical_json"]
                for row in existing_rows
            }
            to_insert: list[tuple[object, ...]] = []
            existing_count = 0
            for value in expected_values:
                assessment_id = str(value[0])
                if assessment_id in existing:
                    if existing[assessment_id] != value[-1]:
                        raise HistoricalBatchConflict(
                            "existing historical assessment diverges"
                        )
                    existing_count += 1
                else:
                    to_insert.append(value)
            if to_insert:
                connection.executemany(
                    "INSERT INTO historical_assessments_v1 ("
                    + _ASSESSMENT_SELECT
                    + ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    to_insert,
                )
                all_values = self._stored_assessment_values(
                    connection,
                    stored_before.prepared,
                )
                manifest_hash = _assessment_manifest_hash(batch_id, all_values)
                cursor = connection.execute(
                    "UPDATE historical_import_batches_v1 "
                    "SET assessment_count=?,assessment_manifest_sha256=? "
                    "WHERE batch_id=? AND status='staged'",
                    (len(all_values), manifest_hash, batch_id),
                )
                if cursor.rowcount != 1:
                    raise HistoricalBatchConflict(
                        "historical assessment metadata update failed"
                    )
            else:
                all_values = self._stored_assessment_values(
                    connection,
                    stored_before.prepared,
                )
                manifest_hash = _assessment_manifest_hash(batch_id, all_values)
            stored_after = self._stored_batch(connection, batch_id)
            if stored_after.summary.assessment_manifest_sha256 != manifest_hash:
                raise HistoricalBatchConflict(
                    "historical assessment manifest reread failed"
                )
            connection.commit()
            return AssessmentStoreResultV1(
                batch_id=batch_id,
                inserted_count=len(to_insert),
                existing_count=existing_count,
                total_count=stored_after.summary.assessment_count,
                assessment_manifest_sha256=manifest_hash,
                writes_performed=len(to_insert) + (1 if to_insert else 0),
            )
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def activate_batch(
        self,
        *,
        asset_id: str,
        batch_id: str,
        expected_active_batch_id: str | None,
    ) -> ActivateHistoryResultV1:
        if asset_id != _ASSET_ID:
            raise HistoricalBatchConflict("historical activation asset is unsupported")
        _require_sha256(batch_id, "batch ID")
        if expected_active_batch_id is not None:
            _require_sha256(expected_active_batch_id, "expected active batch ID")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            target_row = connection.execute(
                "SELECT batch_id,asset_id,status "
                "FROM historical_import_batches_v1 WHERE batch_id=?",
                (batch_id,),
            ).fetchone()
            active_rows = connection.execute(
                "SELECT batch_id FROM historical_import_batches_v1 "
                "WHERE asset_id=? AND status='active' ORDER BY batch_id",
                (asset_id,),
            ).fetchall()
            if target_row is None:
                raise HistoricalBatchConflict("activation target does not exist")
            if len(active_rows) > 1:
                raise HistoricalBatchConflict("multiple active historical batches")
            current_active_id = active_rows[0]["batch_id"] if active_rows else None
            if current_active_id != expected_active_batch_id:
                raise HistoricalBatchConflict("expected active historical batch mismatch")
            if target_row["asset_id"] != asset_id:
                raise HistoricalBatchConflict("activation target asset mismatch")

            target = self._stored_batch(connection, batch_id)
            if current_active_id == batch_id:
                if target.summary.status != "active":
                    raise HistoricalBatchConflict("activation target status mismatch")
                connection.commit()
                return ActivateHistoryResultV1(
                    asset_id=asset_id,
                    batch_id=batch_id,
                    previous_active_batch_id=current_active_id,
                    active_batch_id=batch_id,
                    activated=False,
                    assessment_count=target.summary.assessment_count,
                    assessment_manifest_sha256=(
                        target.summary.assessment_manifest_sha256
                    ),
                    writes_performed=0,
                )
            if target.summary.status != "staged":
                raise HistoricalBatchConflict("activation target must be staged")

            if current_active_id is not None:
                current = self._stored_batch(connection, current_active_id)
                if current.summary.status != "active":
                    raise HistoricalBatchConflict("current active batch status mismatch")
                cursor = connection.execute(
                    "UPDATE historical_import_batches_v1 SET status='superseded' "
                    "WHERE batch_id=? AND asset_id=? AND status='active'",
                    (current_active_id, asset_id),
                )
                if cursor.rowcount != 1:
                    raise HistoricalBatchConflict("active batch supersede failed")

            activated_at = _utc_millis(_now_utc_millis(), "activated_at")
            cursor = connection.execute(
                "UPDATE historical_import_batches_v1 "
                "SET status='active',activated_at=? "
                "WHERE batch_id=? AND asset_id=? AND status='staged'",
                (activated_at, batch_id, asset_id),
            )
            if cursor.rowcount != 1:
                raise HistoricalBatchConflict("historical batch activation failed")

            reread_active = connection.execute(
                "SELECT batch_id FROM historical_import_batches_v1 "
                "WHERE asset_id=? AND status='active' ORDER BY batch_id",
                (asset_id,),
            ).fetchall()
            if len(reread_active) != 1 or reread_active[0]["batch_id"] != batch_id:
                raise HistoricalBatchConflict("active historical batch reread failed")
            activated = self._stored_batch(connection, batch_id)
            connection.commit()
            return ActivateHistoryResultV1(
                asset_id=asset_id,
                batch_id=batch_id,
                previous_active_batch_id=current_active_id,
                active_batch_id=activated.summary.batch_id,
                activated=True,
                assessment_count=activated.summary.assessment_count,
                assessment_manifest_sha256=(
                    activated.summary.assessment_manifest_sha256
                ),
                writes_performed=1 + (1 if current_active_id is not None else 0),
            )
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def active_batch(self, asset_id: str) -> HistoricalBatchSummaryV1 | None:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT batch_id FROM historical_import_batches_v1 "
                "WHERE asset_id=? AND status='active' ORDER BY batch_id",
                (asset_id,),
            ).fetchall()
            if len(rows) > 1:
                raise HistoricalBatchConflict("multiple active historical batches")
            if not rows:
                return None
            return self._stored_batch(connection, rows[0]["batch_id"]).summary

    def reconstruct_source(self, batch_id: str) -> bytes:
        _require_sha256(batch_id, "batch ID")
        with self._connection() as connection:
            return self._stored_batch(connection, batch_id).prepared.source_bytes

    def collection_policy(self, policy_id: str) -> CollectionPolicyV1 | None:
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT {_POLICY_SELECT} FROM collection_policies_v1 "
                "WHERE policy_id=?",
                (policy_id,),
            ).fetchone()
        return None if row is None else _policy_from_row(row)

    def collection_policies(
        self,
        policy_ids: set[str],
    ) -> dict[str, CollectionPolicyV1]:
        if not policy_ids:
            return {}
        if any(not isinstance(policy_id, str) or not policy_id for policy_id in policy_ids):
            raise ValueError("collection policy IDs must be non-empty strings")
        ordered_ids = sorted(policy_ids)
        markers = ",".join("?" for _ in ordered_ids)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT {_POLICY_SELECT} FROM collection_policies_v1 "
                f"WHERE policy_id IN ({markers}) ORDER BY policy_id",
                ordered_ids,
            ).fetchall()
        policies = [_policy_from_row(row) for row in rows]
        return {policy.collection_policy_id: policy for policy in policies}

    def effective_collection_policy(
        self,
        asset_id: str,
        at: datetime,
    ) -> CollectionPolicyV1 | None:
        try:
            instant = serialize_public_utc_millis_v1(at)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "policy lookup timestamp must be an exact UTC millisecond"
            ) from exc
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT {_POLICY_SELECT} FROM collection_policies_v1 "
                "WHERE asset_id=? AND effective_from<=? "
                "AND (effective_to IS NULL OR ?<effective_to) "
                "ORDER BY effective_from,policy_id LIMIT 2",
                (asset_id, instant, instant),
            ).fetchall()
        policies = [_policy_from_row(row) for row in rows]
        if len(policies) > 1:
            raise RuntimeError("multiple effective collection policies")
        return policies[0] if policies else None
