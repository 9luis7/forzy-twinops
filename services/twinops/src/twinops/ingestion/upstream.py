"""Sanitized async client for the two Forzy sensor endpoints."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
import random
import time
from typing import Literal

import httpx


@dataclass(frozen=True)
class FetchResult:
    payload: Mapping[str, object]
    latency_ms: int


class UpstreamFailure(RuntimeError):
    def __init__(self, code: str, latency_ms: int | None = None):
        super().__init__(code)
        self.code = code
        self.latency_ms = latency_ms


class UpstreamClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        timeout_seconds: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self.sleep = sleep

    async def fetch(self, sensor_id: Literal["s1", "s2"]) -> FetchResult:
        last: UpstreamFailure | None = None
        for attempt in range(2):
            started = time.perf_counter()
            try:
                response = await self.http.get(
                    f"{self.base_url}/get_{sensor_id}",
                    headers={"accept": "application/json"},
                    timeout=self.timeout,
                )
                latency = round((time.perf_counter() - started) * 1000)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, Mapping):
                    raise ValueError("payload root must be an object")
                return FetchResult(payload=payload, latency_ms=latency)
            except (httpx.TimeoutException, httpx.HTTPError, ValueError):
                latency = round((time.perf_counter() - started) * 1000)
                last = UpstreamFailure("upstream_unavailable", latency)
                if attempt == 0:
                    await self.sleep(0.1 + random.random() * 0.1)
        raise last or UpstreamFailure("upstream_unavailable")
