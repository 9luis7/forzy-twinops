"""Concurrent, sensor-isolated collection into the telemetry repository."""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import uuid

from twinops.ingestion.live_adapter import InvalidSensorPayload, adapt_live_payload
from twinops.ingestion.schedule import CollectionWindow
from twinops.ingestion.upstream import UpstreamClient, UpstreamFailure
from twinops.storage.repository import (
    CollectionAttempt,
    RawReading,
    TelemetryRepository,
)


class Collector:
    def __init__(
        self,
        upstream: UpstreamClient,
        repository: TelemetryRepository,
        asset_tag: str,
        window: CollectionWindow = CollectionWindow(),
        poll_interval_seconds: float = 5.0,
    ):
        self.upstream = upstream
        self.repository = repository
        self.asset_tag = asset_tag
        self.window = window
        self.poll_interval_seconds = poll_interval_seconds

    async def _one(self, sensor_id: str, slot: datetime) -> str:
        attempted = datetime.now(timezone.utc)
        try:
            fetched = await self.upstream.fetch(sensor_id)
            received = datetime.now(timezone.utc)
            raw_payload = dict(fetched.payload)
            encoded = json.dumps(
                raw_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.repository.append_raw(
                RawReading(
                    raw_id=str(uuid.uuid4()),
                    sensor_id=sensor_id,
                    scheduled_at=slot,
                    received_at=received,
                    payload_hash=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
                    payload=raw_payload,
                )
            )
            sample = adapt_live_payload(
                sensor_id=sensor_id,
                payload=fetched.payload,
                scheduled_at=slot,
                received_at=received,
                asset_tag=self.asset_tag,
            )
            stored = self.repository.insert_sample(sample)
            self.repository.record_attempt(
                CollectionAttempt(
                    sensor_id=sensor_id,
                    scheduled_at=slot,
                    attempted_at=attempted,
                    succeeded=True,
                    latency_ms=fetched.latency_ms,
                    error_code=None,
                )
            )
            return "stored" if stored else "duplicate"
        except (UpstreamFailure, InvalidSensorPayload) as exc:
            error_code = (
                exc.code if isinstance(exc, UpstreamFailure) else "invalid_payload"
            )
            latency = exc.latency_ms if isinstance(exc, UpstreamFailure) else None
            self.repository.record_attempt(
                CollectionAttempt(
                    sensor_id=sensor_id,
                    scheduled_at=slot,
                    attempted_at=attempted,
                    succeeded=False,
                    latency_ms=latency,
                    error_code=error_code,
                )
            )
            return "failed"

    async def collect_slot(self, slot: datetime) -> dict[str, str]:
        values = await asyncio.gather(
            self._one("s1", slot), self._one("s2", slot)
        )
        return dict(zip(("s1", "s2"), values, strict=True))

    async def tick(self, now: datetime) -> str:
        slot = self.window.slot_for(now, self.poll_interval_seconds)
        if slot is None:
            return "expected_idle"
        await self.collect_slot(slot)
        return "collected"

    async def run(self, *, stop, interval_seconds, clock, sleep) -> None:
        while not stop.is_set():
            await self.tick(clock())
            await sleep(interval_seconds)
