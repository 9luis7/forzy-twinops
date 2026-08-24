from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from jsonschema.exceptions import SchemaError
from pydantic import ValidationError

import twinops.contracts.timeline_v1_models as contracts
from twinops.contracts.timeline_v1_models import (
    CollectionPolicyV1,
    HistoricalAssessmentV1,
    HistoricalSensorReadingV1,
    TimelineContextV1,
    TimelineDecisionFactsV1,
    TimelineEventCandidateV1,
    TimelineOverviewV1,
    TimelinePageV1,
    TimelinePointV1,
    TimelineRangeOverflow,
    public_millisecond_successor_v1,
    validate_timeline_public_v1,
)

FIXTURES = Path(__file__).resolve().parents[4] / "contracts/timeline/v1/fixtures"
SCHEMA_DIR = FIXTURES.parent


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _live_assessment_context() -> dict[str, object]:
    point = _fixture("live-point.valid.json")
    at = point["eventAt"]
    return {
        "schemaVersion": "1.0",
        "assetId": "forzy-motor-01",
        "selectedAt": at,
        "segmentId": "00000000-0000-5000-8000-000000000010",
        "anchor": copy.deepcopy(point),
        "channels": {"s1": copy.deepcopy(point), "s2": None},
        "assessment": {
            "schemaVersion": "2.0",
            "assessmentId": "00000000-0000-4000-8000-000000000003",
            "assetId": "forzy-motor-01",
            "sensorId": "s1",
            "window": {"start": at, "end": at, "receivedAt": at, "freshnessMs": 0},
            "quality": {"status": "ok", "flags": []},
            "operatingContext": {"state": "steady", "estimated": True},
            "assessment": {
                "status": "watch",
                "anomalyScore": 0.1,
                "deteriorationScore": 0.2,
                "scoreSemantics": "relative_to_historical_baseline_not_failure_probability",
                "episodeId": "episode-live-1",
                "persistenceSeconds": 5,
            },
            "componentTag": None,
            "recommendation": None,
            "humanValidationRequired": True,
            "evidence": [
                {"id": "ev-1", "feature": "temperature", "value": 30, "unit": "degC"}
            ],
            "model": {
                "name": "robust-baseline",
                "version": "1.0.0",
                "configHash": f"sha256:{'0' * 64}",
                "trainedUntil": at,
            },
            "limitations": [],
        },
        "decisionFacts": {
            "schemaVersion": "1.0",
            "conditionState": "watch",
            "conditionTemporalScope": "current",
            "conditionAsOf": at,
            "conditionEpisodeStartedAt": None,
            "conditionSource": "live_assessment",
            "collectionState": "received_now",
            "collectionExpectation": "expected_now",
            "dataAvailability": "partial",
            "dataFreshness": "fresh",
            "dataTrust": "degraded",
        },
        "provenance": {
            "pointSourceKind": "live_collection",
            "pointSourceSystem": "forzy-api",
            "activeHistoricalBatchId": None,
            "collectionPolicyId": "forzy-live-window-v1",
            "assessmentSource": "live_assessment",
        },
        "capabilities": {
            "historicalNavigation": False,
            "pairedChannels": False,
            "causalAssessment": True,
            "baselineComparison": True,
            "previousCycleComparison": False,
        },
        "limitations": [],
    }


def _degraded_normal_context() -> dict[str, object]:
    payload = _live_assessment_context()
    payload["assessment"]["assessment"].update(
        status="normal",
        episodeId=None,
        persistenceSeconds=0,
    )
    payload["decisionFacts"].update(
        conditionState="normal",
        conditionTemporalScope="none",
        conditionAsOf=None,
        conditionEpisodeStartedAt=None,
        conditionSource="none",
    )
    payload["provenance"]["assessmentSource"] = "none"
    return payload


VALID_CASES = [
    ("historical-reading.valid.json", "historical-sensor-reading", HistoricalSensorReadingV1),
    ("live-point.valid.json", "timeline-point", TimelinePointV1),
    ("historical-assessment.valid.json", "historical-assessment", HistoricalAssessmentV1),
    ("collection-policy.valid.json", "collection-policy", CollectionPolicyV1),
    ("event-candidate-historical.valid.json", "timeline-event-candidate", TimelineEventCandidateV1),
    ("event-candidate-live.valid.json", "timeline-event-candidate", TimelineEventCandidateV1),
    ("overview-unified.valid.json", "timeline-overview", TimelineOverviewV1),
    ("overview-live-only.valid.json", "timeline-overview", TimelineOverviewV1),
    ("page.valid.json", "timeline-page", TimelinePageV1),
    ("context-missing-channel.valid.json", "timeline-context", TimelineContextV1),
    ("context-historical-candidate.valid.json", "timeline-context", TimelineContextV1),
    ("context-historical-gap.valid.json", "timeline-context", TimelineContextV1),
]


def _model_accepts(model_type: type, payload: dict[str, object]) -> bool:
    try:
        model_type.model_validate(payload)
    except (ValidationError, ValueError, TypeError):
        return False
    return True


