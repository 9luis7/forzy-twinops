from datetime import datetime, timezone
from decimal import Decimal
from importlib.util import find_spec

import pytest

from conftest import prepared_batch
from twinops.timeline import repository_v1 as timeline_repository_v1


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


    def test_direct_historical_projector_matches_deep_public_projection() -> None:
        reading = prepared_batch(1).samples[0].reading
        canonical = reading.model_dump_public()
        canonical_before = dict(canonical)
        projector = getattr(
            timeline_repository_v1,
            "historical_timeline_point_from_canonical_v1",
            None,
        )

        assert callable(projector), "RED:VS5C:direct-historical-projector-missing"
        direct = projector(canonical)
        deep = timeline_repository_v1.historical_timeline_point_v1(reading)

        assert direct == deep
        assert direct.model_dump_public_json() == deep.model_dump_public_json()
        assert canonical == canonical_before


    @pytest.mark.parametrize(
        ("case", "source_timestamp_text"),
        (
            ("missing", None),
            ("empty", ""),
            ("non-string", 7),
        ),
    )
    def test_direct_historical_projector_rejects_invalid_source_timestamp_text(
        case: str,
        source_timestamp_text: object,
    ) -> None:
        canonical = prepared_batch(1).samples[0].reading.model_dump_public()
        if case == "missing":
            canonical.pop("sourceTimestampText")
        else:
            canonical["sourceTimestampText"] = source_timestamp_text

        with pytest.raises(ValueError, match="sourceTimestampText"):
            timeline_repository_v1.historical_timeline_point_from_canonical_v1(
                canonical
            )


    def test_direct_historical_projector_rejects_live_canonical_shape() -> None:
        canonical = prepared_batch(1).samples[0].reading.model_dump_public()
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

        with pytest.raises(ValueError, match="historical_archive"):
            timeline_repository_v1.historical_timeline_point_from_canonical_v1(
                canonical
            )
