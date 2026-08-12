import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from twinops.contracts.models import (
    AssetConditionAssessment,
    CanonicalSensorReading,
    DigitalTwinSnapshot,
    SensorTelemetryFrame,
)
from twinops.contracts.projections import to_sensor_telemetry_frame


FIXTURES = Path("contracts/v1/fixtures")


@pytest.mark.parametrize(
    ("fixture_name", "model_type"),
    [
        ("canonical-sensor-reading-live-s1.valid.json", CanonicalSensorReading),
        ("canonical-sensor-reading-csv-s1.valid.json", CanonicalSensorReading),
        ("asset-condition-assessment-evidence.valid.json", AssetConditionAssessment),
        ("digital-twin-snapshot-live.valid.json", DigitalTwinSnapshot),
        ("digital-twin-snapshot-replay.valid.json", DigitalTwinSnapshot),
    ],
)
def test_valid_fixture_round_trips_with_schema_aliases(fixture_name, model_type):
    payload = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))

    model = model_type.model_validate(payload)

    assert model.model_dump(mode="json", by_alias=True) == payload


def test_numeric_string_is_rejected():
    payload = json.loads(
        (FIXTURES / "canonical-sensor-reading-string.invalid.json").read_text(encoding="utf-8")
    )

    with pytest.raises(ValidationError):
        CanonicalSensorReading.model_validate(payload)


def test_canonical_live_timestamp_and_provenance_contract():
    payload = json.loads(
        (FIXTURES / "canonical-sensor-reading-live-s1.valid.json").read_text(encoding="utf-8")
    )
    assert payload["scheduledAt"] == "2026-08-12T15:00:00.000Z"
    assert payload["observedAt"] is None
    assert payload["provenance"] == {
        "sourceSystem": "forzy-api",
        "ingestedAt": payload["receivedAt"],
    }
    assert CanonicalSensorReading.model_validate(payload)
    for mutation in (
        lambda body: body.update(observedAt=body["scheduledAt"]),
        lambda body: body["provenance"].update(sourceSystem="forzy-live"),
        lambda body: body["provenance"].update(ingestedAt="2026-08-12T15:00:02.000Z"),
    ):
        invalid = json.loads(json.dumps(payload))
        mutation(invalid)
        with pytest.raises(ValidationError):
            CanonicalSensorReading.model_validate(invalid)


def test_projection_removes_audit_fields_and_preserves_consumer_data():
    payload = json.loads(
        (FIXTURES / "canonical-sensor-reading-live-s1.valid.json").read_text(encoding="utf-8")
    )
    reading = CanonicalSensorReading.model_validate(payload)

    frame = to_sensor_telemetry_frame(reading)
    dumped = frame.model_dump(mode="json", by_alias=True)

    assert frame.frame_id == reading.reading_id
    assert dumped["sourceMode"] == "live"
    assert dumped["timestampQuality"] == "collector"
    assert dumped["measurements"] == payload["measurements"]
    assert dumped["qualityFlags"] == payload["qualityFlags"]
    assert not {"raw", "payloadHash", "provenance", "scheduledAt"} & dumped.keys()


def test_projection_uses_source_timestamp_for_csv_reading():
    payload = json.loads(
        (FIXTURES / "canonical-sensor-reading-live-s1.valid.json").read_text(encoding="utf-8")
    )
    payload.update(source="forzy-csv", scheduledAt=None, observedAt="2026-08-12T14:59:59.000Z")
    payload["provenance"]["sourceSystem"] = "forzy-csv-import"

    frame = to_sensor_telemetry_frame(CanonicalSensorReading.model_validate(payload))

    assert frame.source_mode == "historical"
    assert frame.timestamp_quality == "source"


def test_sensor_frame_accepts_legacy_acceleration_in_metres_per_second_squared():
    payload = json.loads(
        (FIXTURES / "digital-twin-snapshot-live.valid.json").read_text(encoding="utf-8")
    )["channels"][0]
    payload["measurements"]["vibrationAcceleration"] = {
        "value": 2.1,
        "unit": "m/s²",
        "statistic": "unknown",
        "semanticConfidence": "unconfirmed",
    }

    assert SensorTelemetryFrame.model_validate(payload).measurements.vibration_acceleration.value == 2.1


