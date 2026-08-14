"""On-demand refresh orchestration for the real TwinOps sensors."""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Literal
import uuid

from twinops.ingestion.live_adapter_v2 import (
    InvalidSensorPayloadV2,
    adapt_live_payload_v2,
)
from twinops.ingestion.schedule import CollectionWindow
from twinops.ingestion.upstream import UpstreamClient, UpstreamFailure
from twinops.storage.v2_repository import (
    CollectionAttemptV2,
    RawReadingV2,
    SensorRefreshOutcomeV2,
    SensorRefreshWriteV2,
    TelemetryRepositoryV2,
)


RefreshOutcome = SensorRefreshOutcomeV2


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RefreshResult:
    refresh_attempted: bool
    outcomes: dict[str, RefreshOutcome]
    completed_at: datetime | None = None


class RefreshService:
    def __init__(
        self,
        upstream: UpstreamClient,
        repository: TelemetryRepositoryV2,
        *,
        asset_id: str = "forzy-motor-01",
        window: CollectionWindow = CollectionWindow(),
        poll_interval_seconds: float = 5.0,
        clock: Callable[[], datetime] = _utc_now,
        claim_ttl_seconds: float = 10.0,
        claim_poll_seconds: float = 0.02,
    ):
        if claim_ttl_seconds <= 0 or claim_poll_seconds <= 0:
            raise ValueError("refresh cycle timing must be positive")
        self.upstream = upstream
        self.repository = repository
        self.asset_id = asset_id
        self.window = window
        self.poll_interval_seconds = poll_interval_seconds
        self.clock = clock
        self.claim_ttl_seconds = claim_ttl_seconds
        self.claim_poll_seconds = claim_poll_seconds

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("refresh clock must return a timezone-aware instant")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _attempt(
        *,
        sensor_id: Literal["s1", "s2"],
        slot: datetime,
        attempted: datetime,
        succeeded: bool,
        latency_ms: int | None,
        error_code: str | None,
    ) -> CollectionAttemptV2:
        return CollectionAttemptV2(
            sensor_id=sensor_id,
            scheduled_at=slot,
            attempted_at=attempted,
            succeeded=succeeded,
            latency_ms=latency_ms,
            error_code=error_code,
        )

    def _persist_failed(
        self,
        *,
        sensor_id: Literal["s1", "s2"],
        slot: datetime,
        attempted: datetime,
        latency_ms: int | None,
        error_code: str,
        raw: RawReadingV2 | None = None,
    ) -> None:
        self.repository.persist_sensor_result(
            SensorRefreshWriteV2(
                raw=raw,
                sample=None,
                attempt=self._attempt(
                    sensor_id=sensor_id,
                    slot=slot,
                    attempted=attempted,
                    succeeded=False,
                    latency_ms=latency_ms,
                    error_code=error_code,
                ),
            )
        )

    async def _refresh_one(
        self, sensor_id: Literal["s1", "s2"], slot: datetime
    ) -> tuple[RefreshOutcome, datetime]:
        attempted = self._now()
        try:
            fetched = await self.upstream.fetch(sensor_id)
        except UpstreamFailure as exc:
            self._persist_failed(
                sensor_id=sensor_id,
                slot=slot,
                attempted=attempted,
                latency_ms=exc.latency_ms,
                error_code=exc.code,
            )
            return "failed", attempted

        received = self._now()
        if not isinstance(fetched.payload, Mapping):
            self._persist_failed(
                sensor_id=sensor_id,
                slot=slot,
                attempted=attempted,
                latency_ms=fetched.latency_ms,
                error_code="invalid_payload",
            )
            return "failed", received

        raw_payload = dict(fetched.payload)
        try:
            encoded = json.dumps(
                raw_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            self._persist_failed(
                sensor_id=sensor_id,
                slot=slot,
                attempted=attempted,
                latency_ms=fetched.latency_ms,
                error_code="invalid_payload",
            )
            return "failed", received

        payload_hash = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
        raw = RawReadingV2(
            raw_id=str(uuid.uuid4()),
            sensor_id=sensor_id,
            scheduled_at=slot,
            received_at=received,
            payload_hash=payload_hash,
            payload=raw_payload,
        )
        try:
            sample = adapt_live_payload_v2(
                sensor_id=sensor_id,
                payload=raw_payload,
                scheduled_at=slot,
                received_at=received,
                asset_id=self.asset_id,
            )
        except InvalidSensorPayloadV2:
            self._persist_failed(
                sensor_id=sensor_id,
                slot=slot,
                attempted=attempted,
                latency_ms=fetched.latency_ms,
                error_code="invalid_payload",
                raw=raw,
            )
            return "failed", received

        inserted = self.repository.persist_sensor_result(
            SensorRefreshWriteV2(
                raw=raw,
                sample=sample,
                attempt=self._attempt(
                    sensor_id=sensor_id,
                    slot=slot,
                    attempted=attempted,
                    succeeded=True,
                    latency_ms=fetched.latency_ms,
                    error_code=None,
                ),
            )
        )
        if inserted is None:
            raise RuntimeError("valid sensor result did not produce insert status")
        return ("stored" if inserted.stored else "unchanged"), received

    async def _run_owned_cycle(
        self,
        *,
        slot: datetime,
        owner_token: str,
    ) -> RefreshResult:
        values = await asyncio.gather(
            self._refresh_one("s1", slot),
            self._refresh_one("s2", slot),
            return_exceptions=False,
        )
        outcomes: dict[str, RefreshOutcome] = {
            sensor_id: value[0]
            for sensor_id, value in zip(("s1", "s2"), values, strict=True)
        }
        completed_at = max(self._now(), *(value[1] for value in values))
        cycle = self.repository.complete_refresh_cycle(
            asset_id=self.asset_id,
            scheduled_at=slot,
            owner_token=owner_token,
            completed_at=completed_at,
            outcomes=outcomes,
        )
        if cycle.completed_at is None or cycle.outcomes is None:
            raise RuntimeError("completed refresh cycle has no persisted result")
        return RefreshResult(
            refresh_attempted=True,
            outcomes=cycle.outcomes,
            completed_at=cycle.completed_at,
        )

    async def refresh(self, now: datetime) -> RefreshResult:
        slot = self.window.slot_for(now, self.poll_interval_seconds)
        if slot is None:
            return RefreshResult(
                refresh_attempted=False,
                outcomes={},
                completed_at=self._now(),
            )

        owner_token = str(uuid.uuid4())
        while True:
            claimed_at = self._now()
            claim = self.repository.claim_refresh_cycle(
                asset_id=self.asset_id,
                scheduled_at=slot,
                owner_token=owner_token,
                claimed_at=claimed_at,
                stale_before=claimed_at
                - timedelta(seconds=self.claim_ttl_seconds),
            )
            if claim.owned:
                return await self._run_owned_cycle(
                    slot=slot,
                    owner_token=owner_token,
                )
            if (
                claim.cycle.completed_at is not None
                and claim.cycle.outcomes is not None
            ):
                return RefreshResult(
                    refresh_attempted=True,
                    outcomes=claim.cycle.outcomes,
                    completed_at=claim.cycle.completed_at,
                )
            await asyncio.sleep(self.claim_poll_seconds)
