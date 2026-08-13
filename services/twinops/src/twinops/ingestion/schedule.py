"""Deterministic acquisition windows and UTC polling slots."""

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class CollectionWindow:
    timezone_name: str = "America/Sao_Paulo"
    weekdays: frozenset[int] = frozenset({0, 1, 2})
    start: time = time(12, 0)
    end: time = time(14, 0)

    def is_open(self, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        local = now.astimezone(ZoneInfo(self.timezone_name))
        return (
            local.weekday() in self.weekdays
            and self.start <= local.time() < self.end
        )

    def slot_for(
        self, now: datetime, interval_seconds: float
    ) -> datetime | None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if not self.is_open(now):
            return None
        utc = now.astimezone(timezone.utc)
        floored = int(utc.timestamp() // interval_seconds * interval_seconds)
        return datetime.fromtimestamp(floored, tz=timezone.utc)