def test_assessment_evidence_is_closed_typed_and_round_trips():
    payload = _assessment_payload()
    payload["evidence"] = [{
        "id": "ev-1",
        "feature": "velocity_rms_ewma",
        "value": 0.08,
        "unit": "mm/s",
        "baseline": 0.04,
        "deviation": 0.04,
        "direction": "up",
        "windowSeconds": 300,
    }]

    model = AssetConditionAssessment.model_validate(payload)

    assert model.model_dump(mode="json", by_alias=True) == payload
    for mutation in (
        lambda item: item.update(extra=True),
        lambda item: item.update(feature=""),
        lambda item: item.update(direction="sideways"),
        lambda item: item.update(windowSeconds=-1),
    ):
        invalid = json.loads(json.dumps(payload))
        mutation(invalid["evidence"][0])
        with pytest.raises(ValidationError):
            AssetConditionAssessment.model_validate(invalid)


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_all_numeric_contract_families_reject_non_finite_values(non_finite):
    canonical = json.loads(
        (FIXTURES / "canonical-sensor-reading-live-s1.valid.json").read_text(encoding="utf-8")
    )
    canonical["measurements"]["temperature"]["value"] = non_finite
    with pytest.raises(ValidationError):
        CanonicalSensorReading.model_validate(canonical)

    frame = json.loads(
        (FIXTURES / "digital-twin-snapshot-live.valid.json").read_text(encoding="utf-8")
    )["channels"][0]
    frame["measurements"]["vibrationVelocityRms"]["value"] = non_finite
    with pytest.raises(ValidationError):
        SensorTelemetryFrame.model_validate(frame)

    assessment = _assessment_payload()
    for path in (
        ("window", "freshnessMs"),
        ("assessment", "anomalyScore"),
        ("assessment", "deteriorationScore"),
        ("assessment", "persistenceSeconds"),
    ):
        invalid = json.loads(json.dumps(assessment))
        invalid[path[0]][path[1]] = non_finite
        with pytest.raises(ValidationError):
            AssetConditionAssessment.model_validate(invalid)

    evidence_assessment = json.loads(
        (FIXTURES / "asset-condition-assessment-evidence.valid.json").read_text(encoding="utf-8")
    )
    for numeric in ("value", "baseline", "deviation", "windowSeconds"):
        invalid = json.loads(json.dumps(evidence_assessment))
        invalid["evidence"][0][numeric] = non_finite
        with pytest.raises(ValidationError):
            AssetConditionAssessment.model_validate(invalid)


def _assessment_payload():
    snapshot = json.loads(
        (FIXTURES / "digital-twin-snapshot-live.valid.json").read_text(encoding="utf-8")
    )
    return {
        "schemaVersion": "1.0",
        "assessmentId": "00000000-0000-4000-8000-000000000003",
        "assetTag": snapshot["assetTag"],
        "sensorId": "s1",
        "window": {"start": snapshot["generatedAt"], "end": snapshot["generatedAt"], "receivedAt": snapshot["generatedAt"], "freshnessMs": 0},
        "quality": {"status": "ok", "flags": []},
        "operatingContext": {"state": "steady", "estimated": True},
        "assessment": {"status": "normal", "anomalyScore": 0.1, "deteriorationScore": 0.2, "scoreSemantics": "relative_to_historical_baseline_not_failure_probability", "episodeId": None, "persistenceSeconds": 0},
        "componentTag": None,
        "recommendation": None,
        "humanValidationRequired": True,
        "evidence": [],
        "model": {"name": "robust-baseline", "version": "1.0.0", "configHash": f"sha256:{'0' * 64}", "trainedUntil": snapshot["generatedAt"]},
        "limitations": [],
    }
