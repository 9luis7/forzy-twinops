from datetime import datetime, timezone
from decimal import Decimal
from importlib.util import find_spec

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


    def _query_with_limit(limit: object) -> TimelineReadQueryV1:
        return TimelineReadQueryV1(
            asset_id="forzy-motor-01",
            from_at=None,
            to_at=None,
            sensor_id=None,
            metric=None,
            limit=limit,
        )


    @pytest.mark.parametrize("limit", (1, 500))
    def test_timeline_read_query_accepts_strict_integer_limit_boundaries(
        limit: int,
    ) -> None:
        query = _query_with_limit(limit)

        assert type(query.limit) is int
        assert query.limit == limit


    @pytest.mark.parametrize(
        "limit",
        (
            pytest.param(0, id="zero"),
            pytest.param(501, id="above-maximum"),
            pytest.param(-1, id="negative"),
            pytest.param(True, id="true"),
            pytest.param(False, id="false"),
            pytest.param(1.0, id="integral-float"),
            pytest.param(1.5, id="fractional-float"),
            pytest.param(Decimal("2"), id="decimal"),
            pytest.param("200", id="string"),
            pytest.param(None, id="none"),
            pytest.param([], id="list"),
            pytest.param(object(), id="object"),
        ),
    )
    def test_timeline_read_query_rejects_non_integer_or_out_of_range_limit(
        limit: object,
    ) -> None:
        with pytest.raises(ValueError):
            _query_with_limit(limit)


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