def _composed_accepts(schema_name: str, payload: dict[str, object]) -> bool:
    try:
        validate_timeline_public_v1(schema_name, payload)
    except Exception:
        return False
    return True


def _invariants_accept(schema_name: str, payload: dict[str, object]) -> bool:
    try:
        contracts.assert_timeline_invariants_v1(payload, schema_name)
    except Exception:
        return False
    return True


def _assert_rejected_everywhere(
    schema_name: str, model_type: type, payload: dict[str, object]
) -> None:
    assert _model_accepts(model_type, payload) is False
    assert _composed_accepts(schema_name, payload) is False


@pytest.mark.parametrize(("fixture_name", "schema_name", "model_type"), VALID_CASES)
def test_timeline_fixture_matrix_accepts_valid_cases(
    fixture_name: str, schema_name: str, model_type: type
) -> None:
    payload = _fixture(fixture_name)
    parsed = model_type.model_validate(payload)
    wire_json = parsed.model_dump_public_json()
    wire_payload = json.loads(wire_json)

    assert wire_payload == payload
    assert model_type.model_validate_json(wire_json) == parsed
    validate_timeline_public_v1(schema_name, payload)


def test_strict_public_json_accepts_aliases_and_emits_canonical_wire_values() -> None:
    payload = _fixture("live-point.valid.json")
    point = TimelinePointV1.model_validate(payload)
    wire = point.model_dump_public()

    assert wire["pointId"] == payload["pointId"]
    assert contracts.PUBLIC_UTC_MILLIS_RE.fullmatch(wire["eventAt"])
    assert wire["eventAt"] == payload["eventAt"]
    assert "point_id" not in wire
    assert TimelinePointV1.model_validate(wire) == point


def test_nested_measurements_accept_only_public_alias_keys() -> None:
    for snake_key, public_key in (
        ("vibration_velocity_rms", "vibrationVelocityRms"),
        ("semantic_confidence", "semanticConfidence"),
    ):
        payload = _fixture("live-point.valid.json")
        if public_key == "semanticConfidence":
            measurement = payload["measurements"]["temperature"]
        else:
            measurement = payload["measurements"]
        measurement[snake_key] = measurement.pop(public_key)
        _assert_rejected_everywhere("timeline-point", TimelinePointV1, payload)

    snake_case = copy.deepcopy(payload)
    snake_case["point_id"] = snake_case.pop("pointId")
    with pytest.raises(ValidationError):
        TimelinePointV1.model_validate(snake_case)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pointId", 123),
        ("pointId", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),
        ("eventAt", 1_724_329_600),
        ("eventAt", "2026-08-22T12:00:00+00:00"),
        ("eventAt", "2026-08-22T12:00:00.123456Z"),
        ("eventAt", "2026-02-29T12:00:00.123Z"),
        ("eventAt", "0000-01-01T00:00:00.000Z"),
    ],
)
def test_identifier_and_timestamp_matrix_is_rejected_by_both_public_layers(
    field: str, value: object
) -> None:
    payload = _fixture("live-point.valid.json")
    payload[field] = value
    _assert_rejected_everywhere("timeline-point", TimelinePointV1, payload)


@pytest.mark.parametrize("value", ["1.1", True, math.nan, math.inf, -math.inf])
def test_measurement_numbers_do_not_coerce_or_admit_non_finite_values(value: object) -> None:
    payload = _fixture("historical-reading.valid.json")
    payload["measurements"]["temperature"]["value"] = value
    _assert_rejected_everywhere(
        "historical-sensor-reading", HistoricalSensorReadingV1, payload
    )


def test_composed_validators_parse_every_public_calendar_timestamp() -> None:
    reading = _fixture("historical-reading.valid.json")
    reading["provenance"]["ingestedAt"] = "2026-02-29T12:00:00.000Z"
    _assert_rejected_everywhere(
        "historical-sensor-reading", HistoricalSensorReadingV1, reading
    )

    archive_point = _fixture("context-historical-candidate.valid.json")["anchor"]
    archive_point["eventAt"] = "2026-02-29T12:00:00.000Z"
    _assert_rejected_everywhere("timeline-point", TimelinePointV1, archive_point)

    overview = _fixture("overview-live-only.valid.json")
    overview["requestedRange"]["from"] = "2026-02-29T12:00:00.000Z"
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, overview)

    facts = _live_assessment_context()["decisionFacts"]
    facts["conditionAsOf"] = "2026-02-29T12:00:00.000Z"
    _assert_rejected_everywhere(
        "timeline-decision-facts", TimelineDecisionFactsV1, facts
    )

    context = _fixture("context-historical-gap.valid.json")
    context["selectedAt"] = "2026-02-29T12:00:00.000Z"
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, context)


