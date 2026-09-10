"""Trusted two-sensor context and bounded retrospective history."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from twinops.rag.operational import TrustedOperationalContext, build_analysis_context
from .test_demo_service import context, TIME


def frame(row, sensor="s1", *, time=TIME, value=0.04, repeated=False):
    return {"sensorId": sensor, "sourceRow": row, "observedAt": time,
            "measurements": {"vibrationVelocityRms": {"value": value, "unit": "mm/s"}},
            "qualityFlags": ["duplicate_payload"] if repeated else [], "gapBefore": False}


def test_cutoff_excludes_future_rows_even_when_timestamp_matches():
    source = context()
    source["history"] = [frame(149), frame(150), frame(151),
                         frame(140, time="2026-08-12T13:01:01Z")]
    projected = build_analysis_context(source)
    assert [row["sourceRow"] for row in projected["historyRows"]] == [149, 150]
    assert projected["origin"]["observedAt"] == TIME
    assert projected["origin"]["sourceRow"] == 150
    assert projected["origin"]["retrospective"] is True


def test_repeated_readings_do_not_claim_independent_trend_or_full_window():
    source = context()
    source["history"] = [frame(index, repeated=index > 146) for index in range(146, 151)]
    projected = build_analysis_context(source)
    window = projected["sensors"]["s1"]["windows"]["long"]
    assert window["count"] == 5
    assert window["newInformationCount"] == 1
    assert window["repeatedCount"] == 4
    assert window["coverageComplete"] is False
    assert window["measurements"]["vibrationVelocityRms"]["change"] == 0
    assert projected["sensors"]["s1"]["scoreHistoryAvailable"] is False


def test_prompt_detaches_both_sensor_scores_without_full_history_or_transport_secrets():
    source = context()
    source["history"] = [frame(150), frame(150, "s2", value=0.08)]
    source["token"] = "private-token"
    source["events"] = [{"recommendation": "untrusted-old-answer"}]
    operational = replace(TrustedOperationalContext.unavailable(operational_state="replay"),
                          analysis_context=build_analysis_context(source))
    prompt = operational.to_prompt_context()
    assert "historyRows" not in prompt
    assert set(prompt["sensors"]) == {"s1", "s2"}
    assert prompt["sensors"]["s2"]["assessment"]["assessment"]["anomalyScore"] == 0.5
    assert prompt["sensors"]["s2"]["manualCoverage"] is False
    encoded = json.dumps(prompt)
    assert "private-token" not in encoded and "untrusted-old-answer" not in encoded
    prompt["sensors"]["s2"]["assessment"]["assessment"]["anomalyScore"] = 99
    assert operational.to_prompt_context()["sensors"]["s2"]["assessment"]["assessment"]["anomalyScore"] == 0.5


def test_history_reservoir_is_bounded_and_preserves_sensor_identity():
    source = context()
    source["replay"]["sourceRow"] = 500
    source["history"] = [frame(index, sensor) for index in range(1, 501) for sensor in ("s1", "s2")]
    projected = build_analysis_context(source)
    assert len(projected["historyRows"]) == 600
    for sensor in ("s1", "s2"):
        assert projected["sensors"][sensor]["availableHistoryRows"] == 300
        assert len(projected["sensors"][sensor]["lastFive"]) == 5


def test_latest_sensor_mismatch_rejected_before_generation():
    source = context()
    source["sensors"]["s1"]["latest"] = frame(150, "s2")
    with pytest.raises(ValueError, match="cutoff"):
        build_analysis_context(source)


def test_missing_nullable_measurement_does_not_crash_or_count_as_zero():
    source = context()
    missing = frame(149)
    missing["measurements"] = {"vibrationVelocityRms": None,
                               "temperature": {"value": None, "unit": "degC"}}
    source["history"] = [missing, frame(150, value=0.04)]
    measurements = build_analysis_context(source)["sensors"]["s1"]["windows"]["short"]["measurements"]
    assert measurements["vibrationVelocityRms"]["mean"] == 0.04
    assert "temperature" not in measurements
