from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from twinops.ml.artifacts import (
    ArtifactIntegrityError,
    compute_file_hash,
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
    loaded = load_artifact_bundle(
        tmp_path,
        expected_manifest_hash=compute_file_hash(tmp_path / "feature-manifest.json"),
        expected_model_hash=manifest["files"]["pipeline.joblib"],
    )

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
        load_artifact_bundle(
            tmp_path,
            expected_manifest_hash=compute_file_hash(tmp_path / "feature-manifest.json"),
            expected_model_hash=compute_file_hash(tmp_path / "pipeline.joblib"),
        )


def test_replaced_manifest_and_pickle_are_rejected_before_deserialization(
    tmp_path, monkeypatch
):
    manifest = save_artifact_bundle(
        tmp_path,
        _fitted_pipeline(),
        {"dataset": {"kind": "test_fixture"}},
        {"status": "fixture_validation"},
    )
    trusted_manifest_hash = compute_file_hash(tmp_path / "feature-manifest.json")
    trusted_model_hash = manifest["files"]["pipeline.joblib"]
    (tmp_path / "pipeline.joblib").write_bytes(b"attacker pickle")
    replaced = dict(manifest)
    replaced["files"] = dict(manifest["files"])
    replaced["files"]["pipeline.joblib"] = compute_file_hash(
        tmp_path / "pipeline.joblib"
    )
    (tmp_path / "feature-manifest.json").write_text(
        __import__("json").dumps(replaced), encoding="utf-8"
    )
    deserialized = False

    def forbidden_load(*args, **kwargs):
        nonlocal deserialized
        deserialized = True
        raise AssertionError("joblib.load must not run before external anchors pass")

    monkeypatch.setattr("twinops.ml.artifacts.joblib.load", forbidden_load)

    with pytest.raises(ArtifactIntegrityError, match="trusted manifest"):
        load_artifact_bundle(
            tmp_path,
            expected_manifest_hash=trusted_manifest_hash,
            expected_model_hash=trusted_model_hash,
        )
    assert not deserialized
