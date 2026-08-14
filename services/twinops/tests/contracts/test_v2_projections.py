import json
from pathlib import Path

import pytest

from twinops.contracts.v2_models import CanonicalSensorReadingV2
from twinops.contracts.v2_projections import to_sensor_telemetry_frame_v2


FIXTURES = Path("contracts/v2/fixtures")


@pytest.fixture
def valid_live_reading_v2() -> CanonicalSensorReadingV2:
    body = json.loads(
        (FIXTURES / "canonical-live-s1.valid.json").read_text(encoding="utf-8")
    )
    return CanonicalSensorReadingV2.model_validate(body)


def test_projection_removes_audit_fields(valid_live_reading_v2):
    frame = to_sensor_telemetry_frame_v2(valid_live_reading_v2)

    body = frame.model_dump(mode="json", by_alias=True)

    assert body["observedAt"] == body["receivedAt"]
    assert body["timestampQuality"] == "assumed_from_retrieval"
    assert body["measurements"]["vibrationAcceleration"]["value"] == 0
    assert set(body) == {
        "schemaVersion",
        "frameId",
        "assetId",
        "sensorId",
        "observedAt",
        "receivedAt",
        "timestampQuality",
        "measurements",
        "qualityFlags",
    }
    assert "raw" not in body and "payloadHash" not in body and "provenance" not in body
