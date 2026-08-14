"""Version 2 persistence boundary for real TwinOps telemetry."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from twinops.contracts.v2_models import CanonicalSensorReadingV2


@dataclass(frozen=True)
class InsertResult:
    stored: bool
    duplicate_of: str | None


@dataclass(frozen=True)
class HistoryQueryV2:
    asset_id: str
    sensor_id: str | None = None
    from_at: datetime | None = None
    to_at: datetime | None = None
    limit: int = 200


@dataclass(frozen=True)
class RawReadingV2:
    raw_id: str
    sensor_id: str
    scheduled_at: datetime
    received_at: datetime
    payload_hash: str
    payload: dict[str, object]


@dataclass(frozen=True)
class CollectionAttemptV2:
    sensor_id: str
    scheduled_at: datetime
    attempted_at: datetime
    succeeded: bool
    latency_ms: int | None
    error_code: str | None


@dataclass(frozen=True)
class RepositorySensorHealthV2:
    sensor_id: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    latency_ms: int | None
    error_code: str | None
    sample_count: int


class TelemetryRepositoryV2(Protocol):
    def initialize(self) -> None: ...

    def append_raw(self, reading: RawReadingV2) -> None: ...

    def insert_distinct_sample(
        self, sample: CanonicalSensorReadingV2
    ) -> InsertResult: ...

    def record_attempt(self, attempt: CollectionAttemptV2) -> None: ...

    def latest(self, asset_id: str) -> list[CanonicalSensorReadingV2]: ...

    def history(self, query: HistoryQueryV2) -> list[CanonicalSensorReadingV2]: ...

    def health(self, sensor_id: str) -> RepositorySensorHealthV2 | None: ...
