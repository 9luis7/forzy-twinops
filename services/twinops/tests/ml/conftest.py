from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from twinops.contracts.models import CanonicalSensorReading


@pytest.fixture
def sample_factory():
    base = datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)

    def make(
        *,
        second: int,
        velocity: float = 0.01,
        temperature: float = 30.0,
        acceleration: float = 0.0,
        payload_hash: str | None = None,
        sensor_id: str = "s1",
        quality_flags: list[str] | None = None,
    ) -> CanonicalSensorReading:
        instant = base + timedelta(seconds=second)
        timestamp = instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        digest = payload_hash or sha256(
            f"{sensor_id}:{second}:{velocity}:{temperature}:{acceleration}".encode()
        ).hexdigest()
        if not digest.startswith("sha256:"):
            digest = f"sha256:{sha256(digest.encode()).hexdigest()}"
        return CanonicalSensorReading.model_validate(
            {
                "schemaVersion": "1.0",
                "readingId": f"00000000-0000-4000-8000-{second:012d}",
                "source": "forzy-csv",
                "assetTag": "MTR-BMB-042",
                "sensorId": sensor_id,
                "scheduledAt": None,
                "observedAt": timestamp,
                "receivedAt": timestamp,
                "measurements": {
                    "vibrationVelocityRms": {
                        "value": velocity,
                        "unit": "mm/s",
                        "semanticConfidence": "inferred_from_datasheet",
                    },
                    "vibrationAcceleration": {
                        "value": acceleration,
                        "unit": "g",
                        "statistic": "unknown",
                        "semanticConfidence": "unconfirmed",
                    },
                    "temperature": {
                        "value": temperature,
                        "unit": "degC",
                        "semanticConfidence": "inferred_from_datasheet",
                    },
                },
                "qualityFlags": quality_flags or [],
                "payloadHash": digest,
                "raw": {},
                "provenance": {"sourceSystem": "test-import", "ingestedAt": timestamp},
            }
        )

    return make

