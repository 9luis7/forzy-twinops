"""PostgreSQL adapter unit coverage; live integration remains externally gated."""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
import pytest

from conftest import live_reading, prepared_batch
from twinops.contracts.timeline_v1_models import HistoricalSensorReadingV1
from twinops.storage.historical_repository_v1 import (
    HistoricalBatchConflict,
    HistoricalBatchSummaryV1,
)
from twinops.storage.historical_repository_v1 import HistoricalAssessmentRangeQueryV1
from twinops.storage.postgres_historical_repository_v1 import (
    PostgresHistoricalRepositoryV1,
)
from twinops.storage.sqlite_historical_repository_v1 import (
    _ASSESSMENT_COLUMNS,
    _assessment_manifest_hash,
    _assessment_values,
)
from twinops.timeline.repository_v1 import TimelineReadQueryV1


class _Cursor:
    def __init__(self, rows):
        self._rows = rows
        self.rowcount = 1

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Connection:
    def __init__(self, responses):
        self.closed = False
        self.autocommit = False
        self.info = SimpleNamespace(transaction_status=TransactionStatus.IDLE)
        self.row_factory = dict_row
        self.responses = list(responses)
        self.statements = []
        self.committed = False
        self.rolled_back = False

    def execute(self, sql, parameters=()):
        self.statements.append((" ".join(sql.split()), parameters))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return _Cursor(response)

    def close(self):
        self.closed = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _repository(connection):
    return PostgresHistoricalRepositoryV1(
        "postgresql://unit.invalid/test",
        connection_factory=lambda _: connection,
    )


