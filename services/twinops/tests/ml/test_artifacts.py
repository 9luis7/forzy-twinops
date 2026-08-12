from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from twinops.ml.artifacts import (
    ArtifactIntegrityError,
    load_artifact_bundle,
    save_artifact_bundle,
)
from twinops.ml.baseline import BaselineConfig, RobustBaseline


def _fitted_pipeline():
    start = datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)
    frame = pd.DataFrame(
        {
            "event_at": [start + timedelta(seconds=i) for i in range(4)],
            "sensor_id": ["s1"] * 4,
            "cycle_id": [0] * 4,
            "operating_state": ["steady"] * 4,
            "feature_valid": [True] * 4,
            "velocity_ewma": [0.1, 0.11, 0.09, 0.1],
            "velocity_slope": [0.0] * 4,
            "velocity_change_point": [0.0] * 4,
            "temperature_deviation": [0.0] * 4,
        }
    )
    return RobustBaseline(BaselineConfig()).fit(frame)


def test_artifact_bundle_round_trips_with_verified_hashes(tmp_path):
    pipeline = _fitted_pipeline()
    config = {"dataset": {"kind": "test_fixture"}, "holdoutCount": 2}
    report = {"status": "fixture_validation", "cycleResults": []}

    manifest = save_artifact_bundle(tmp_path, pipeline, config, report)
    loaded = load_artifact_bundle(tmp_path)

    assert loaded.config == config
    assert loaded.report == report
    assert loaded.pipeline.centers_ == pipeline.centers_
    assert loaded.manifest == manifest
    assert set(manifest["files"]) == {
        "pipeline.joblib",
        "pipeline-config.json",
        "backtest-report.json",
        "model-card.md",
    }
    assert manifest["officialScoreExclusions"] == [
        "vibration_acceleration_statistic_unknown",
        "physical_s1_s2_difference_unconfirmed",
    ]


def test_modified_artifact_is_rejected_before_deserialization(tmp_path):
    save_artifact_bundle(
        tmp_path,
        _fitted_pipeline(),
        {"dataset": {"kind": "test_fixture"}},
        {"status": "fixture_validation"},
    )
    (tmp_path / "pipeline-config.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError, match="pipeline-config.json"):
        load_artifact_bundle(tmp_path)