@pytest.mark.parametrize(
    ("fixture_name", "schema_name", "model_type", "path"),
    [
        ("historical-reading.valid.json", "historical-sensor-reading", HistoricalSensorReadingV1, ("measurements", "temperature")),
        ("historical-assessment.valid.json", "historical-assessment", HistoricalAssessmentV1, ("quality",)),
        ("overview-unified.valid.json", "timeline-overview", TimelineOverviewV1, ("requestedRange",)),
        ("overview-unified.valid.json", "timeline-overview", TimelineOverviewV1, ("aggregationSummary",)),
        ("overview-unified.valid.json", "timeline-overview", TimelineOverviewV1, ("segments", 0, "sensorCounts")),
        ("context-missing-channel.valid.json", "timeline-context", TimelineContextV1, ("provenance",)),
        ("context-missing-channel.valid.json", "timeline-context", TimelineContextV1, ("capabilities",)),
    ],
)
def test_nested_public_objects_reject_extra_keys(
    fixture_name: str,
    schema_name: str,
    model_type: type,
    path: tuple[object, ...],
) -> None:
    payload = _fixture(fixture_name)
    target: object = payload
    for part in path:
        target = target[part]
    target["unexpected"] = True
    _assert_rejected_everywhere(schema_name, model_type, payload)


def test_python_registry_checks_ids_schemas_duplicates_and_cross_references() -> None:
    builder = getattr(contracts, "build_timeline_schema_registry_v1", None)
    assert callable(builder), "RED:A1R:python-schema-registry-builder-missing"

    documents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SCHEMA_DIR.glob("*.schema.json"))
    ]
    documents.append(
        json.loads(
            (SCHEMA_DIR.parents[1] / "v2/asset-condition-assessment.schema.json").read_text(
                encoding="utf-8"
            )
        )
    )
    registry, validators = builder(documents)
    assert len(list(registry)) == 10
    assert set(validators) == {
        "collection-policy",
        "historical-assessment",
        "historical-sensor-reading",
        "timeline-context",
        "timeline-decision-facts",
        "timeline-event-candidate",
        "timeline-overview",
        "timeline-page",
        "timeline-point",
    }

    duplicate = documents + [copy.deepcopy(documents[0])]
    with pytest.raises(ValueError, match="duplicate timeline schema \\$id"):
        builder(duplicate)

    relative_id = copy.deepcopy(documents)
    relative_id[0]["$id"] = "relative/schema"
    with pytest.raises(ValueError, match="absolute"):
        builder(relative_id)

    invalid_schema = copy.deepcopy(documents)
    invalid_schema[0]["type"] = "not-a-json-schema-type"
    with pytest.raises(SchemaError):
        builder(invalid_schema)

    unresolved = copy.deepcopy(documents)
    context = next(document for document in unresolved if document["$id"].endswith("timeline-context"))
    context["properties"]["anchor"] = {"$ref": "forzy://contracts/timeline/v1/missing"}
    with pytest.raises(ValueError, match="unresolved"):
        builder(unresolved)


def test_source_and_provenance_cannot_be_crossed() -> None:
    _assert_rejected_everywhere(
        "timeline-point",
        TimelinePointV1,
        _fixture("source-provenance-cross.invalid.json"),
    )


def test_historical_assessment_causal_and_nested_shapes_fail_closed() -> None:
    for fixture_name in (
        "historical-assessment-future.invalid.json",
        "historical-assessment-episode.invalid.json",
    ):
        _assert_rejected_everywhere(
            "historical-assessment", HistoricalAssessmentV1, _fixture(fixture_name)
        )

    persistence = _fixture("historical-assessment.valid.json")
    persistence["persistence"]["persistenceSeconds"] = 899
    _assert_rejected_everywhere(
        "historical-assessment", HistoricalAssessmentV1, persistence
    )

    score = _fixture("historical-assessment.valid.json")
    score["status"] = "insufficient_data"
    score["anomalyScore"] = 0.1
    score["deteriorationScore"] = None
    score["persistence"] = {
        "episodeId": None,
        "episodeStartedAt": None,
        "persistenceSeconds": 0,
        "persistenceCount": 0,
    }
    _assert_rejected_everywhere("historical-assessment", HistoricalAssessmentV1, score)

    evidence = _fixture("historical-assessment.valid.json")
    evidence["evidence"] = [
        {
            "id": "ev-temperature",
            "feature": "temperature",
            "value": 30.0,
            "unit": "degC",
            "baseline": 29.0,
            "deviation": 1.0,
            "direction": "up",
            "windowSeconds": 60.0,
            "unexpected": True,
        }
    ]
    _assert_rejected_everywhere("historical-assessment", HistoricalAssessmentV1, evidence)


def _policy_hash(payload: dict[str, object]) -> str:
    selected = {
        key: payload[key]
        for key in (
            "schemaVersion",
            "collectionPolicyId",
            "assetId",
            "timezone",
            "activeWeekdays",
            "windowStartLocal",
            "windowEndLocal",
            "pollIntervalSeconds",
            "gapThresholdSeconds",
        )
    }
    canonical = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _candidate_uuid5(payload: dict[str, object]) -> str:
    name = "|".join(
        (
            "timeline-event-candidate-v1",
            str(payload["sourceKind"]),
            str(payload["batchId"] or "none"),
            str(payload["anchorPointId"]),
            str(payload["modelFamily"]),
            str(payload["modelVersion"]),
            str(payload["foldId"] or "none"),
        )
    )
    return str(uuid5(NAMESPACE_URL, name))


