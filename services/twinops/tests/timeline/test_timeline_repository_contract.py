from importlib.util import find_spec
from datetime import datetime, timezone

import pytest


_TIMELINE_FOUNDATION_AVAILABLE = (
    find_spec("twinops.timeline") is not None
    and all(
        find_spec(module) is not None
        for module in (
            "twinops.timeline.repository_v1",
            "twinops.timeline.cursor_v1",
        )
    )
)


def test_timeline_reader_cursor_foundation_exists() -> None:
    assert (
        _TIMELINE_FOUNDATION_AVAILABLE
    ), "RED:VS1:timeline-reader-cursor-missing"


if _TIMELINE_FOUNDATION_AVAILABLE:
    from twinops.timeline.repository_v1 import (
        TimelineOrderKeyV1,
        TimelineReadQueryV1,
    )


    def test_timeline_read_query_and_order_key_enforce_the_frozen_contract() -> None:
        first = TimelineOrderKeyV1(
            event_at=datetime(2026, 8, 12, 15, tzinfo=timezone.utc),
            sample_pair_id="00000000-0000-5000-8000-000000000001",
            sensor_id="s1",
            point_id="00000000-0000-5000-8000-000000000002",
        )
        second = TimelineOrderKeyV1(
            event_at=first.event_at,
            sample_pair_id=first.sample_pair_id,
            sensor_id="s2",
            point_id="00000000-0000-5000-8000-000000000003",
        )
        query = TimelineReadQueryV1(
            asset_id="forzy-motor-01",
            from_at=first.event_at,
            to_at=datetime(2026, 8, 12, 16, tzinfo=timezone.utc),
            sensor_id=None,
            metric="temperature",
            after=first,
            limit=500,
        )

        assert first < second
        assert query.after is first

        invalid_values = (
            {"asset_id": "other"},
            {"from_at": datetime(2026, 8, 12, 15)},
            {"to_at": first.event_at},
            {"sensor_id": "s3"},
            {"metric": "rpm"},
            {"limit": 0},
            {"limit": 501},
        )
        base = {
            "asset_id": "forzy-motor-01",
            "from_at": first.event_at,
            "to_at": datetime(2026, 8, 12, 16, tzinfo=timezone.utc),
            "sensor_id": None,
            "metric": None,
            "after": None,
            "limit": 200,
        }
        for change in invalid_values:
            with pytest.raises(ValueError):
                TimelineReadQueryV1(**(base | change))