def _assessment_read_row(stored, batch):
    values = dict(zip(_ASSESSMENT_COLUMNS, _assessment_values(stored), strict=True))
    for field in (
        "training_window_start",
        "training_window_end",
        "window_start",
        "window_end",
        "assessment_at",
    ):
        values[field] = datetime.fromisoformat(values[field][:-1] + "+00:00")
    anchor = next(
        sample.reading
        for sample in batch.samples
        if sample.point_id == str(stored.assessment.anchor_point_id)
    )
    values["anchor_canonical_json"] = json.dumps(
        anchor.model_dump_public(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return values


def test_postgres_assessment_reads_are_single_query_exact_and_range_bounded() -> None:
    from services.twinops.tests.storage.historical_repository_contract import (
        _assessment,
    )

    batch = prepared_batch(1)
    stored = _assessment(batch)
    row = _assessment_read_row(stored, batch)
    range_connection = _Connection([[row]])
    query = HistoricalAssessmentRangeQueryV1(
        asset_id=batch.asset_id,
        batch_id=batch.batch_id,
        from_at=stored.assessment.assessment_at,
        to_at=stored.assessment.assessment_at + timedelta(milliseconds=1),
        sensor_id="s1",
    )

    result = _repository(range_connection).historical_assessments(query)

    assert result.assessments == (stored.assessment,)
    assert set(result.anchors_by_id) == {
        str(stored.assessment.anchor_point_id)
    }
    assert len(range_connection.statements) == 1
    sql, parameters = range_connection.statements[0]
    assert "JOIN historical_samples_v1" in sql
    assert "a.assessment_at>=%s" in sql
    assert "a.assessment_at<%s" in sql
    assert "a.sensor_id=%s" in sql
    assert parameters == (
        batch.batch_id,
        batch.asset_id,
        batch.asset_id,
        query.from_at,
        query.to_at,
        "s1",
    )

    exact_connection = _Connection([[row]])
    exact = _repository(exact_connection).historical_assessment_for_anchor(
        batch.batch_id,
        str(stored.assessment.anchor_point_id),
    )
    assert exact == stored.assessment
    assert len(exact_connection.statements) == 1
    assert "LIMIT 2" in exact_connection.statements[0][0]


def test_postgres_assessment_store_takes_one_global_identity_lock_before_lookup(
    monkeypatch,
) -> None:
    """Catches two batches racing through absent assessment identity rows."""

    from services.twinops.tests.storage.historical_repository_contract import (
        _assessment,
    )

    batch = prepared_batch(1)
    assessments = (
        _assessment(batch, sensor_id="s2", exact_anchor=True),
        _assessment(batch, sensor_id="s1", exact_anchor=True),
    )
    values = tuple(_assessment_values(item) for item in assessments)
    manifest = _assessment_manifest_hash(batch.batch_id, values)
    before = SimpleNamespace(
        prepared=batch,
        summary=SimpleNamespace(
            status="staged",
            assessment_count=0,
            assessment_manifest_sha256=None,
        ),
    )
    after = SimpleNamespace(
        prepared=batch,
        summary=SimpleNamespace(
            status="staged",
            assessment_count=2,
            assessment_manifest_sha256=manifest,
        ),
    )
    connection = _Connection(
        [
            [],  # batch advisory lock
            [],  # global assessment identity advisory lock
            [],  # target-batch inventory
            [],  # global identity owner lookup
            [],  # insert s2
            [],  # insert s1
            [],  # metadata update
        ]
    )
    repository = _repository(connection)
    stored_batches = iter((before, after))
    monkeypatch.setattr(
        repository,
        "_stored_batch",
        lambda *args, **kwargs: next(stored_batches),
    )
    monkeypatch.setattr(
        repository,
        "_stored_assessment_values",
        lambda *args, **kwargs: values,
    )

    result = repository.store_assessments(batch.batch_id, assessments)

    lock_statements = [
        statement
        for statement in connection.statements
        if "pg_advisory_xact_lock" in statement[0]
    ]
    assert lock_statements == [
        (
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (batch.batch_id,),
        ),
        (
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("historical-assessment-global-identity-v1",),
        ),
    ]
    owner_lookup_index = next(
        index
        for index, (sql, _) in enumerate(connection.statements)
        if "assessment_id = ANY" in sql
    )
    assert all(
        connection.statements.index(statement) < owner_lookup_index
        for statement in lock_statements
    )
    assert result.inserted_count == 2
    assert connection.committed is True


def test_postgres_assessment_store_translates_unique_violation_to_domain_conflict(
    monkeypatch,
) -> None:
    from services.twinops.tests.storage.historical_repository_contract import (
        _assessment,
    )

    batch = prepared_batch(1)
    assessment = _assessment(batch, exact_anchor=True)
    before = SimpleNamespace(
        prepared=batch,
        summary=SimpleNamespace(
            status="staged",
            assessment_count=0,
            assessment_manifest_sha256=None,
        ),
    )
    connection = _Connection(
        [
            [],
            [],
            [],
            [],
            psycopg.errors.UniqueViolation("duplicate assessment identity"),
        ]
    )
    repository = _repository(connection)
    monkeypatch.setattr(repository, "_stored_batch", lambda *args, **kwargs: before)

    with pytest.raises(
        HistoricalBatchConflict,
        match="identity conflicts with stored data",
    ):
        repository.store_assessments(batch.batch_id, [assessment])

    assert connection.rolled_back is True
    assert connection.committed is False


def test_postgres_assessment_store_rejects_persisted_partial_set_before_dml(
    monkeypatch,
) -> None:
    from services.twinops.tests.storage.historical_repository_contract import (
        _assessment,
    )

    batch = prepared_batch(1)
    assessments = (
        _assessment(batch, sensor_id="s1", exact_anchor=True),
        _assessment(batch, sensor_id="s2", exact_anchor=True),
    )
    first_values = _assessment_values(assessments[0])
    existing_row = {
        "assessment_id": first_values[0],
        "batch_id": first_values[1],
        "canonical_json": first_values[-1],
    }
    before = SimpleNamespace(
        prepared=batch,
        summary=SimpleNamespace(
            status="staged",
            assessment_count=1,
            assessment_manifest_sha256="sha256:" + "9" * 64,
        ),
    )
    connection = _Connection([[], [], [existing_row], [existing_row]])
    repository = _repository(connection)
    monkeypatch.setattr(repository, "_stored_batch", lambda *args, **kwargs: before)

    with pytest.raises(HistoricalBatchConflict, match="exact assessment set"):
        repository.store_assessments(batch.batch_id, assessments)

    assert connection.rolled_back is True
    assert all(
        not sql.startswith(("INSERT", "UPDATE", "DELETE"))
        for sql, _ in connection.statements
    )


def test_postgres_active_batch_id_reads_only_canonical_parent_metadata() -> None:
    batch_id = "sha256:" + "a" * 64
    connection = _Connection([[{"batch_id": batch_id}]])
    repository = _repository(connection)
    repository._stored_batch = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("metadata identity read must not rehydrate child rows")
    )

    assert repository.active_batch_id("forzy-motor-01") == batch_id
    assert connection.statements == [
        (
            "SELECT batch_id FROM historical_import_batches_v1 "
            "WHERE asset_id=%s AND status='active' ORDER BY batch_id",
            ("forzy-motor-01",),
        )
    ]
    assert connection.closed is True


def test_postgres_active_batch_id_returns_none_without_an_active_row() -> None:
    connection = _Connection([[]])

    assert _repository(connection).active_batch_id("forzy-motor-01") is None
    assert connection.closed is True


def test_postgres_active_batch_summary_is_one_parent_only_metadata_query() -> None:
    batch_id = "sha256:" + "a" * 64
    connection = _Connection(
        [[
            {
                "batch_id": batch_id,
                "asset_id": "forzy-motor-01",
                "status": "active",
                "source_sha256": "sha256:" + "b" * 64,
                "manifest_sha256": "sha256:" + "c" * 64,
                "raw_row_count": 10,
                "sample_count": 20,
                "operating_cycle_count": 2,
                "assessment_count": 5,
                "assessment_manifest_sha256": "sha256:" + "d" * 64,
                "staged_at": datetime(2026, 8, 25, 12, tzinfo=timezone.utc),
                "activated_at": datetime(2026, 8, 25, 13, tzinfo=timezone.utc),
            }
        ]]
    )
    repository = _repository(connection)
    repository._stored_batch = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("runtime summary must not rehydrate source/raw/sample rows")
    )

    result = repository.active_batch_summary("forzy-motor-01")

    assert isinstance(result, HistoricalBatchSummaryV1)
    assert result.batch_id == batch_id
    assert result.assessment_count == 5
    assert len(connection.statements) == 1
    sql, parameters = connection.statements[0]
    assert "historical_import_batches_v1" in sql
    assert "source_bytes" not in sql
    assert "historical_raw_rows_v1" not in sql
    assert "historical_samples_v1" not in sql
    assert parameters == ("forzy-motor-01",)
    assert connection.closed is True


