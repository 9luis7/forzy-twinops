from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from twinops.contracts.timeline_v1_models import HistoricalSensorReadingV1
from twinops.ingestion.history_profiles_v1 import (
    HistoricalStoredSampleV1,
    PreparedHistoricalBatchV1,
)
from twinops.ml.artifacts import compute_file_hash, save_artifact_bundle
from twinops.ml.baseline import BaselineConfig, RobustBaseline


try:
    from twinops.ml.backtest import WalkForwardRowAssessmentV1
    from twinops.ml.historical_assessments_v1 import (
        HistoricalAssessmentBuildV1,
        build_historical_assessments_v1,
    )
except ImportError:
    WalkForwardRowAssessmentV1 = None
    HistoricalAssessmentBuildV1 = None
    build_historical_assessments_v1 = None


def test_causal_historical_assessment_exporter_exists():
    if build_historical_assessments_v1 is None:
        pytest.fail("RED:VS6A:causal-historical-assessments-missing")


@pytest.mark.skipif(
    build_historical_assessments_v1 is None,
    reason="covered by the VS6A RED tracer",
)
def test_public_row_and_build_shapes_match_the_frozen_interface():
    assert tuple(field.name for field in fields(WalkForwardRowAssessmentV1)) == (
        "fold_id",
        "sensor_id",
        "reading_id",
        "anchor_event_at",
        "training_start",
        "training_end",
        "window_start",
        "window_end",
        "status",
        "anomaly_score",
        "deterioration_score",
        "episode_id",
        "episode_started_at",
        "persistence_seconds",
        "persistence_count",
        "quality_status",
        "quality_flags",
        "evidence",
        "model_family",
        "model_version",
        "fold_model_hash",
    )
    assert tuple(field.name for field in fields(HistoricalAssessmentBuildV1)) == (
        "assessments",
        "artifact_sha256",
        "feature_manifest_sha256",
        "report_sha256",
        "config_sha256",
        "candidate_count",
        "validated_anchor_count",
        "validated_episode_count",
    )


@pytest.mark.skipif(
    build_historical_assessments_v1 is None,
    reason="covered by the VS6A RED tracer",
)
def test_builder_exports_deterministic_strict_contract_rows(tmp_path):
    batch = _prepared_batch()
    artifact_dir, expected = _artifact_bundle(tmp_path, batch)

    first = build_historical_assessments_v1(batch, artifact_dir, **expected)
    second = build_historical_assessments_v1(batch, artifact_dir, **expected)

    assert first == second
    assert first.assessments
    assert first.validated_anchor_count == len(first.assessments)
    assert first.candidate_count == sum(
        stored.assessment.status in {"watch", "alert"}
        for stored in first.assessments
    )
    assert first.validated_episode_count == first.candidate_count
    anchors = {sample.point_id: sample.reading for sample in batch.samples}
    serialized = []
    for stored in first.assessments:
        assessment = stored.assessment
        anchor = anchors[str(assessment.anchor_point_id)]
        assert stored.batch_id == batch.batch_id
        assert str(assessment.assessment_id) == str(
            uuid5(
                NAMESPACE_URL,
                "|".join(
                    (
                        "historical-assessment-v1",
                        str(batch.batch_id),
                        assessment.fold_id,
                        str(assessment.anchor_point_id),
                    )
                ),
            )
        )
        assert assessment.sensor_id == anchor.sensor_id
        assert assessment.operating_cycle_id == anchor.operating_cycle_id
        assert assessment.assessment_at == anchor.event_at
        assert assessment.assessment_window.end == anchor.event_at
        assert assessment.training_window.end < assessment.assessment_window.start
        assert assessment.model_hash == expected["expected_artifact_sha256"]
        assert assessment.fold_hash.startswith("sha256:")
        assert assessment.report_hash == expected["expected_report_sha256"]
        assert assessment.component_tag is None
        assert assessment.human_validation_required is True
        expected_limitations = [
            "historical_source_participated_in_baseline_construction_and_evaluation",
            "relative_score_not_failure_probability_confidence_rul_or_diagnosis",
            "no_confirmed_failure_labels_available",
        ]
        if assessment.status in {"watch", "alert"}:
            expected_limitations.append("candidate_not_ground_truth")
        assert assessment.limitations == sorted(expected_limitations)
        assert [item.feature for item in assessment.evidence] == [
            "velocity_ewma",
            "velocity_slope",
            "velocity_change_point",
            "temperature_deviation",
        ]
        serialized.append(assessment.model_dump_json(by_alias=True))
    assert serialized == sorted(
        serialized,
        key=lambda payload: (
            json.loads(payload)["assessmentAt"],
            json.loads(payload)["anchorPointId"],
            json.loads(payload)["sensorId"],
            json.loads(payload)["foldId"],
        ),
    )


