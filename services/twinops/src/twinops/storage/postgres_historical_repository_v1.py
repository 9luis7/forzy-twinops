"""PostgreSQL implementation of the immutable historical repository boundary."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    HistoricalAssessmentV1,
    HistoricalSensorReadingV1,
    serialize_public_utc_millis_v1,
)
from twinops.ingestion.history_profiles_v1 import (
    HistoricalRawRowV1,
    HistoricalStoredSampleV1,
    PreparedHistoricalBatchV1,
)
from twinops.storage.collection_policy_v1 import (
    _policy_from_row,
    read_collection_policy,
    read_effective_collection_policy,
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
from twinops.storage.sqlite_historical_repository_v1 import (
    _ASSET_ID,
    _ASSESSMENT_COLUMNS,
    _BATCH_COLUMNS,
    _BATCH_SELECT,
    _POLICY_COLUMNS,
    _RAW_COLUMNS,
    _RAW_SELECT,
    _SAMPLE_COLUMNS,
    _SAMPLE_SELECT,
    _StoredBatch,
    _assessment_manifest_hash,
    _assessment_values,
    _decode_canonical_json,
    _now_utc_millis,
    _parse_stored_timestamp,
    _require_sha256,
    _utc_millis,
    _validate_prepared_batch,
)


ConnectionFactory = Callable[[str], object]
_ASSESSMENT_SELECT = ",".join(_ASSESSMENT_COLUMNS)
_POLICY_SELECT = ",".join(_POLICY_COLUMNS)
_TIMESTAMP_COLUMNS = frozenset(
    {
        "imported_at",
        "staged_at",
        "activated_at",
        "observed_at",
        "training_window_start",
        "training_window_end",
        "window_start",
        "window_end",
        "assessment_at",
        "effective_from",
        "effective_to",
    }
)


def _normalised_row(row: dict[str, object]) -> dict[str, object]:
    normalised = dict(row)
    for column in _TIMESTAMP_COLUMNS:
        value = normalised.get(column)
        if isinstance(value, datetime):
            normalised[column] = serialize_public_utc_millis_v1(value)
    return normalised


def _row_values(row: dict[str, object], columns: tuple[str, ...]) -> tuple[object, ...]:
    return tuple(_normalised_row(row)[column] for column in columns)


class PostgresHistoricalRepositoryV1:
    """Stage, verify, and activate immutable historical batches in PostgreSQL."""

    def __init__(
        self,
        database_url: str,
        *,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self.database_url = database_url
        self._connection_factory = connection_factory

    def _connect(self):
        if self._connection_factory is not None:
            return self._connection_factory(self.database_url)
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _stored_assessment_values(
        connection,
        prepared: PreparedHistoricalBatchV1,
    ) -> tuple[tuple[object, ...], ...]:
        rows = connection.execute(
            f"SELECT {_ASSESSMENT_SELECT} FROM historical_assessments_v1 "
            "WHERE batch_id=%s ORDER BY assessment_id",
            (prepared.batch_id,),
        ).fetchall()
        sample_by_id = {sample.point_id: sample.reading for sample in prepared.samples}
        values: list[tuple[object, ...]] = []
        for stored_row in rows:
            row = _normalised_row(stored_row)
            canonical = _decode_canonical_json(
                row["canonical_json"],
                "stored historical assessment",
            )
            if not isinstance(canonical, dict):
                raise HistoricalBatchConflict("stored historical assessment is not an object")
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
                raise HistoricalBatchConflict("stored historical assessment anchor mismatch")
            values.append(expected)
        return tuple(values)

    def _stored_batch(
        self,
        connection,
        batch_id: str,
        *,
        expected=None,
        lock: bool = False,
    ) -> _StoredBatch:
        suffix = " FOR UPDATE" if lock else ""
        batch_row = connection.execute(
            f"SELECT {_BATCH_SELECT} FROM historical_import_batches_v1 "
            f"WHERE batch_id=%s{suffix}",
            (batch_id,),
        ).fetchone()
        if batch_row is None:
            raise HistoricalBatchConflict("historical batch does not exist")
        row = _normalised_row(batch_row)
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
                "WHERE batch_id=%s ORDER BY record_ordinal",
                (batch_id,),
            ).fetchall()
        )
        sample_rows = connection.execute(
            f"SELECT {_SAMPLE_SELECT} FROM historical_samples_v1 "
            "WHERE batch_id=%s ORDER BY record_ordinal,sensor_id,reading_id",
            (batch_id,),
        ).fetchall()
        samples: list[HistoricalStoredSampleV1] = []
        for sample_row in sample_rows:
            sample = _normalised_row(sample_row)
            canonical = _decode_canonical_json(
                sample["canonical_json"],
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
                    batch_id=sample["batch_id"],
                    record_ordinal=sample["record_ordinal"],
                    point_id=sample["reading_id"],
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
                "WHERE batch_id=%s ORDER BY record_ordinal",
                (batch_id,),
            ).fetchall()
        )
        actual_sample_values = tuple(
            _row_values(sample, _SAMPLE_COLUMNS) for sample in sample_rows
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
                raise HistoricalBatchConflict(f"stored historical batch {column} mismatch")
        if source_bytes != prepared.source_bytes:
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
            expected_assessment_manifest = _assessment_manifest_hash(batch_id, assessment_values)
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
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (batch.batch_id,),
            )
            existing = connection.execute(
                "SELECT 1 FROM historical_import_batches_v1 WHERE batch_id=%s FOR UPDATE",
                (batch.batch_id,),
            ).fetchone()
            if existing is not None:
                stored = self._stored_batch(connection, batch.batch_id, expected=facts, lock=True)
                connection.commit()
                return StageHistoryResultV1(stored.summary, False, 0)

            staged_at = _utc_millis(_now_utc_millis(), "staged_at")
            connection.execute(
                "INSERT INTO historical_import_batches_v1 (" + _BATCH_SELECT + ") VALUES ("
                + ",".join(["%s"] * len(_BATCH_COLUMNS)) + ")",
                (
                    batch.batch_id, batch.asset_id, facts.source_name, batch.source_sha256,
                    batch.source_bytes, len(batch.source_bytes), "utf-8", ";", "CRLF",
                    len(batch.raw_rows), len(batch.samples), facts.operating_cycle_count,
                    "America/Sao_Paulo", "forzy-history-parser-v1", "1.0", facts.imported_at_text,
                    "staged", batch.manifest_json, batch.manifest_sha256, 0, None, staged_at, None,
                ),
            )
            raw_markers = ",".join(["%s"] * len(_RAW_COLUMNS))
            for values in facts.raw_values:
                connection.execute(
                    "INSERT INTO historical_raw_rows_v1 (" + _RAW_SELECT + ") VALUES ("
                    + raw_markers + ")", values
                )
            sample_markers = ",".join(["%s"] * len(_SAMPLE_COLUMNS))
            for values in facts.sample_values:
                connection.execute(
                    "INSERT INTO historical_samples_v1 (" + _SAMPLE_SELECT + ") VALUES ("
                    + sample_markers + ")", values
                )
            stored = self._stored_batch(connection, batch.batch_id, expected=facts, lock=True)
            connection.commit()
            return StageHistoryResultV1(
                stored.summary, True, 1 + len(batch.raw_rows) + len(batch.samples)
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
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (batch_id,)
            )
            stored_before = self._stored_batch(connection, batch_id, lock=True)
            if stored_before.summary.status != "staged":
                raise HistoricalBatchConflict("historical assessments require a staged batch")
            existing_rows = connection.execute(
                "SELECT assessment_id,batch_id,canonical_json FROM historical_assessments_v1 "
                "WHERE assessment_id = ANY(%s) FOR UPDATE",
                (assessment_ids,),
            ).fetchall()
            existing = {
                row["assessment_id"]: (row["batch_id"], row["canonical_json"])
                for row in existing_rows
            }
            to_insert: list[tuple[object, ...]] = []
            existing_count = 0
            for value in expected_values:
                assessment_id = str(value[0])
                if assessment_id in existing:
                    existing_batch_id, existing_canonical_json = existing[assessment_id]
                    if existing_batch_id != batch_id:
                        raise HistoricalBatchConflict(
                            "historical assessment identity belongs to another batch"
                        )
                    if existing_canonical_json != value[-1]:
                        raise HistoricalBatchConflict("existing historical assessment diverges")
                    existing_count += 1
                else:
                    to_insert.append(value)
            if to_insert:
                markers = ",".join(["%s"] * len(_ASSESSMENT_COLUMNS))
                for values in to_insert:
                    connection.execute(
                        "INSERT INTO historical_assessments_v1 (" + _ASSESSMENT_SELECT
                        + ") VALUES (" + markers + ")", values
                    )
                all_values = self._stored_assessment_values(connection, stored_before.prepared)
                manifest_hash = _assessment_manifest_hash(batch_id, all_values)
                cursor = connection.execute(
                    "UPDATE historical_import_batches_v1 "
                    "SET assessment_count=%s,assessment_manifest_sha256=%s "
                    "WHERE batch_id=%s AND status='staged'",
                    (len(all_values), manifest_hash, batch_id),
                )
                if cursor.rowcount != 1:
                    raise HistoricalBatchConflict("historical assessment metadata update failed")
            else:
                all_values = self._stored_assessment_values(connection, stored_before.prepared)
                manifest_hash = _assessment_manifest_hash(batch_id, all_values)
            stored_after = self._stored_batch(connection, batch_id, lock=True)
            if stored_after.summary.assessment_manifest_sha256 != manifest_hash:
                raise HistoricalBatchConflict("historical assessment manifest reread failed")
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
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (asset_id,)
            )
            target_row = connection.execute(
                "SELECT batch_id,asset_id,status FROM historical_import_batches_v1 "
                "WHERE batch_id=%s FOR UPDATE", (batch_id,)
            ).fetchone()
            active_rows = connection.execute(
                "SELECT batch_id FROM historical_import_batches_v1 "
                "WHERE asset_id=%s AND status='active' ORDER BY batch_id FOR UPDATE", (asset_id,)
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

            target = self._stored_batch(connection, batch_id, lock=True)
            if current_active_id == batch_id:
                if target.summary.status != "active":
                    raise HistoricalBatchConflict("activation target status mismatch")
                connection.commit()
                return ActivateHistoryResultV1(
                    asset_id, batch_id, current_active_id, batch_id, False,
                    target.summary.assessment_count,
                    target.summary.assessment_manifest_sha256, 0,
                )
            if target.summary.status != "staged":
                raise HistoricalBatchConflict("activation target must be staged")

            if current_active_id is not None:
                current = self._stored_batch(connection, current_active_id, lock=True)
                if current.summary.status != "active":
                    raise HistoricalBatchConflict("current active batch status mismatch")
                cursor = connection.execute(
                    "UPDATE historical_import_batches_v1 SET status='superseded' "
                    "WHERE batch_id=%s AND asset_id=%s AND status='active'",
                    (current_active_id, asset_id),
                )
                if cursor.rowcount != 1:
                    raise HistoricalBatchConflict("active batch supersede failed")

            activated_at = _utc_millis(_now_utc_millis(), "activated_at")
            cursor = connection.execute(
                "UPDATE historical_import_batches_v1 SET status='active',activated_at=%s "
                "WHERE batch_id=%s AND asset_id=%s AND status='staged'",
                (activated_at, batch_id, asset_id),
            )
            if cursor.rowcount != 1:
                raise HistoricalBatchConflict("historical batch activation failed")
            reread_active = connection.execute(
                "SELECT batch_id FROM historical_import_batches_v1 "
                "WHERE asset_id=%s AND status='active' ORDER BY batch_id FOR UPDATE", (asset_id,)
            ).fetchall()
            if len(reread_active) != 1 or reread_active[0]["batch_id"] != batch_id:
                raise HistoricalBatchConflict("active historical batch reread failed")
            activated = self._stored_batch(connection, batch_id, lock=True)
            connection.commit()
            return ActivateHistoryResultV1(
                asset_id, batch_id, current_active_id, activated.summary.batch_id, True,
                activated.summary.assessment_count,
                activated.summary.assessment_manifest_sha256,
                1 + (1 if current_active_id is not None else 0),
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
                "WHERE asset_id=%s AND status='active' ORDER BY batch_id", (asset_id,)
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
            return read_collection_policy(connection, policy_id)

    def collection_policies(self, policy_ids: set[str]) -> dict[str, CollectionPolicyV1]:
        if not policy_ids:
            return {}
        if any(not isinstance(policy_id, str) or not policy_id for policy_id in policy_ids):
            raise ValueError("collection policy IDs must be non-empty strings")
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT {_POLICY_SELECT} FROM collection_policies_v1 "
                "WHERE policy_id = ANY(%s) ORDER BY policy_id", (sorted(policy_ids),)
            ).fetchall()
        policies = [_policy_from_row(row) for row in rows]
        return {policy.collection_policy_id: policy for policy in policies}

    def effective_collection_policy(
        self,
        asset_id: str,
        at: datetime,
    ) -> CollectionPolicyV1 | None:
        with self._connection() as connection:
            return read_effective_collection_policy(connection, asset_id, at)
