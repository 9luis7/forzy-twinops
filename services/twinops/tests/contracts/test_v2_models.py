import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from twinops.contracts.v2_models import (
    AssetConditionAssessmentV2,
    CanonicalSensorReadingV2,
    DigitalTwinSnapshotV2,
    SensorTelemetryFrameV2,
)


FIXTURES = Path("contracts/v2/fixtures")


def payload(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_live_round_trip_preserves_assumed_retrieval_time():
    body = payload("canonical-live-s1.valid.json")

    model = CanonicalSensorReadingV2.model_validate(body)

    assert model.observed_at == model.received_at
    assert model.model_dump(mode="json", by_alias=True) == body


def test_source_timestamp_claim_is_rejected():
    with pytest.raises(ValidationError):
        CanonicalSensorReadingV2.model_validate(
            payload("canonical-source-time.invalid.json")
        )


def test_rejects_impossible_rfc3339_timestamp():
    body = payload("canonical-live-s1.valid.json")
    body["scheduledAt"] = "2026-13-40T25:61:61Z"

    with pytest.raises(ValidationError):
        CanonicalSensorReadingV2.model_validate(body)


@pytest.mark.parametrize(
    "fixture_name",
    ["snapshot-received-now.valid.json", "snapshot-last-known.valid.json"],
)
def test_snapshot_fixture_round_trips(fixture_name: str):
    body = payload(fixture_name)

    model = DigitalTwinSnapshotV2.model_validate(body)

    assert model.model_dump(mode="json", by_alias=True) == body


def test_snapshot_rejects_asset_tag():
    with pytest.raises(ValidationError):
        DigitalTwinSnapshotV2.model_validate(payload("snapshot-asset-tag.invalid.json"))


def test_snapshot_requires_assessment_key():
    body = payload("snapshot-received-now.valid.json")
    del body["assessment"]

    with pytest.raises(ValidationError):
        DigitalTwinSnapshotV2.model_validate(body)


def test_snapshot_rejects_duplicate_live_sensor_channel():
    body = payload("snapshot-received-now.valid.json")
    body["channels"][1]["sensorId"] = "s1"

    with pytest.raises(ValidationError):
        DigitalTwinSnapshotV2.model_validate(body)


@pytest.mark.parametrize("invalid_number", ["0", float("nan"), float("inf"), float("-inf")])
def test_measurement_values_are_strict_finite_numbers_and_zero_is_valid(invalid_number):
    valid = payload("canonical-live-s1.valid.json")
    assert (
        CanonicalSensorReadingV2.model_validate(valid)
        .measurements.vibration_acceleration.value
        == 0
    )

    valid["measurements"]["vibrationAcceleration"]["value"] = invalid_number
    with pytest.raises(ValidationError):
        CanonicalSensorReadingV2.model_validate(valid)


def test_valid_assessment_object_round_trips_in_snapshot():
    body = payload("snapshot-received-now.valid.json")
    assessment = _assessment_payload(body)
    body["assessment"] = assessment

    model = DigitalTwinSnapshotV2.model_validate(body)

    assert isinstance(model.assessment, AssetConditionAssessmentV2)
    assert model.model_dump(mode="json", by_alias=True) == body


def test_sensor_frame_rejects_numeric_string_for_health_counter():
    body = payload("snapshot-received-now.valid.json")
    body["integration"]["sensors"]["s1"]["sampleCount"] = "1"

    with pytest.raises(ValidationError):
        DigitalTwinSnapshotV2.model_validate(body)


def _assessment_payload(snapshot: dict) -> dict:
    timestamp = snapshot["generatedAt"]
    return {
        "schemaVersion": "2.0",
        "assessmentId": "00000000-0000-4000-8000-000000000003",
        "assetId": "forzy-motor-01",
        "sensorId": "s1",
        "window": {
            "start": timestamp,
            "end": timestamp,
            "receivedAt": timestamp,
            "freshnessMs": 0,
        },
        "quality": {"status": "ok", "flags": []},
        "operatingContext": {"state": "steady", "estimated": True},
        "assessment": {
            "status": "normal",
            "anomalyScore": 0,
            "deteriorationScore": 0,
            "scoreSemantics": "relative_to_historical_baseline_not_failure_probability",
            "episodeId": None,
            "persistenceSeconds": 0,
        },
        "componentTag": None,
        "recommendation": None,
        "humanValidationRequired": True,
        "evidence": [],
        "model": {
            "name": "robust-baseline",
            "version": "1.0.0",
            "configHash": f"sha256:{'0' * 64}",
            "trainedUntil": timestamp,
        },
        "limitations": [],
    }