def _gap_uuid5(gap: dict[str, object]) -> str:
    name = "|".join(
        (
            "timeline-gap-v1",
            str(gap["gapType"]),
            str(gap["leftSegmentId"] or "none"),
            str(gap["rightSegmentId"] or "none"),
            str(gap["startAt"]),
            str(gap["endAt"]),
            str(gap["ruleVersion"]),
        )
    )
    return str(uuid5(NAMESPACE_URL, name))


def test_collection_policy_hash_validity_and_versioned_identity_are_composed() -> None:
    _assert_rejected_everywhere(
        "collection-policy",
        CollectionPolicyV1,
        _fixture("collection-policy-hash.invalid.json"),
    )

    future = _fixture("collection-policy.valid.json")
    future["collectionPolicyId"] = "forzy-live-window-v2"
    future["effectiveFrom"] = "2026-09-01T00:00:00.000Z"
    future["configurationHash"] = _policy_hash(future)
    assert _model_accepts(CollectionPolicyV1, future)
    assert _composed_accepts("collection-policy", future)

    invalid_interval = copy.deepcopy(future)
    invalid_interval["effectiveTo"] = "2026-08-31T23:59:59.999Z"
    _assert_rejected_everywhere("collection-policy", CollectionPolicyV1, invalid_interval)

    reordered = _fixture("collection-policy.valid.json")
    reordered["activeWeekdays"] = ["wednesday", "tuesday", "monday"]
    reordered["configurationHash"] = _policy_hash(reordered)
    _assert_rejected_everywhere("collection-policy", CollectionPolicyV1, reordered)


def test_open_ended_policy_still_parses_effective_from_calendar() -> None:
    policy = _fixture("collection-policy.valid.json")
    policy["effectiveFrom"] = "2026-02-29T00:00:00.000Z"
    assert _model_accepts(CollectionPolicyV1, policy) is False
    assert _composed_accepts("collection-policy", policy) is False, (
        "RED:FR1:I2:open-ended-policy-skips-effective-from-calendar"
    )


def test_event_candidate_source_quality_model_and_episode_facts_fail_closed() -> None:
    for fixture_name in (
        "event-candidate-cross.invalid.json",
        "event-candidate-episode.invalid.json",
    ):
        _assert_rejected_everywhere(
            "timeline-event-candidate", TimelineEventCandidateV1, _fixture(fixture_name)
        )

    flags = _fixture("event-candidate-live.valid.json")
    flags["quality"]["flags"] = ["z_flag", "a_flag"]
    _assert_rejected_everywhere("timeline-event-candidate", TimelineEventCandidateV1, flags)

    trust = _fixture("event-candidate-live.valid.json")
    trust["quality"]["status"] = "insufficient_data"
    trust["dataTrust"] = "sufficient"
    _assert_rejected_everywhere("timeline-event-candidate", TimelineEventCandidateV1, trust)

    empty_model = _fixture("event-candidate-live.valid.json")
    empty_model["modelVersion"] = ""
    _assert_rejected_everywhere(
        "timeline-event-candidate", TimelineEventCandidateV1, empty_model
    )


def test_candidate_id_is_the_frozen_uuid5_identity() -> None:
    for fixture_name in (
        "event-candidate-historical.valid.json",
        "event-candidate-live.valid.json",
    ):
        payload = _fixture(fixture_name)
        assert payload["candidateId"] == _candidate_uuid5(payload), (
            "RED:A1R:deterministic-candidate-uuid5-missing"
        )

        crossed = copy.deepcopy(payload)
        crossed["candidateId"] = "00000000-0000-5000-8000-000000000099"
        _assert_rejected_everywhere(
            "timeline-event-candidate", TimelineEventCandidateV1, crossed
        )


def _malformed_gap_overview() -> dict[str, object]:
    payload = _fixture("overview-unified.valid.json")
    payload["gaps"] = [
        {
            "gapId": "00000000-0000-5000-8000-000000000020",
            "leftSegmentId": payload["segments"][0]["segmentId"],
            "rightSegmentId": payload["segments"][1]["segmentId"],
            "startAt": "2026-08-22T12:00:00.000Z",
            "endAt": "2026-08-22T12:01:00.000Z",
            "gapType": "archive_sampling_gap",
            "durationSeconds": 59,
            "ruleVersion": "timeline-gap-v1",
            "messageCode": "timeline_gap_expected_idle",
        }
    ]
    payload["gaps"][0]["gapId"] = _gap_uuid5(payload["gaps"][0])
    return payload


def test_overview_segment_gap_membership_and_count_rules_fail_closed() -> None:
    crossed_segment = _fixture("overview-unified.valid.json")
    crossed_segment["segments"][0]["collectionPolicyId"] = "forzy-live-window-v1"
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, crossed_segment)

    sensor_count = _fixture("overview-unified.valid.json")
    sensor_count["segments"][0]["sensorCounts"] = {"s1": 0, "s2": 0}
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, sensor_count)

    membership = _fixture("overview-unified.valid.json")
    membership["series"][0]["sensorId"] = "s2"
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, membership)

    assumptions = _fixture("overview-unified.valid.json")
    assumptions["segments"][0]["assumptions"] = ["same", "same"]
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, assumptions)

    _assert_rejected_everywhere(
        "timeline-overview", TimelineOverviewV1, _malformed_gap_overview()
    )


