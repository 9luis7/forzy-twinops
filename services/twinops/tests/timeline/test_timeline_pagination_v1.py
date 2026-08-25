"""All-pages archive/live traversal."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from twinops.contracts.timeline_v1_models import TimelinePageV1, TimelinePointV1
from twinops.timeline.cursor_v1 import (
    TimelineCursorCodecV1,
    TimelineCursorConflict,
    TimelinePaginatorV1,
    timeline_query_fingerprint_v1,
)
from twinops.timeline.repository_v1 import (
    TimelineOrderKeyV1,
    TimelineReadQueryV1,
    TimelineSliceV1,
    timeline_order_key_v1,
)


_FIXTURES = Path(__file__).resolve().parents[4] / "contracts/timeline/v1/fixtures"
_BATCH = "sha256:" + "a" * 64
_OTHER_BATCH = "sha256:" + "b" * 64


def _fixture(name: str):
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _point(source: str, index: int) -> TimelinePointV1:
    if source == "archive":
        payload = deepcopy(_fixture("context-historical-candidate.valid.json")["anchor"])
        payload["provenance"]["batchId"] = _BATCH
    else:
        payload = deepcopy(_fixture("live-point.valid.json"))
    payload["eventAt"] = "2026-08-22T12:00:00.123Z"
    payload["samplePairId"] = str(uuid5(NAMESPACE_URL, f"pair-{index // 2}"))
    payload["pointId"] = str(uuid5(NAMESPACE_URL, f"point-{source}-{index}"))
    payload["sensorId"] = "s1" if index % 2 == 0 else "s2"
    if source == "live":
        payload["provenance"]["readingId"] = (
            f"11111111-1111-4{index:03x}-8111-{index:012x}"
        )
        payload["provenance"]["scheduledAt"] = payload["eventAt"]
        payload["provenance"]["receivedAt"] = payload["eventAt"]
    return TimelinePointV1.model_validate(payload)


class _Repository:
    def __init__(self, archive, live, *, batch_id=_BATCH):
        self.archive = tuple(archive)
        self.live = tuple(live)
        self.batch_id = batch_id
        self.source_reads = 0
        self.active_batch_id_calls = 0

    def active_batch_id(self, asset_id):
        assert asset_id == "forzy-motor-01"
        self.active_batch_id_calls += 1
        return self.batch_id

    def active_batch(self, asset_id):
        raise AssertionError("timeline pagination must not call deep active_batch")

    @staticmethod
    def _read(points, query):
        selected = [
            point
            for point in points
            if (query.from_at is None or point.event_at >= query.from_at)
            and (query.to_at is None or point.event_at < query.to_at)
            and (query.sensor_id is None or point.sensor_id == query.sensor_id)
            and (
                query.after is None
                or timeline_order_key_v1(point) > query.after
            )
        ]
        selected.sort(key=timeline_order_key_v1)
        selected = selected[: query.limit + 1]
        return TimelineSliceV1(
            points=tuple(selected),
            has_more=len(selected) > query.limit,
        )

    def read_archive_points(self, query):
        self.source_reads += 1
        return self._read(self.archive, query)

    def read_live_points(self, query):
        self.source_reads += 1
        return self._read(self.live, query)

    def point_by_id(self, asset_id, point_id):
        return next(
            (
                point
                for point in (*self.archive, *self.live)
                if str(point.point_id) == point_id
            ),
            None,
        )


class _SwitchingRepository(_Repository):
    def read_archive_points(self, query):
        self.batch_id = _OTHER_BATCH
        return super().read_archive_points(query)


class _SwitchingLiveRepository(_Repository):
    def read_live_points(self, query):
        self.batch_id = _OTHER_BATCH
        return super().read_live_points(query)


def _query() -> TimelineReadQueryV1:
    return TimelineReadQueryV1(
        asset_id="forzy-motor-01",
        from_at=datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
        to_at=datetime(2026, 8, 22, 12, 1, tzinfo=timezone.utc),
        sensor_id=None,
        metric=None,
        limit=2,
    )


def test_pagination_uses_only_metadata_active_batch_guards() -> None:
    repository = _Repository((), ())
    paginator = TimelinePaginatorV1(repository, TimelineCursorCodecV1())

    page = paginator.page(_query(), cursor=None)

    assert page.active_historical_batch_id == _BATCH
    assert repository.active_batch_id_calls == 2


def test_all_pages_merge_tied_archive_and_live_points_without_deduplication() -> None:
    points = [_point("archive", index) for index in range(3)] + [
        _point("live", index) for index in range(3, 6)
    ]
    repository = _Repository(points[:3][::-1], points[3:][::-1])
    paginator = TimelinePaginatorV1(repository, TimelineCursorCodecV1())
    cursor = None
    returned = []

    while True:
        page = paginator.page(_query(), cursor=cursor)
        returned.extend(page.items)
        if not page.has_more:
            break
        cursor = page.next_cursor

    expected = sorted(points, key=timeline_order_key_v1)
    assert [point.point_id for point in returned] == [
        point.point_id for point in expected
    ]
    assert len({point.point_id for point in returned}) == len(points)


def test_paginator_reuses_validated_cached_archive_tuple_with_identical_pages() -> None:
    points = [_point("archive", index) for index in range(3)] + [
        _point("live", index) for index in range(3, 6)
    ]
    direct_repository = _Repository(points[:3][::-1], points[3:][::-1])
    direct_paginator = TimelinePaginatorV1(
        direct_repository,
        TimelineCursorCodecV1(),
    )
    expected_pages = []
    cursor = None
    while True:
        page = direct_paginator.page(_query(), cursor=cursor)
        expected_pages.append(page.model_dump_public_json())
        if not page.has_more:
            break
        cursor = page.next_cursor

    cached_archive = tuple(sorted(points[:3], key=timeline_order_key_v1))
    cached_repository = _Repository(cached_archive, points[3:][::-1])
    cache_reads = []
    cached_paginator = TimelinePaginatorV1(
        cached_repository,
        TimelineCursorCodecV1(),
        cached_archive_points=lambda active_batch_id: (
            cache_reads.append(active_batch_id) or cached_archive
        ),
    )
    actual_pages = []
    cursor = None
    while True:
        page = cached_paginator.page(_query(), cursor=cursor)
        actual_pages.append(page.model_dump_public_json())
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert actual_pages == expected_pages
    assert cache_reads == [_BATCH] * len(actual_pages)
    assert cached_repository.source_reads == len(actual_pages)


def test_paginator_does_not_redump_already_validated_points_for_page_validation(
    monkeypatch,
) -> None:
    point = _point("archive", 0)
    repository = _Repository((point,), ())
    original_model_validate = TimelinePageV1.model_validate

    def require_validated_point_instances(cls, payload, *args, **kwargs):
        assert all(
            isinstance(item, TimelinePointV1) for item in payload["items"]
        ), "validated timeline points must remain model instances"
        return original_model_validate(payload, *args, **kwargs)

    monkeypatch.setattr(
        TimelinePageV1,
        "model_validate",
        classmethod(require_validated_point_instances),
    )

    page = TimelinePaginatorV1(
        repository,
        TimelineCursorCodecV1(),
    ).page(_query(), cursor=None)

    assert page.items == [point]


def test_cached_archive_path_retains_active_batch_race_guard() -> None:
    point = _point("archive", 0)
    repository = _SwitchingLiveRepository((), ())
    paginator = TimelinePaginatorV1(
        repository,
        TimelineCursorCodecV1(),
        cached_archive_points=lambda active_batch_id: (point,),
    )

    with pytest.raises(TimelineCursorConflict):
        paginator.page(_query(), cursor=None)
    assert repository.active_batch_id_calls == 2


def test_cursor_conflicts_fail_closed_before_source_reads() -> None:
    points = [_point("live", index) for index in range(3)]
    repository = _Repository((), points, batch_id=None)
    codec = TimelineCursorCodecV1()
    paginator = TimelinePaginatorV1(repository, codec)
    first = paginator.page(_query(), cursor=None)
    repository.source_reads = 0

    with pytest.raises(TimelineCursorConflict):
        paginator.page(replace(_query(), sensor_id="s1"), cursor=first.next_cursor)
    assert repository.source_reads == 0

    missing = TimelineOrderKeyV1(
        event_at=datetime(2026, 8, 22, 12, 0, 0, 123_000, tzinfo=timezone.utc),
        sample_pair_id=str(uuid5(NAMESPACE_URL, "missing-pair")),
        sensor_id="s1",
        point_id=str(uuid5(NAMESPACE_URL, "missing-point")),
    )
    forged = codec.encode(
        active_batch_id=None,
        query_fingerprint=timeline_query_fingerprint_v1(_query()),
        last=missing,
    )
    with pytest.raises(TimelineCursorConflict):
        paginator.page(_query(), cursor=forged)
    assert repository.source_reads == 0


@pytest.mark.parametrize("source", ("live", "archive"))
def test_batch_activation_change_during_source_reads_is_a_cursor_conflict(
    source: str,
) -> None:
    point = _point(source, 0)
    if source == "archive":
        payload = point.model_dump_public()
        payload["provenance"]["batchId"] = _OTHER_BATCH
        point = TimelinePointV1.model_validate(payload)
    repository = _SwitchingRepository(
        (point,) if source == "archive" else (),
        (point,) if source == "live" else (),
    )
    paginator = TimelinePaginatorV1(repository, TimelineCursorCodecV1())

    with pytest.raises(TimelineCursorConflict):
        paginator.page(_query(), cursor=None)
