from datetime import datetime, timedelta, timezone

import pandas as pd

from twinops.ml.artifacts import compute_file_hash, save_artifact_bundle
from twinops.ml.baseline import RobustBaseline
from twinops.ml.features import FeatureConfig
from twinops.ml.runtime import load_assessment_scorer


def test_runtime_loads_scorer_only_after_external_hash_verification(tmp_path):
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
    pipeline = RobustBaseline().fit(frame)
    manifest = save_artifact_bundle(
        tmp_path,
        pipeline,
        {
            "dataset": {"kind": "test_fixture"},
            "features": {
                "short_window_seconds": 10,
                "long_window_seconds": 60,
                "min_points": 3,
            },
            "scorer": {"gap_seconds": 15, "max_freshness_seconds": 30},
        },
        {"status": "fixture_validation"},
    )

    scorer = load_assessment_scorer(
        tmp_path,
        expected_manifest_hash=compute_file_hash(
            tmp_path / "feature-manifest.json"
        ),
        expected_model_hash=manifest["files"]["pipeline.joblib"],
    )

    assert scorer.feature_config == FeatureConfig(10, 60, 3)
    assert scorer.config.gap_seconds == 15
    assert scorer.config.max_freshness_seconds == 30