def test_gap_id_is_the_frozen_uuid5_identity() -> None:
    payload = _fixture("overview-unified.valid.json")
    for gap in payload["gaps"]:
        assert gap["gapId"] == _gap_uuid5(gap), (
            "RED:A1R:deterministic-gap-uuid5-missing"
        )

    crossed = copy.deepcopy(payload)
    crossed["gaps"][0]["gapId"] = "00000000-0000-5000-8000-000000000099"
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, crossed)


def test_overview_aggregation_ceiling_method_summary_and_order_are_coherent() -> None:
    payload = _fixture("overview-unified.valid.json")
    assert len(payload["gaps"]) >= 3, "RED:A1R:multi-segment-three-gap-fixture-missing"
    assert len(payload["segments"]) >= 4
    assert sum(row["aggregation"]["returnedPointCount"] for row in payload["series"]) <= 40
    TimelineOverviewV1.model_validate(payload)
    validate_timeline_public_v1("timeline-overview", payload)

    per_segment_ceiling = copy.deepcopy(payload)
    template_point = copy.deepcopy(payload["series"][0]["points"][0])
    for row in per_segment_ceiling["series"]:
        row["aggregation"]["returnedPointCount"] = 20
        row["aggregation"]["originalPointCount"] = 20
        row["aggregation"]["omittedPointCount"] = 0
        row["points"] = [copy.deepcopy(template_point) for _ in range(20)]
    per_segment_ceiling["aggregationSummary"].update(
        originalPointCount=80,
        returnedPointCount=80,
        omittedPointCount=0,
    )
    _assert_rejected_everywhere(
        "timeline-overview", TimelineOverviewV1, per_segment_ceiling
    )

    mixed_method = copy.deepcopy(payload)
    mixed_method["series"][0]["aggregation"]["method"] = "none"
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, mixed_method)

    wrong_summary = copy.deepcopy(payload)
    wrong_summary["aggregationSummary"]["reducedSeriesCount"] = 0
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, wrong_summary)

    wrong_ceiling = copy.deepcopy(payload)
    wrong_ceiling["series"][0]["aggregation"]["requestedMaxPoints"] = 41
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, wrong_ceiling)

    reversed_series = copy.deepcopy(payload)
    reversed_series["series"] = list(reversed(reversed_series["series"]))
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, reversed_series)

    reversed_points = copy.deepcopy(payload)
    reversed_points["series"][0]["points"] = list(
        reversed(reversed_points["series"][0]["points"])
    )
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, reversed_points)


def test_overview_none_method_requires_full_retention() -> None:
    payload = _fixture("overview-unified.valid.json")
    payload["aggregationSummary"]["requestedMaxPoints"] = 100
    payload["aggregationSummary"]["reducedSeriesCount"] = 0
    for row in payload["series"]:
        row["aggregation"]["requestedMaxPoints"] = 100
        row["aggregation"]["method"] = "none"
    assert _composed_accepts("timeline-overview", payload) is False, (
        "RED:FR1:I3:none-method-retains-omissions"
    )
    assert _model_accepts(TimelineOverviewV1, payload) is False


def test_overview_requires_every_nonzero_segment_sensor_group() -> None:
    payload = _fixture("overview-unified.valid.json")
    omitted = payload["series"].pop()
    assert omitted["aggregation"]["originalPointCount"] > 0
    assert omitted["points"] == []
    segments = {segment["segmentId"]: segment for segment in payload["segments"]}
    for row in payload["series"]:
        row["aggregation"]["originalPointCount"] = 15
        row["aggregation"]["omittedPointCount"] = (
            15 - row["aggregation"]["returnedPointCount"]
        )
        segment = segments[row["segmentId"]]
        segment["sensorCounts"]["s1"] = 15
        segment["totalPoints"] = 15
    payload["aggregationSummary"].update(
        originalPointCount=45,
        returnedPointCount=4,
        omittedPointCount=41,
        reducedSeriesCount=3,
    )
    assert _composed_accepts("timeline-overview", payload) is False, (
        "RED:FR1:I3:nonzero-zero-selected-group-may-be-omitted"
    )
    assert _model_accepts(TimelineOverviewV1, payload) is False


def _operating_cycles(count: int = 204) -> list[dict[str, object]]:
    cycles: list[dict[str, object]] = []
    for index in range(count):
        cycle_id = f"00000000-0000-5000-8000-{index + 256:012x}"
        cycles.append(
            {
                "operatingCycleId": cycle_id,
                "sourceKind": "historical_archive",
                "batchId": "sha256:" + "a" * 64,
                "startAt": f"2026-08-22T{index // 60:02d}:{index % 60:02d}:00.000Z",
                "endAt": f"2026-08-22T{index // 60:02d}:{index % 60:02d}:00.000Z",
                "durationSeconds": 0.0,
                "totalPoints": 2,
                "sensorCounts": {"s1": 1, "s2": 1},
                "candidateCount": 0,
                "gapBeforeSeconds": None if index == 0 else 60.0,
                "previousOperatingCycleId": None if index == 0 else cycles[-1]["operatingCycleId"],
                "assumptions": [],
            }
        )
    return cycles


