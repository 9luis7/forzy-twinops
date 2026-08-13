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


@pytest.mark.asyncio
async def test_loop_is_anchored_to_monotonic_deadlines_without_duration_drift():
    stop = asyncio.Event()
    monotonic_seconds = 0.0
    tick_starts = []
    sleep_delays = []
    work_durations = iter([2.0, 1.0, 6.0])

    class TimedCollector:
        run = Collector.run

        async def tick(self, now):
            nonlocal monotonic_seconds
            tick_starts.append(monotonic_seconds)
            monotonic_seconds += next(work_durations)

    async def sleep(delay):
        nonlocal monotonic_seconds
        sleep_delays.append(delay)
        monotonic_seconds += delay
        if len(sleep_delays) == 3:
            stop.set()

    base = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
    await TimedCollector().run(
        stop=stop,
        interval_seconds=5,
        clock=lambda: base,
        sleep=sleep,
        monotonic=lambda: monotonic_seconds,
    )

    assert tick_starts == [0.0, 5.0, 10.0]
    assert sleep_delays == [3.0, 4.0, 4.0]
