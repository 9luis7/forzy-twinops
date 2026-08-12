import asyncio
from datetime import datetime, timezone

import pytest

from twinops.ingestion.collector import Collector


class RecordingCollector:
    def __init__(self):
        self.requested_slots = []

    async def tick(self, now):
        seconds = int(now.timestamp() // 5 * 5)
        self.requested_slots.append(
            datetime.fromtimestamp(seconds, tz=timezone.utc)
        )

    run = Collector.run


@pytest.mark.asyncio
async def test_loop_collects_current_slot_only_and_stops():
    clean_collector = RecordingCollector()
    stop = asyncio.Event()
    ticks = iter(
        [
            datetime(2026, 8, 12, 15, 0, 7, tzinfo=timezone.utc),
            datetime(2026, 8, 12, 15, 0, 12, tzinfo=timezone.utc),
        ]
    )
    sleeps = 0

    async def sleep(_):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            stop.set()

    await clean_collector.run(
        stop=stop,
        interval_seconds=5,
        clock=lambda: next(ticks),
        sleep=sleep,
    )

    assert clean_collector.requested_slots == [
        datetime(2026, 8, 12, 15, 0, 5, tzinfo=timezone.utc),
        datetime(2026, 8, 12, 15, 0, 10, tzinfo=timezone.utc),
    ]
