import os
from datetime import datetime, timezone

import httpx
import pytest

from twinops.config import Settings
from twinops.ingestion.live_adapter import adapt_live_payload
from twinops.ingestion.upstream import UpstreamClient


pytestmark = pytest.mark.skipif(
    os.getenv("TWINOPS_RUN_LIVE_SMOKE") != "1",
    reason="live smoke requires explicit opt-in",
)


@pytest.mark.asyncio
async def test_live_endpoints_match_contract():
    settings = Settings.from_env(os.environ)
    async with httpx.AsyncClient() as http:
        client = UpstreamClient(
            http,
            settings.upstream_base_url,
            settings.request_timeout_seconds,
        )
        for sensor_id in ("s1", "s2"):
            result = await client.fetch(sensor_id)
            assert result.latency_ms >= 0
            adapt_live_payload(
                sensor_id=sensor_id,
                payload=result.payload,
                scheduled_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                asset_tag=settings.asset_tag,
            )