@pytest.mark.skipif(
    build_historical_assessments_v1 is None,
    reason="covered by the VS6A RED tracer",
)
@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("expected_artifact_sha256", "sha256:" + "a" * 64, "model"),
        ("expected_feature_manifest_sha256", "sha256:" + "b" * 64, "manifest"),
        ("expected_report_sha256", "sha256:" + "c" * 64, "report"),
        ("expected_config_sha256", "sha256:" + "d" * 64, "config"),
    ],
)
def test_builder_fails_closed_on_each_pinned_identity(
    tmp_path, field, replacement, message
):
    batch = _prepared_batch()
    artifact_dir, expected = _artifact_bundle(tmp_path, batch)
    expected[field] = replacement

    with pytest.raises(ValueError, match=message):
        build_historical_assessments_v1(batch, artifact_dir, **expected)


def test_episode_validator_rejects_future_and_cross_cycle_starts():
    from twinops.ml.historical_assessments_v1 import _validate_causal_episode_rows

    anchor_at = datetime(2026, 5, 19, 15, 2, 2, tzinfo=timezone.utc)
    valid = WalkForwardRowAssessmentV1(
        fold_id="fold-v1-0000",
        sensor_id="s1",
        reading_id="reading-cycle-2",
        anchor_event_at=anchor_at,
        training_start=anchor_at - timedelta(minutes=2),
        training_end=anchor_at - timedelta(seconds=90),
        window_start=anchor_at - timedelta(seconds=2),
        window_end=anchor_at,
        status="watch",
        anomaly_score=80.0,
        deterioration_score=50.0,
        episode_id="episode-cycle-2",
        episode_started_at=anchor_at,
        persistence_seconds=0.0,
        persistence_count=1,
        quality_status="ok",
        quality_flags=(),
        evidence=(),
        model_family="robust-baseline",
        model_version="1.0.1",
        fold_model_hash="sha256:" + "e" * 64,
    )
    frame = _episode_frame(anchor_at)

    _validate_causal_episode_rows((valid,), frame)
    with pytest.raises(ValueError, match="future"):
        _validate_causal_episode_rows(
            (replace(valid, episode_started_at=anchor_at + timedelta(seconds=1)),),
            frame,
        )
    with pytest.raises(ValueError, match="cycle"):
        _validate_causal_episode_rows(
            (replace(valid, episode_started_at=anchor_at - timedelta(minutes=1)),),
            frame,
        )


@pytest.mark.parametrize(
    "break_kind",
    (
        "normal",
        "missing_evaluation",
        "feature_invalid",
        "duplicate",
        "non_finite",
        "gap",
        "source",
        "policy",
        "model_family",
        "model_version",
    ),
)
def test_episode_validator_reconstructs_every_available_causal_boundary(
    break_kind,
):
    from twinops.ml.historical_assessments_v1 import _validate_causal_episode_rows

    start = datetime(2026, 5, 19, 15, 2, tzinfo=timezone.utc)
    first = _episode_assessment(
        reading_id="reading-0",
        anchor_at=start,
        episode_id="forged-continuation",
        episode_started_at=start,
        persistence_count=1,
    )
    last = _episode_assessment(
        reading_id="reading-2",
        anchor_at=start + timedelta(seconds=2),
        episode_id="forged-continuation",
        episode_started_at=start,
        persistence_count=2,
    )
    frame = _three_row_episode_frame(start)
    rows = [first, last]

    if break_kind == "normal":
        rows.insert(
            1,
            _episode_assessment(
                reading_id="reading-1",
                anchor_at=start + timedelta(seconds=1),
                status="normal",
            ),
        )
    elif break_kind == "feature_invalid":
        frame.loc[1, "feature_valid"] = False
    elif break_kind == "duplicate":
        frame.loc[1, "is_new_information"] = False
    elif break_kind == "non_finite":
        frame.loc[1, "velocity_ewma"] = float("nan")
    elif break_kind == "gap":
        frame.at[2, "quality_flags"] = ("gap_before",)
    elif break_kind == "source":
        frame.loc[2, "source"] = "other-history"
    elif break_kind == "policy":
        frame.loc[2, "collection_policy_id"] = "policy-b"
    elif break_kind == "model_family":
        rows[-1] = replace(last, model_family="other-baseline")
    elif break_kind == "model_version":
        rows[-1] = replace(last, model_version="1.0.2")

    with pytest.raises(ValueError, match="boundary"):
        _validate_causal_episode_rows(tuple(rows), frame)


