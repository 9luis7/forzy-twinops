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


def test_live_reading_rejects_mismatched_observed_and_received_timestamps():
    body = payload("canonical-live-s1.valid.json")
    body["observedAt"] = "2026-08-12T15:00:00.000Z"

    with pytest.raises(ValidationError):
        CanonicalSensorReadingV2.model_validate(body)


def test_live_reading_rejects_wrong_timestamp_quality():
    body = payload("canonical-live-s1.valid.json")
    body["timestampQuality"] = "source"

    with pytest.raises(ValidationError):
        CanonicalSensorReadingV2.model_validate(body)


def test_live_reading_rejects_source_timestamp_claim():
    body = payload("canonical-live-s1.valid.json")
    body["provenance"]["sourceTimestampProvided"] = True

    with pytest.raises(ValidationError):
        CanonicalSensorReadingV2.model_validate(body)


@pytest.mark.parametrize(
    "timestamp",
    [
        "0000-01-01T00:00:00Z",
        "2000-02-29T12:34:56Z",
        "2024-12-31T23:59:60Z",
    ],
)
def test_accepts_normative_rfc3339_utc_boundaries(timestamp: str):
    body = payload("canonical-live-s1.valid.json")
    body["scheduledAt"] = timestamp

    model = CanonicalSensorReadingV2.model_validate(body)

    assert model.scheduled_at == timestamp


@pytest.mark.parametrize(
    "timestamp",
    [
        "2023-02-29T12:34:56Z",
        "2024-12-31T12:34:60Z",
        "2026-13-40T25:61:61Z",
    ],
)
def test_rejects_impossible_rfc3339_timestamp(timestamp: str):
    body = payload("canonical-live-s1.valid.json")
    body["scheduledAt"] = timestamp

    with pytest.raises(ValidationError):
        CanonicalSensorReadingV2.model_validate(body)


def test_frame_accepts_unavailable_only_with_null_timestamps():
    body = payload("snapshot-received-now.valid.json")["channels"][0]
    body["observedAt"] = None
    body["receivedAt"] = None
    body["timestampQuality"] = "unavailable"

    model = SensorTelemetryFrameV2.model_validate(body)

    assert model.observed_at is None
    assert model.received_at is None


@pytest.mark.parametrize(
    ("timestamp_quality", "observed_at", "received_at"),
    [
        (
            "assumed_from_retrieval",
            None,
            "2026-08-12T15:00:01.000Z",
        ),
        (
            "assumed_from_retrieval",
            "2026-08-12T15:00:00.000Z",
            "2026-08-12T15:00:01.000Z",
        ),
        (
            "unavailable",
            "2026-08-12T15:00:01.000Z",
            "2026-08-12T15:00:01.000Z",
        ),
    ],
    ids=["assumed-null", "assumed-mismatch", "unavailable-non-null"],
)
def test_frame_rejects_incoherent_temporal_state(
    timestamp_quality: str,
    observed_at: str | None,
    received_at: str | None,
):
    body = payload("snapshot-received-now.valid.json")["channels"][0]
    body["timestampQuality"] = timestamp_quality
    body["observedAt"] = observed_at
    body["receivedAt"] = received_at

    with pytest.raises(ValidationError):
        SensorTelemetryFrameV2.model_validate(body)


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
    assert model.to_public_dict() == body


def test_public_dump_preserves_omitted_and_explicit_null_evidence_fields():
    omitted = _assessment_payload(payload("snapshot-received-now.valid.json"))
    omitted["evidence"] = [
        {"id": "ev-1", "feature": "temperature", "value": 0, "unit": "degC"}
    ]

    omitted_model = AssetConditionAssessmentV2.model_validate(omitted)
    omitted_public = omitted_model.to_public_dict()

    assert omitted_public["evidence"][0] == omitted["evidence"][0]
    assert omitted_model.model_dump(mode="json", by_alias=True)["evidence"][0][
        "baseline"
    ] is None

    explicit_null = _assessment_payload(payload("snapshot-received-now.valid.json"))
    explicit_null["evidence"] = [
        {
            "id": "ev-1",
            "feature": "temperature",
            "value": 0,
            "unit": "degC",
            "baseline": None,
        }
    ]

    explicit_public = AssetConditionAssessmentV2.model_validate(
        explicit_null
    ).to_public_dict()

    assert "baseline" in explicit_public["evidence"][0]
    assert explicit_public["evidence"][0]["baseline"] is None


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