@pytest.mark.parametrize(
    ("rows", "message"),
    (
        (
            [{"batch_id": "not-a-canonical-hash"}],
            "active batch ID is not canonical sha256",
        ),
        (
            [
                {"batch_id": "sha256:" + "a" * 64},
                {"batch_id": "sha256:" + "b" * 64},
            ],
            "multiple active historical batches",
        ),
    ),
)
def test_postgres_active_batch_id_rejects_invalid_active_metadata(
    rows,
    message,
) -> None:
    connection = _Connection([rows])

    with pytest.raises(HistoricalBatchConflict, match=message):
        _repository(connection).active_batch_id("forzy-motor-01")
    assert connection.closed is True


def test_postgres_archive_adapter_uses_active_predicate_and_limit_plus_one() -> None:
    batch = prepared_batch(1)
    connection = _Connection(
        [[{"canonical_json": json.dumps(
            batch.samples[0].reading.model_dump_public(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )}]]
    )
    result = _repository(connection).read_archive_points(
        TimelineReadQueryV1(
            asset_id=batch.asset_id,
            from_at=None,
            to_at=None,
            sensor_id=None,
            metric=None,
            limit=1,
        )
    )

    sql, parameters = connection.statements[0]
    assert "b.status='active'" in sql
    assert "LIMIT %s" in sql
    assert parameters[-1] == 2
    assert [str(point.point_id) for point in result.points] == [
        batch.samples[0].point_id
    ]
    assert connection.closed is True


def test_postgres_timeline_archive_reads_use_direct_point_projection(
    monkeypatch,
) -> None:
    batch = prepared_batch(1)
    canonical_json = json.dumps(
        batch.samples[0].reading.model_dump_public(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    row = {"canonical_json": canonical_json}
    archive_repository = _repository(_Connection([[row]]))
    point_repository = _repository(_Connection([[row], []]))
    pair_repository = _repository(_Connection([[row], []]))

    def fail_deep_revalidation(cls, *args, **kwargs):
        raise AssertionError("timeline adapter must not revalidate deep readings")

    monkeypatch.setattr(
        HistoricalSensorReadingV1,
        "model_validate",
        classmethod(fail_deep_revalidation),
    )
    page = archive_repository.read_archive_points(
        TimelineReadQueryV1(
            asset_id=batch.asset_id,
            from_at=None,
            to_at=None,
            sensor_id=None,
            metric=None,
            limit=1,
        )
    )
    point = point_repository.point_by_id(
        batch.asset_id,
        batch.samples[0].point_id,
    )
    pair = pair_repository.points_for_pair(
        batch.asset_id,
        str(batch.samples[0].reading.sample_pair_id),
    )

    assert [str(item.point_id) for item in page.points] == [
        batch.samples[0].point_id
    ]
    assert str(point.point_id) == batch.samples[0].point_id
    assert [str(item.point_id) for item in pair] == [
        batch.samples[0].point_id
    ]


def test_postgres_timeline_archive_projection_rejects_live_canonical_without_deep_validation(
    monkeypatch,
) -> None:
    batch = prepared_batch(1)
    sample = batch.samples[0]
    canonical = sample.reading.model_dump_public()
    canonical["operatingCycleId"] = None
    canonical["sourceKind"] = "live_collection"
    canonical["timestampQuality"] = "assumed_from_retrieval"
    canonical["provenance"] = {
        "sourceSystem": "forzy-api",
        "readingId": "11111111-1111-4111-8111-111111111111",
        "scheduledAt": canonical["eventAt"],
        "receivedAt": canonical["eventAt"],
        "collectionPolicyId": None,
    }
    row = {
        "canonical_json": json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    }
    deep_calls = 0

    def fail_deep_revalidation(cls, *args, **kwargs):
        nonlocal deep_calls
        deep_calls += 1
        raise AssertionError("timeline adapter must not revalidate deep readings")

    monkeypatch.setattr(
        HistoricalSensorReadingV1,
        "model_validate",
        classmethod(fail_deep_revalidation),
    )
    operations = (
        lambda: _repository(_Connection([[row]])).read_archive_points(
            TimelineReadQueryV1(
                asset_id=batch.asset_id,
                from_at=None,
                to_at=None,
                sensor_id=None,
                metric=None,
                limit=1,
            )
        ),
        lambda: _repository(_Connection([[row], []])).point_by_id(
            batch.asset_id,
            sample.point_id,
        ),
        lambda: _repository(_Connection([[row], []])).points_for_pair(
            batch.asset_id,
            str(sample.reading.sample_pair_id),
        ),
    )

    for operation in operations:
        with pytest.raises(HistoricalBatchConflict, match="failed closed validation"):
            operation()
    assert deep_calls == 0


def test_postgres_live_adapter_projects_and_bulk_loads_policy_associations() -> None:
    scheduled = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    reading = live_reading(
        reading_id="55555555-5555-4555-8555-555555555555",
        sensor_id="s1",
        scheduled_at=scheduled,
        received_at=scheduled + timedelta(microseconds=123_456),
        velocity=0.51,
    )
    canonical_json = json.dumps(
        reading.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    connection = _Connection(
        [
            [{"event_at": scheduled + timedelta(milliseconds=123)}],
            [
                {
                    "reading_id": reading.reading_id,
                    "asset_id": reading.asset_id,
                    "sensor_id": reading.sensor_id,
                    "observed_at": scheduled + timedelta(microseconds=123_456),
                    "received_at": scheduled + timedelta(microseconds=123_456),
                    "payload_hash": reading.payload_hash,
                    "canonical_json": canonical_json,
                }
            ],
            [
                {
                    "scheduled_at": scheduled,
                    "policy_id": "forzy-live-window-v1",
                }
            ],
        ]
    )
    result = _repository(connection).read_live_points(
        TimelineReadQueryV1(
            asset_id=reading.asset_id,
            from_at=scheduled,
            to_at=scheduled + timedelta(seconds=1),
            sensor_id=None,
            metric=None,
            limit=1,
        )
    )

    assert len(connection.statements) == 3
    assert "date_trunc('milliseconds',s.observed_at)" in connection.statements[0][0]
    assert "refresh_cycle_policies_v1" in connection.statements[2][0]
    assert result.points[0].event_at.microsecond == 123_000
    assert (
        result.points[0].provenance.collection_policy_id
        == "forzy-live-window-v1"
    )
    assert connection.closed is True