def test_204_cycle_matrix_enforces_order_counts_duration_and_predecessors() -> None:
    payload = _fixture("overview-unified.valid.json")
    payload["operatingCycles"] = _operating_cycles()
    assert len(payload["operatingCycles"]) == 204
    TimelineOverviewV1.model_validate(payload)
    validate_timeline_public_v1("timeline-overview", payload)

    for mutation in ("sensorCounts", "durationSeconds", "previousOperatingCycleId", "order"):
        invalid = copy.deepcopy(payload)
        if mutation == "sensorCounts":
            invalid["operatingCycles"][1]["sensorCounts"]["s2"] = 0
        elif mutation == "durationSeconds":
            invalid["operatingCycles"][1]["durationSeconds"] = 1.0
        elif mutation == "previousOperatingCycleId":
            invalid["operatingCycles"][2]["previousOperatingCycleId"] = invalid["operatingCycles"][0]["operatingCycleId"]
        else:
            invalid["operatingCycles"][0], invalid["operatingCycles"][1] = invalid["operatingCycles"][1], invalid["operatingCycles"][0]
        _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, invalid)


def test_context_missing_channel_gap_assessment_and_provenance_branches_are_exact() -> None:
    missing = _fixture("context-missing-channel.valid.json")
    assert sum(point is not None for point in missing["channels"].values()) == 1, (
        "RED:A1R:missing-channel-fixture-does-not-prove-nullability"
    )

    candidate = _fixture("context-historical-candidate.valid.json")
    assert candidate["assessment"] is not None, "RED:A1R:matching-causal-assessment-missing"
    TimelineContextV1.model_validate(candidate)
    validate_timeline_public_v1("timeline-context", candidate)

    _assert_rejected_everywhere(
        "timeline-context",
        TimelineContextV1,
        _fixture("context-decision-facts-cross.invalid.json"),
    )

    provenance = _fixture("context-missing-channel.valid.json")
    provenance["provenance"]["pointSourceKind"] = "live_collection"
    provenance["provenance"]["pointSourceSystem"] = "forzy-csv"
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, provenance)

    gap = _fixture("context-historical-gap.valid.json")
    gap["channels"]["s1"] = _fixture("live-point.valid.json")
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, gap)


def test_nested_roots_compose_child_invariants() -> None:
    page = _fixture("page.valid.json")
    point = _fixture("live-point.valid.json")
    point["provenance"]["receivedAt"] = "2026-08-22T12:00:00.124Z"
    page["items"] = [point]
    _assert_rejected_everywhere("timeline-page", TimelinePageV1, page)

    overview = _fixture("overview-unified.valid.json")
    candidate = _fixture("event-candidate-live.valid.json")
    candidate["candidateId"] = "00000000-0000-5000-8000-000000000099"
    overview["eventCandidates"] = [candidate]
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, overview)

    context = _fixture("context-historical-candidate.valid.json")
    context["assessment"]["persistence"]["persistenceSeconds"] = 899
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, context)


def test_overview_range_claims_preserve_explicit_bounds_and_global_availability() -> None:
    bounded = _fixture("overview-unified.valid.json")
    bounded["requestedRange"] = {
        "from": "2026-08-22T11:59:00.000Z",
        "to": "2026-08-22T12:04:00.000Z",
    }
    bounded["effectiveRange"] = copy.deepcopy(bounded["requestedRange"])
    TimelineOverviewV1.model_validate(bounded)
    validate_timeline_public_v1("timeline-overview", bounded)

    crossed = copy.deepcopy(bounded)
    crossed["effectiveRange"]["to"] = bounded["availableRange"]["to"]
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, crossed)

    no_result = _fixture("overview-live-only.valid.json")
    no_result["requestedRange"] = {
        "from": "2026-08-22T13:00:00.000Z",
        "to": "2026-08-22T14:00:00.000Z",
    }
    no_result["availableRange"] = {
        "from": "2026-08-22T12:00:00.000Z",
        "to": "2026-08-22T12:00:00.124Z",
    }
    TimelineOverviewV1.model_validate(no_result)
    validate_timeline_public_v1("timeline-overview", no_result)


def test_overview_requires_one_metric_and_one_series_per_returned_group() -> None:
    mixed_metric = _fixture("overview-unified.valid.json")
    mixed_metric["series"][1]["metric"] = "vibrationAcceleration"
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, mixed_metric)

    duplicate_group = _fixture("overview-unified.valid.json")
    duplicate_group["series"].append(copy.deepcopy(duplicate_group["series"][-1]))
    duplicate_group["aggregationSummary"]["originalPointCount"] += 11
    duplicate_group["aggregationSummary"]["omittedPointCount"] += 11
    duplicate_group["aggregationSummary"]["reducedSeriesCount"] += 1
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, duplicate_group)


