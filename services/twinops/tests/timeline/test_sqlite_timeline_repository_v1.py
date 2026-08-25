"""Focused SQLite timeline reader behavior."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import sqlite3
from uuid import NAMESPACE_URL, uuid5

from conftest import live_reading, prepared_batch, store_live_reading
import pytest

from twinops.contracts.timeline_v1_models import HistoricalSensorReadingV1
from twinops.storage.historical_repository_v1 import HistoricalBatchConflict
from twinops.storage.sqlite_historical_repository_v1 import (
    SQLiteHistoricalRepositoryV1,
)
from twinops.timeline.repository_v1 import (
    TimelineReadQueryV1,
    timeline_order_key_v1,
)


def _metadata_only_sqlite_repository(tmp_path, rows):
    path = tmp_path / "active-batch-id.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE historical_import_batches_v1 ("
            "batch_id TEXT NOT NULL,asset_id TEXT NOT NULL,status TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO historical_import_batches_v1 "
            "(batch_id,asset_id,status) VALUES (?,?,?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()
    repository = SQLiteHistoricalRepositoryV1(path)
    repository._stored_batch = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("metadata identity read must not rehydrate child rows")
    )
    return repository


def test_sqlite_active_batch_id_reads_only_canonical_parent_metadata(tmp_path) -> None:
    batch_id = "sha256:" + "a" * 64
    repository = _metadata_only_sqlite_repository(
        tmp_path,
        ((batch_id, "forzy-motor-01", "active"),),
    )

    assert repository.active_batch_id("forzy-motor-01") == batch_id


def test_sqlite_active_batch_id_returns_none_without_an_active_row(tmp_path) -> None:
    repository = _metadata_only_sqlite_repository(
        tmp_path,
        (("sha256:" + "a" * 64, "forzy-motor-01", "staged"),),
    )

    assert repository.active_batch_id("forzy-motor-01") is None


@pytest.mark.parametrize(
    ("rows", "message"),
    (
        (
            (("not-a-canonical-hash", "forzy-motor-01", "active"),),
            "active batch ID is not canonical sha256",
        ),
        (
            (
                ("sha256:" + "a" * 64, "forzy-motor-01", "active"),
                ("sha256:" + "b" * 64, "forzy-motor-01", "active"),
            ),
            "multiple active historical batches",
        ),
    ),
)
def test_sqlite_active_batch_id_rejects_invalid_active_metadata(
    tmp_path,
    rows,
    message,
) -> None:
    repository = _metadata_only_sqlite_repository(tmp_path, rows)

    with pytest.raises(HistoricalBatchConflict, match=message):
        repository.active_batch_id("forzy-motor-01")


def test_sqlite_reads_only_original_points_from_the_active_archive(
    sqlite_timeline_repository,
) -> None:
    staged = prepared_batch(0)
    active = prepared_batch(1)
    sqlite_timeline_repository.stage_batch(staged)
    sqlite_timeline_repository.stage_batch(active)
    sqlite_timeline_repository.activate_batch(
        asset_id=active.asset_id,
        batch_id=active.batch_id,
        expected_active_batch_id=None,
    )

    result = sqlite_timeline_repository.read_archive_points(
        TimelineReadQueryV1(
            asset_id=active.asset_id,
            from_at=None,
            to_at=None,
            sensor_id=None,
            metric=None,
            limit=10,
        )
    )

    assert result.has_more is False
    assert len(result.points) == len(active.samples)
    assert tuple(map(timeline_order_key_v1, result.points)) == tuple(
        sorted(map(timeline_order_key_v1, result.points))
    )
    assert {str(point.point_id) for point in result.points} == {
        sample.point_id for sample in active.samples
    }
    assert {
        point.provenance.batch_id for point in result.points
    } == {active.batch_id}
    assert [
        point.measurements.vibration_velocity_rms.value for point in result.points
    ] == [0.14, 0.15, 0.16, 0.17]
    limited = sqlite_timeline_repository.read_archive_points(
        TimelineReadQueryV1(
            asset_id=active.asset_id,
            from_at=None,
            to_at=None,
            sensor_id=None,
            metric=None,
            limit=1,
        )
    )
    assert limited.has_more is True
    assert len(limited.points) == 2
    after_first = sqlite_timeline_repository.read_archive_points(
        TimelineReadQueryV1(
            asset_id=active.asset_id,
            from_at=None,
            to_at=None,
            sensor_id=None,
            metric=None,
            after=timeline_order_key_v1(result.points[0]),
            limit=10,
        )
    )
    assert after_first.points == result.points[1:]


def test_sqlite_timeline_archive_reads_use_direct_point_projection(
    sqlite_timeline_repository,
    monkeypatch,
) -> None:
    active = prepared_batch(1)
    sqlite_timeline_repository.stage_batch(active)
    sqlite_timeline_repository.activate_batch(
        asset_id=active.asset_id,
        batch_id=active.batch_id,
        expected_active_batch_id=None,
    )

    def fail_deep_revalidation(cls, *args, **kwargs):
        raise AssertionError("timeline adapter must not revalidate deep readings")

    monkeypatch.setattr(
        HistoricalSensorReadingV1,
        "model_validate",
        classmethod(fail_deep_revalidation),
    )
    page = sqlite_timeline_repository.read_archive_points(
        TimelineReadQueryV1(
            asset_id=active.asset_id,
            from_at=None,
            to_at=None,
            sensor_id=None,
            metric=None,
            limit=10,
        )
    )
    point = sqlite_timeline_repository.point_by_id(
        active.asset_id,
        active.samples[0].point_id,
    )
    pair = sqlite_timeline_repository.points_for_pair(
        active.asset_id,
        str(active.samples[0].reading.sample_pair_id),
    )

    expected_pair_ids = {
        sample.point_id
        for sample in active.samples
        if sample.reading.sample_pair_id
        == active.samples[0].reading.sample_pair_id
    }
    assert {str(item.point_id) for item in page.points} == {
        sample.point_id for sample in active.samples
    }
    assert str(point.point_id) == active.samples[0].point_id
    assert {str(item.point_id) for item in pair} == expected_pair_ids


def test_sqlite_reads_live_points_with_deterministic_ids_and_nullable_policy(
    sqlite_database_path,
    sqlite_timeline_repository,
) -> None:
    scheduled = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    readings = (
        live_reading(
            reading_id="11111111-1111-4111-8111-111111111111",
            sensor_id="s1",
            scheduled_at=scheduled,
            received_at=scheduled + timedelta(microseconds=123_999),
            velocity=0.11,
        ),
        live_reading(
            reading_id="22222222-2222-4222-8222-222222222222",
            sensor_id="s1",
            scheduled_at=scheduled + timedelta(seconds=5),
            received_at=scheduled + timedelta(seconds=5, microseconds=654_321),
            velocity=0.21,
        ),
        live_reading(
            reading_id="33333333-3333-4333-8333-333333333333",
            sensor_id="s2",
            scheduled_at=scheduled + timedelta(seconds=5),
            received_at=scheduled + timedelta(seconds=5, microseconds=654_321),
            velocity=0.31,
        ),
    )
    store_live_reading(
        sqlite_database_path,
        readings[0],
        collection_policy_id=None,
    )
    for reading in readings[1:]:
        store_live_reading(
            sqlite_database_path,
            reading,
            collection_policy_id="forzy-live-window-v1",
        )

    result = sqlite_timeline_repository.read_live_points(
        TimelineReadQueryV1(
            asset_id="forzy-motor-01",
            from_at=scheduled,
            to_at=scheduled + timedelta(seconds=10),
            sensor_id=None,
            metric="vibrationVelocityRms",
            limit=10,
        )
    )

    assert result.has_more is False
    assert [point.event_at.microsecond for point in result.points] == [
        123_000,
        654_000,
        654_000,
    ]
    assert {str(point.provenance.reading_id) for point in result.points} == {
        reading.reading_id for reading in readings
    }
    for point in result.points:
        assert str(point.point_id) == str(
            uuid5(
                NAMESPACE_URL,
                "timeline-point-v1|live_collection|"
                + str(point.provenance.reading_id),
            )
        )
    paired = result.points[1:]
    assert len({point.sample_pair_id for point in paired}) == 1
    assert str(paired[0].sample_pair_id) == str(
        uuid5(
            NAMESPACE_URL,
            "timeline-sample-pair-v1|live_collection|forzy-motor-01|"
            "2026-08-12T15:00:05.000Z",
        )
    )
    assert [
        point.provenance.collection_policy_id for point in result.points
    ] == [None, "forzy-live-window-v1", "forzy-live-window-v1"]
    narrow = sqlite_timeline_repository.read_live_points(
        TimelineReadQueryV1(
            asset_id="forzy-motor-01",
            from_at=scheduled + timedelta(milliseconds=123),
            to_at=scheduled + timedelta(milliseconds=124),
            sensor_id=None,
            metric=None,
            limit=10,
        )
    )
    assert [point.point_id for point in narrow.points] == [result.points[0].point_id]
    limited = sqlite_timeline_repository.read_live_points(
        TimelineReadQueryV1(
            asset_id="forzy-motor-01",
            from_at=scheduled,
            to_at=scheduled + timedelta(seconds=10),
            sensor_id=None,
            metric=None,
            limit=1,
        )
    )
    assert limited.has_more is True
    assert len(limited.points) == 2
    after_first = sqlite_timeline_repository.read_live_points(
        TimelineReadQueryV1(
            asset_id="forzy-motor-01",
            from_at=scheduled,
            to_at=scheduled + timedelta(seconds=10),
            sensor_id=None,
            metric=None,
            after=timeline_order_key_v1(result.points[0]),
            limit=10,
        )
    )
    assert after_first.points == result.points[1:]


def test_sqlite_point_and_pair_lookup_use_only_active_archive_and_persisted_live(
    sqlite_database_path,
    sqlite_timeline_repository,
) -> None:
    hidden = prepared_batch(0)
    active = prepared_batch(1)
    for batch in (hidden, active):
        sqlite_timeline_repository.stage_batch(batch)
    sqlite_timeline_repository.activate_batch(
        asset_id=active.asset_id,
        batch_id=active.batch_id,
        expected_active_batch_id=None,
    )
    scheduled = datetime(2026, 8, 12, 15, tzinfo=timezone.utc)
    live = live_reading(
        reading_id="44444444-4444-4444-8444-444444444444",
        sensor_id="s1",
        scheduled_at=scheduled,
        received_at=scheduled + timedelta(milliseconds=100),
        velocity=0.41,
    )
    store_live_reading(
        sqlite_database_path,
        live,
        collection_policy_id="forzy-live-window-v1",
    )
    database_before = sha256(sqlite_database_path.read_bytes()).digest()
    inventory_before = sorted(path.name for path in sqlite_database_path.parent.iterdir())

    active_point = sqlite_timeline_repository.point_by_id(
        active.asset_id, active.samples[0].point_id
    )
    hidden_point = sqlite_timeline_repository.point_by_id(
        hidden.asset_id, hidden.samples[0].point_id
    )
    live_point_id = str(
        uuid5(
            NAMESPACE_URL,
            f"timeline-point-v1|live_collection|{live.reading_id}",
        )
    )
    live_point = sqlite_timeline_repository.point_by_id(active.asset_id, live_point_id)

    assert str(active_point.point_id) == active.samples[0].point_id
    assert hidden_point is None
    assert str(live_point.provenance.reading_id) == live.reading_id
    archive_pair = sqlite_timeline_repository.points_for_pair(
        active.asset_id, str(active.samples[0].reading.sample_pair_id)
    )
    live_pair = sqlite_timeline_repository.points_for_pair(
        active.asset_id, str(live_point.sample_pair_id)
    )
    assert {str(point.point_id) for point in archive_pair} == {
        sample.point_id
        for sample in active.samples
        if sample.reading.sample_pair_id == active.samples[0].reading.sample_pair_id
    }
    assert [str(point.point_id) for point in live_pair] == [live_point_id]
    assert sha256(sqlite_database_path.read_bytes()).digest() == database_before
    assert sorted(path.name for path in sqlite_database_path.parent.iterdir()) == inventory_before