def _episode_assessment(
    *,
    reading_id: str,
    anchor_at: datetime,
    status: str = "watch",
    episode_id: str | None = None,
    episode_started_at: datetime | None = None,
    persistence_count: int = 0,
) -> WalkForwardRowAssessmentV1:
    persistence_seconds = (
        0.0
        if episode_started_at is None
        else (anchor_at - episode_started_at).total_seconds()
    )
    return WalkForwardRowAssessmentV1(
        fold_id="fold-v1-0000",
        sensor_id="s1",
        reading_id=reading_id,
        anchor_event_at=anchor_at,
        training_start=anchor_at - timedelta(minutes=2),
        training_end=anchor_at - timedelta(minutes=1),
        window_start=anchor_at - timedelta(seconds=1),
        window_end=anchor_at,
        status=status,
        anomaly_score=80.0 if status != "normal" else 10.0,
        deterioration_score=50.0 if status != "normal" else 5.0,
        episode_id=episode_id,
        episode_started_at=episode_started_at,
        persistence_seconds=persistence_seconds,
        persistence_count=persistence_count,
        quality_status="ok",
        quality_flags=(),
        evidence=(),
        model_family="robust-baseline",
        model_version="1.0.1",
        fold_model_hash="sha256:" + "e" * 64,
    )


def _three_row_episode_frame(start: datetime):
    import pandas as pd

    rows = []
    for offset in range(3):
        event_at = start + timedelta(seconds=offset)
        rows.append(
            {
                "reading_id": f"reading-{offset}",
                "sensor_id": "s1",
                "cycle_id": 2,
                "event_at": event_at,
                "source": "forzy-csv",
                "collection_policy_id": "policy-a",
                "quality_flags": (),
                "feature_valid": True,
                "is_new_information": True,
                "velocity_ewma": 0.1,
                "velocity_slope": 0.0,
                "velocity_change_point": 0.0,
                "temperature_deviation": 0.0,
            }
        )
    return pd.DataFrame(rows)


def _episode_frame(anchor_at: datetime):
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "reading_id": "reading-cycle-1",
                "sensor_id": "s1",
                "cycle_id": 1,
                "event_at": anchor_at - timedelta(minutes=1),
            },
            {
                "reading_id": "reading-cycle-2",
                "sensor_id": "s1",
                "cycle_id": 2,
                "event_at": anchor_at,
            },
        ]
    )


def _prepared_batch() -> PreparedHistoricalBatchV1:
    imported_at = datetime(2026, 8, 20, tzinfo=timezone.utc)
    batch_id = "sha256:" + "1" * 64
    source_bytes = b"synthetic-history"
    source_sha = "sha256:" + sha256(source_bytes).hexdigest()
    samples = []
    for cycle_index in range(6):
        cycle_id = str(uuid5(NAMESPACE_URL, f"test-cycle|{cycle_index}"))
        for offset in range(5):
            event_at = datetime(2026, 5, 19, 15, cycle_index, offset, tzinfo=timezone.utc)
            for sensor_id in ("s1", "s2"):
                reading_id = str(
                    uuid5(NAMESPACE_URL, f"test-reading|{cycle_index}|{offset}|{sensor_id}")
                )
                point_id = str(
                    uuid5(NAMESPACE_URL, f"test-point|{cycle_index}|{offset}|{sensor_id}")
                )
                velocity = 0.10 + cycle_index * 0.02 + offset * 0.001
                if cycle_index == 5 and offset >= 2:
                    velocity += 4.0
                row_hash = "sha256:" + sha256(reading_id.encode()).hexdigest()
                reading = HistoricalSensorReadingV1.model_validate(
                    {
                        "schemaVersion": "1.0",
                        "readingId": reading_id,
                        "samplePairId": str(
                            uuid5(NAMESPACE_URL, f"test-pair|{cycle_index}|{offset}")
                        ),
                        "operatingCycleId": cycle_id,
                        "assetId": "forzy-motor-01",
                        "sensorId": sensor_id,
                        "eventAt": event_at,
                        "sourceTimestampText": event_at.isoformat(),
                        "sourceKind": "historical_archive",
                        "timestampQuality": "source_without_offset_assumed_timezone",
                        "measurements": {
                            "vibrationVelocityRms": {
                                "value": velocity,
                                "unit": "mm/s",
                                "semanticConfidence": "inferred_from_datasheet",
                            },
                            "vibrationAcceleration": {
                                "value": 0.0,
                                "unit": "g",
                                "statistic": "unknown",
                                "semanticConfidence": "unconfirmed",
                            },
                            "temperature": {
                                "value": 30.0 + cycle_index + offset * 0.01,
                                "unit": "degC",
                                "semanticConfidence": "inferred_from_datasheet",
                            },
                        },
                        "qualityFlags": [],
                        "provenance": {
                            "sourceSystem": "forzy-csv",
                            "batchId": batch_id,
                            "sourceFileSha256": source_sha,
                            "recordOrdinal": cycle_index * 5 + offset + 1,
                            "sourceLineNumber": cycle_index * 5 + offset + 4,
                            "rowSha256": row_hash,
                            "ingestedAt": imported_at,
                        },
                    }
                )
                samples.append(
                    HistoricalStoredSampleV1(
                        batch_id=batch_id,
                        record_ordinal=cycle_index * 5 + offset + 1,
                        point_id=point_id,
                        reading=reading,
                    )
                )
    manifest = {
        "sampleCount": len(samples),
        "operatingCycleCount": 6,
        "sourceSha256": source_sha,
    }
    manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return PreparedHistoricalBatchV1(
        batch_id=batch_id,
        asset_id="forzy-motor-01",
        source_bytes=source_bytes,
        source_sha256=source_sha,
        manifest_json=manifest_json,
        manifest_sha256="sha256:" + sha256(manifest_json.encode()).hexdigest(),
        imported_at=imported_at,
        raw_rows=(),
        samples=tuple(samples),
    )