def test_cycle_gap_and_candidate_cycle_graph_facts_are_exact() -> None:
    payload = _fixture("overview-unified.valid.json")
    payload["operatingCycles"] = _operating_cycles()

    bad_gap = copy.deepcopy(payload)
    bad_gap["operatingCycles"][1]["gapBeforeSeconds"] = 59.0
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, bad_gap)

    unknown_cycle = copy.deepcopy(payload)
    unknown_cycle["eventCandidates"] = [
        _fixture("event-candidate-historical.valid.json")
    ]
    _assert_rejected_everywhere("timeline-overview", TimelineOverviewV1, unknown_cycle)


def test_page_archive_items_use_only_the_active_historical_batch() -> None:
    page = _fixture("page.valid.json")
    archive_point = _fixture("context-historical-candidate.valid.json")["anchor"]
    page["items"] = [archive_point]
    _assert_rejected_everywhere("timeline-page", TimelinePageV1, page)

    page["activeHistoricalBatchId"] = archive_point["provenance"]["batchId"]
    TimelinePageV1.model_validate(page)
    validate_timeline_public_v1("timeline-page", page)


def test_context_channel_availability_pair_and_provenance_facts_are_exact() -> None:
    missing = _fixture("context-missing-channel.valid.json")
    wrong_availability = copy.deepcopy(missing)
    wrong_availability["decisionFacts"]["dataAvailability"] = "complete"
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, wrong_availability)

    paired = _fixture("context-historical-candidate.valid.json")
    crossed_pair = copy.deepcopy(paired)
    crossed_pair["channels"]["s2"]["samplePairId"] = (
        "00000000-0000-5000-8000-000000000099"
    )
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, crossed_pair)

    no_navigation = copy.deepcopy(paired)
    no_navigation["capabilities"]["historicalNavigation"] = False
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, no_navigation)

    wrong_batch = copy.deepcopy(paired)
    wrong_batch["provenance"]["activeHistoricalBatchId"] = f"sha256:{'9' * 64}"
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, wrong_batch)


def test_context_resolves_unchanged_v2_assessment_and_preserves_public_bytes() -> None:
    payload = _live_assessment_context()
    parsed = TimelineContextV1.model_validate(payload)
    assert parsed.model_dump_public() == payload
    validate_timeline_public_v1("timeline-context", payload)
    assert (
        TimelineContextV1.model_validate_json(parsed.model_dump_public_json())
        .model_dump_public_json()
        == parsed.model_dump_public_json()
    )


def test_context_retains_degraded_normal_assessment_with_suppressed_claims() -> None:
    payload = _degraded_normal_context()
    assert _composed_accepts("timeline-context", payload), (
        "RED:FR1:I4:degraded-normal-assessment-is-unrepresentable"
    )
    assert _model_accepts(TimelineContextV1, payload)


def test_context_degraded_normal_suppression_rejects_near_neighbors() -> None:
    watch = _degraded_normal_context()
    watch["assessment"]["assessment"]["status"] = "watch"
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, watch)

    wrong_label = _degraded_normal_context()
    wrong_label["decisionFacts"]["conditionState"] = "unknown"
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, wrong_label)

    unsuppressed = _degraded_normal_context()
    at = unsuppressed["selectedAt"]
    unsuppressed["decisionFacts"].update(
        conditionTemporalScope="current",
        conditionAsOf=at,
        conditionSource="live_assessment",
    )
    unsuppressed["provenance"]["assessmentSource"] = "live_assessment"
    _assert_rejected_everywhere("timeline-context", TimelineContextV1, unsuppressed)

    sufficient_complete = _degraded_normal_context()
    second = copy.deepcopy(sufficient_complete["channels"]["s1"])
    second["sensorId"] = "s2"
    second["pointId"] = "00000000-0000-5000-8000-000000000005"
    second["provenance"]["readingId"] = second["pointId"]
    sufficient_complete["channels"]["s2"] = second
    sufficient_complete["decisionFacts"]["dataAvailability"] = "complete"
    sufficient_complete["decisionFacts"]["dataTrust"] = "sufficient"
    sufficient_complete["capabilities"]["pairedChannels"] = True
    _assert_rejected_everywhere(
        "timeline-context", TimelineContextV1, sufficient_complete
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "wrong_sensor",
        "condition_as_of",
        "window_order",
        "anchor_received_at",
        "selected_at",
        "invented_episode_start",
        "freshness_arithmetic",
        "future_trained_model",
        "quality_trust",
    ),
)
def test_live_v2_assessment_must_match_causal_context(mutation: str) -> None:
    payload = _live_assessment_context()
    if mutation == "wrong_sensor":
        payload["assessment"]["sensorId"] = "s2"
    elif mutation == "condition_as_of":
        payload["decisionFacts"]["conditionAsOf"] = "2026-08-22T12:00:00.124Z"
    elif mutation == "window_order":
        payload["assessment"]["window"]["start"] = "2026-08-22T12:00:00.124Z"
    elif mutation == "anchor_received_at":
        payload["assessment"]["window"]["receivedAt"] = "2026-08-22T12:00:00.124Z"
        payload["decisionFacts"]["conditionAsOf"] = "2026-08-22T12:00:00.124Z"
        payload["selectedAt"] = "2026-08-22T12:00:00.124Z"
        payload["assessment"]["window"]["freshnessMs"] = 1
    elif mutation == "selected_at":
        payload["selectedAt"] = "2026-08-22T12:00:00.124Z"
    elif mutation == "invented_episode_start":
        payload["decisionFacts"]["conditionEpisodeStartedAt"] = payload[
            "decisionFacts"
        ]["conditionAsOf"]
    elif mutation == "freshness_arithmetic":
        payload["assessment"]["window"]["freshnessMs"] = 1
    elif mutation == "future_trained_model":
        payload["assessment"]["model"]["trainedUntil"] = (
            "2026-08-22T12:00:00.124Z"
        )
    elif mutation == "quality_trust":
        payload["assessment"]["quality"]["status"] = "insufficient_data"
    assert _composed_accepts("timeline-context", payload) is False, (
        f"RED:FR1:I5:live-assessment-causality:{mutation}"
    )
    assert _model_accepts(TimelineContextV1, payload) is False


