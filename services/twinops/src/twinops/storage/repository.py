"""Storage boundary for canonical telemetry."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from twinops.contracts.models import CanonicalSensorReading


@dataclass(frozen=True)
class HistoryQuery:
    asset_tag: str
    sensor_id: str | None = None
    source: str | None = None
    from_at: datetime | None = None
    to_at: datetime | None = None
    limit: int = 200


@dataclass(frozen=True)
class CollectionAttempt:
    sensor_id: str
    scheduled_at: datetime
    attempted_at: datetime
    succeeded: bool
    latency_ms: int | None
    error_code: str | None


@dataclass(frozen=True)
class RawReading:
    raw_id: str
    sensor_id: str
    scheduled_at: datetime
    received_at: datetime
    payload_hash: str
    payload: dict[str, object]


@dataclass(frozen=True)
class SensorHealth:
    sensor_id: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    latency_ms: int | None
    error_code: str | None
    sample_count: int


class TelemetryRepository(Protocol):
    def initialize(self) -> None: ...

    def append_raw(self, reading: RawReading) -> None: ...

    def insert_sample(self, sample: CanonicalSensorReading) -> bool: ...

    def record_attempt(self, attempt: CollectionAttempt) -> None: ...

    def history(self, query: HistoryQuery) -> list[CanonicalSensorReading]: ...

    def latest(self, asset_tag: str) -> list[CanonicalSensorReading]: ...

    def health(self, sensor_id: str) -> SensorHealth | None: ...