def _artifact_bundle(
    tmp_path: Path, batch: PreparedHistoricalBatchV1
) -> tuple[Path, dict[str, str]]:
    artifact_dir = tmp_path / "artifacts"
    calibration = _calibration_frame()
    pipeline = RobustBaseline(BaselineConfig(persistence_seconds=1)).fit(calibration)
    save_artifact_bundle(
        artifact_dir,
        pipeline,
        {
            "dataset": {
                "rows": len(batch.samples),
                "cycleCount": 6,
                "sourceSha256": batch.source_sha256,
            },
            "holdoutCount": 2,
            "baseline": pipeline.config.__dict__,
            "features": {
                "short_window_seconds": 4,
                "long_window_seconds": 10,
                "min_points": 2,
            },
            "scorer": {"gap_seconds": 15.0, "max_freshness_seconds": 30},
        },
        {
            "candidate_events": [],
            "folds": [
                {
                    "fold": 0,
                    "train_cycle_ids": [0, 1],
                    "test_cycle_ids": [2],
                    "frozen_holdout": False,
                    "trained_until": "2026-05-19T15:01:04+00:00",
                },
                {
                    "fold": 1,
                    "train_cycle_ids": [0, 1, 2],
                    "test_cycle_ids": [3],
                    "frozen_holdout": False,
                    "trained_until": "2026-05-19T15:02:04+00:00",
                },
                {
                    "fold": 2,
                    "train_cycle_ids": [0, 1, 2, 3],
                    "test_cycle_ids": [4, 5],
                    "frozen_holdout": True,
                    "trained_until": "2026-05-19T15:03:04+00:00",
                },
            ],
        },
    )
    return artifact_dir, {
        "expected_artifact_sha256": compute_file_hash(artifact_dir / "pipeline.joblib"),
        "expected_feature_manifest_sha256": compute_file_hash(
            artifact_dir / "feature-manifest.json"
        ),
        "expected_report_sha256": compute_file_hash(
            artifact_dir / "backtest-report.json"
        ),
        "expected_config_sha256": pipeline.config_hash,
    }


def _calibration_frame():
    import pandas as pd

    rows = []
    for sensor_id in ("s1", "s2"):
        for index in range(4):
            rows.append(
                {
                    "event_at": datetime(2026, 5, 19, 14, 0, index, tzinfo=timezone.utc),
                    "sensor_id": sensor_id,
                    "cycle_id": 0,
                    "operating_state": "steady",
                    "feature_valid": True,
                    "velocity_ewma": 0.1 + index * 0.001,
                    "velocity_slope": 0.001,
                    "velocity_change_point": 0.001,
                    "temperature_deviation": index * 0.01,
                }
            )
    return pd.DataFrame(rows)