def test_live_v2_assessment_asset_must_match_even_before_schema_validation() -> None:
    payload = _live_assessment_context()
    payload["assessment"]["assetId"] = "crossed-asset"
    assert _invariants_accept("timeline-context", payload) is False, (
        "RED:FR1:I5:live-assessment-causality:crossed_asset"
    )


def test_decision_facts_reject_historical_and_unavailable_crossings() -> None:
    historical = _fixture("context-historical-candidate.valid.json")["decisionFacts"]
    historical["dataFreshness"] = "fresh"
    _assert_rejected_everywhere(
        "timeline-decision-facts", TimelineDecisionFactsV1, historical
    )

    unavailable = {
        "schemaVersion": "1.0",
        "conditionState": "watch",
        "conditionTemporalScope": "current",
        "conditionAsOf": "2026-08-22T12:00:00.000Z",
        "conditionEpisodeStartedAt": None,
        "conditionSource": "live_assessment",
        "collectionState": "unavailable",
        "collectionExpectation": "not_applicable",
        "dataAvailability": "unavailable",
        "dataFreshness": "unknown",
        "dataTrust": "insufficient",
    }
    _assert_rejected_everywhere(
        "timeline-decision-facts", TimelineDecisionFactsV1, unavailable
    )


def test_page_items_use_total_order_without_duplicate_points() -> None:
    point = _fixture("live-point.valid.json")
    later = copy.deepcopy(point)
    later["pointId"] = "00000000-0000-5000-8000-000000000005"
    later["eventAt"] = "2026-08-22T12:00:00.124Z"
    later["provenance"]["readingId"] = later["pointId"]
    later["provenance"]["scheduledAt"] = later["eventAt"]
    later["provenance"]["receivedAt"] = later["eventAt"]

    page = _fixture("page.valid.json")
    page["items"] = [point, later]
    TimelinePageV1.model_validate(page)
    validate_timeline_public_v1("timeline-page", page)

    reversed_page = copy.deepcopy(page)
    reversed_page["items"].reverse()
    _assert_rejected_everywhere("timeline-page", TimelinePageV1, reversed_page)

    duplicate_page = copy.deepcopy(page)
    duplicate_page["items"] = [point, copy.deepcopy(point)]
    _assert_rejected_everywhere("timeline-page", TimelinePageV1, duplicate_page)


def test_canonical_json_is_byte_stable_after_revalidation() -> None:
    for fixture_name, _, model_type in VALID_CASES:
        payload = _fixture(fixture_name)
        first = model_type.model_validate(payload).model_dump_public_json()
        second = model_type.model_validate_json(first).model_dump_public_json()
        assert first == second

    overview = TimelineOverviewV1.model_validate(_fixture("overview-unified.valid.json"))
    first = overview.model_dump_public()
    second = TimelineOverviewV1.model_validate_json(
        overview.model_dump_public_json()
    ).model_dump_public()
    assert [row["segmentId"] for row in first["series"]] == [
        row["segmentId"] for row in second["series"]
    ]
    assert [point["pointId"] for row in first["series"] for point in row["points"]] == [
        point["pointId"] for row in second["series"] for point in row["points"]
    ]


def test_public_millisecond_successor_uses_the_literal_shared_matrix() -> None:
    cases = _fixture("public-millisecond-successor-v1-cases.json")
    for case in cases["valid"]:
        actual = public_millisecond_successor_v1(
            datetime.fromisoformat(case["input"].replace("Z", "+00:00"))
        )
        assert actual.isoformat(timespec="milliseconds").replace("+00:00", "Z") == case["expected"]

    with pytest.raises(ValueError, match="timeline_invalid_public_millisecond"):
        public_millisecond_successor_v1(
            datetime(2026, 8, 22, 12, 0, 0, 123_400, tzinfo=timezone.utc)
        )
    with pytest.raises(TimelineRangeOverflow, match="timeline_range_overflow"):
        public_millisecond_successor_v1(
            datetime(9999, 12, 31, 23, 59, 59, 999_000, tzinfo=timezone.utc)
        )
