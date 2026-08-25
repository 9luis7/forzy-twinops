"""PostgreSQL adapter unit coverage; live integration remains externally gated."""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

from conftest import live_reading, prepared_batch
from twinops.storage.postgres_historical_repository_v1 import (
    PostgresHistoricalRepositoryV1,
)
from twinops.timeline.repository_v1 import TimelineReadQueryV1


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

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

    def execute(self, sql, parameters=()):
        self.statements.append((" ".join(sql.split()), parameters))
        return _Cursor(self.responses.pop(0))

    def close(self):
        self.closed = True


def _repository(connection):
    return PostgresHistoricalRepositoryV1(
        "postgresql://unit.invalid/test",
        connection_factory=lambda _: connection,
    )


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
