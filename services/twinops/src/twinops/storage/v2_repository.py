"""Version 2 persistence boundary for real TwinOps telemetry."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

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
    attempt_id: str = field(default_factory=lambda: str(uuid.uuid4()))


SensorRefreshOutcomeV2 = Literal["stored", "unchanged", "failed"]


@dataclass(frozen=True)
class SensorRefreshWriteV2:
    raw: RawReadingV2 | None
    sample: CanonicalSensorReadingV2 | None
    attempt: CollectionAttemptV2


@dataclass(frozen=True)
class RefreshCycleV2:
    asset_id: str
    scheduled_at: datetime
    owner_token: str
    claimed_at: datetime
    completed_at: datetime | None
    outcomes: dict[str, SensorRefreshOutcomeV2] | None


@dataclass(frozen=True)
class RefreshCycleClaimV2:
    owned: bool
    cycle: RefreshCycleV2


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

    def persist_sensor_result(
        self, write: SensorRefreshWriteV2
    ) -> InsertResult | None: ...

    def claim_refresh_cycle(
        self,
        *,
        asset_id: str,
        scheduled_at: datetime,
        owner_token: str,
        claimed_at: datetime,
        stale_before: datetime,
    ) -> RefreshCycleClaimV2: ...

    def get_refresh_cycle(
        self, asset_id: str, scheduled_at: datetime
    ) -> RefreshCycleV2 | None: ...

    def complete_refresh_cycle(
        self,
        *,
        asset_id: str,
        scheduled_at: datetime,
        owner_token: str,
        completed_at: datetime,
        outcomes: dict[str, SensorRefreshOutcomeV2],
    ) -> RefreshCycleV2: ...

    def latest(self, asset_id: str) -> list[CanonicalSensorReadingV2]: ...

    def history(self, query: HistoryQueryV2) -> list[CanonicalSensorReadingV2]: ...

    def health(self, sensor_id: str) -> RepositorySensorHealthV2 | None: ...
