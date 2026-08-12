from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from twinops.ingestion.schedule import CollectionWindow


SP = ZoneInfo("America/Sao_Paulo")


def test_schedule_boundaries():
    window = CollectionWindow()
    assert not window.is_open(datetime(2026, 8, 10, 11, 59, tzinfo=SP))
    assert window.is_open(datetime(2026, 8, 10, 12, 0, tzinfo=SP))
    assert window.is_open(datetime(2026, 8, 12, 13, 59, 59, tzinfo=SP))
    assert not window.is_open(datetime(2026, 8, 12, 14, 0, tzinfo=SP))
    assert not window.is_open(datetime(2026, 8, 13, 12, 0, tzinfo=SP))


def test_slot_is_utc_and_floor_aligned():
    slot = CollectionWindow().slot_for(
        datetime(2026, 8, 12, 12, 0, 7, tzinfo=SP), 5
    )
    assert slot.isoformat() == "2026-08-12T15:00:05+00:00"


def test_schedule_rejects_naive_clock_and_non_positive_interval():
    window = CollectionWindow()
    with pytest.raises(ValueError, match="timezone-aware"):
        window.is_open(datetime(2026, 8, 12, 12, 0))
    with pytest.raises(ValueError, match="positive"):
        window.slot_for(datetime(2026, 8, 12, 12, 0, tzinfo=SP), 0)
