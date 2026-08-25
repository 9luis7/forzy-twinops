from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from twinops.contracts.timeline_v1_models import (
    TimelineRangeOverflow,
    parse_public_utc_millis_v1,
    serialize_public_utc_millis_v1,
)
from twinops.timeline import ranges_v1

from overview_fixtures_v1 import make_point


_SUCCESSOR_CASES = (
    Path(__file__).resolve().parents[4]
    / "contracts/timeline/v1/fixtures/public-millisecond-successor-v1-cases.json"
)


def test_range_resolution_preserves_requested_bounds_and_global_availability() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    points = (
        make_point(0, event_at=start),
        make_point(1, event_at=start + timedelta(seconds=10)),
    )

    full = ranges_v1.resolve_timeline_ranges_v1(points, from_at=None, to_at=None)
    assert full.requested_from is None
    assert full.requested_to is None
    assert full.available_from == start
    assert full.available_to == start + timedelta(seconds=10, milliseconds=1)
    assert full.effective_from == full.available_from
    assert full.effective_to == full.available_to

    explicit_from = start - timedelta(minutes=1)
    explicit_to = start + timedelta(minutes=1)
    bounded = ranges_v1.resolve_timeline_ranges_v1(
        points,
        from_at=explicit_from,
        to_at=explicit_to,
    )
    assert bounded.effective_from == explicit_from
    assert bounded.effective_to == explicit_to
    assert bounded.available_from == full.available_from
    assert bounded.available_to == full.available_to


def test_empty_and_narrow_ranges_do_not_invent_effective_coverage() -> None:
    start = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    points = (make_point(0, event_at=start),)

    empty = ranges_v1.resolve_timeline_ranges_v1((), from_at=None, to_at=None)
    assert empty.available_from is None
    assert empty.available_to is None
    assert empty.effective_from is None
    assert empty.effective_to is None

    narrow = ranges_v1.resolve_timeline_ranges_v1(
        points,
        from_at=start + timedelta(milliseconds=1),
        to_at=start + timedelta(milliseconds=2),
    )
    assert narrow.available_from == start
    assert narrow.available_to == start + timedelta(milliseconds=1)
    assert narrow.effective_from is None
    assert narrow.effective_to is None


@pytest.mark.parametrize(
    "change",
    (
        {"from_at": datetime(2026, 8, 22, 12)},
        {"to_at": datetime(2026, 8, 22, 12)},
        {
            "from_at": datetime(
                2026, 8, 22, 12, 0, 0, 1, tzinfo=timezone.utc
            )
        },
        {
            "from_at": datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
            "to_at": datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
        },
        {
            "from_at": datetime(2026, 8, 22, 12, 0, 0, 1_000, tzinfo=timezone.utc),
            "to_at": datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
        },
    ),
)
def test_range_resolution_rejects_noncanonical_or_nonincreasing_bounds(change) -> None:
    with pytest.raises(ValueError):
        ranges_v1.resolve_timeline_ranges_v1(
            (), **({"from_at": None, "to_at": None} | change)
        )


def test_range_module_uses_the_frozen_public_millisecond_successor_table() -> None:
    cases = json.loads(_SUCCESSOR_CASES.read_text(encoding="utf-8"))
    observed: dict[str, str] = {}
    for case in cases["valid"]:
        value = parse_public_utc_millis_v1(case["input"])
        observed[case["caseId"]] = serialize_public_utc_millis_v1(
            ranges_v1.public_millisecond_successor_v1(value)
        )
    assert observed == {
        case["caseId"]: case["expected"] for case in cases["valid"]
    }

    with pytest.raises(ValueError, match="timeline_invalid_public_millisecond"):
        parse_public_utc_millis_v1(cases["invalid"][0]["input"])
    terminal = parse_public_utc_millis_v1(cases["invalid"][1]["input"])
    with pytest.raises(TimelineRangeOverflow, match="timeline_range_overflow"):
        ranges_v1.public_millisecond_successor_v1(terminal)
