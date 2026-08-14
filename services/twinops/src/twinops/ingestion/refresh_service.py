"""On-demand refresh orchestration for the real TwinOps sensors."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
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
    TelemetryRepositoryV2,
)


RefreshOutcome = Literal["stored", "unchanged", "failed"]


@dataclass(frozen=True)
class RefreshResult:
    refresh_attempted: bool
    outcomes: dict[str, RefreshOutcome]


class RefreshService:
    def __init__(
        self,
        upstream: UpstreamClient,
        repository: TelemetryRepositoryV2,
        *,
        asset_id: str = "forzy-motor-01",
        window: CollectionWindow = CollectionWindow(),
        poll_interval_seconds: float = 5.0,
    ):
        self.upstream = upstream
        self.repository = repository
        self.asset_id = asset_id
        self.window = window
        self.poll_interval_seconds = poll_interval_seconds

    def _record_attempt(
        self,
        *,
        sensor_id: Literal["s1", "s2"],
        slot: datetime,
        attempted: datetime,
        succeeded: bool,
        latency_ms: int | None,
        error_code: str | None,
    ) -> None:
        self.repository.record_attempt(
            CollectionAttemptV2(
                sensor_id=sensor_id,
                scheduled_at=slot,
                attempted_at=attempted,
                succeeded=succeeded,
                latency_ms=latency_ms,
                error_code=error_code,
            )
        )

    async def _refresh_one(
        self, sensor_id: Literal["s1", "s2"], slot: datetime
    ) -> RefreshOutcome:
        attempted = datetime.now(timezone.utc)
        try:
            fetched = await self.upstream.fetch(sensor_id)
        except UpstreamFailure as exc:
            self._record_attempt(
                sensor_id=sensor_id,
                slot=slot,
                attempted=attempted,
                succeeded=False,
                latency_ms=exc.latency_ms,
                error_code=exc.code,
            )
            return "failed"
        received = datetime.now(timezone.utc)
        if not isinstance(fetched.payload, Mapping):
            self._record_attempt(
                sensor_id=sensor_id,
                slot=slot,
                attempted=attempted,
                succeeded=False,
                latency_ms=None,
                error_code="invalid_payload",
            )
            return "failed"
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
            self._record_attempt(
                sensor_id=sensor_id,
                slot=slot,
                attempted=attempted,
                succeeded=False,
                latency_ms=None,
                error_code="invalid_payload",
            )
            return "failed"
        payload_hash = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
        self.repository.append_raw(
            RawReadingV2(
                raw_id=str(uuid.uuid4()),
                sensor_id=sensor_id,
                scheduled_at=slot,
                received_at=received,
                payload_hash=payload_hash,
                payload=raw_payload,
            )
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
            self._record_attempt(
                sensor_id=sensor_id,
                slot=slot,
                attempted=attempted,
                succeeded=False,
                latency_ms=None,
                error_code="invalid_payload",
            )
            return "failed"
        inserted = self.repository.insert_distinct_sample(sample)
        self._record_attempt(
            sensor_id=sensor_id,
            slot=slot,
            attempted=attempted,
            succeeded=True,
            latency_ms=fetched.latency_ms,
            error_code=None,
        )
        return "stored" if inserted.stored else "unchanged"

    async def refresh(self, now: datetime) -> RefreshResult:
        slot = self.window.slot_for(now, self.poll_interval_seconds)
        if slot is None:
            return RefreshResult(refresh_attempted=False, outcomes={})
        values = await asyncio.gather(
            self._refresh_one("s1", slot),
            self._refresh_one("s2", slot),
            return_exceptions=False,
        )
        return RefreshResult(
            refresh_attempted=True,
            outcomes=dict(zip(("s1", "s2"), values, strict=True)),
        )
