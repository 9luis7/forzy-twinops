from datetime import datetime, timedelta, timezone
from importlib.util import find_spec
from time import perf_counter

import pytest

from twinops.contracts.models import AssetConditionAssessment
from twinops.ml.baseline import BaselineConfig, RobustBaseline
from twinops.ml.curation import curate_samples
from twinops.ml.features import FeatureConfig, compute_trailing_features
from twinops.ml.scorer import AssessmentScorer, ScorerConfig


FEATURE_CONFIG = FeatureConfig(10, 60, 3)
EXPORTER_AVAILABLE = find_spec("twinops.ml.historical_assessments_v1") is not None


def _scorer(sample_factory):
    calibration = [
        sample_factory(second=index, velocity=0.1, temperature=30 + index * 0.01)
        for index in range(10)
    ]
    features = compute_trailing_features(
        curate_samples(calibration, gap_seconds=15), FEATURE_CONFIG
    )
    baseline = RobustBaseline(BaselineConfig(persistence_seconds=2)).fit(features)
    return AssessmentScorer(
        baseline,
        feature_config=FEATURE_CONFIG,
        config=ScorerConfig(gap_seconds=15, max_freshness_seconds=30),
    )


def test_gap_returns_insufficient_data(sample_factory):
    scorer = _scorer(sample_factory)
    samples = [
        sample_factory(second=0, velocity=0.1),
        sample_factory(second=2, velocity=0.1),
        sample_factory(second=120, velocity=2.0),
    ]

    result = scorer.assess(
        samples, now=datetime(2026, 8, 12, 13, 2, tzinfo=timezone.utc)
    )

    assert result.quality.status == "insufficient_data"
    assert result.assessment.status == "insufficient_data"
    assert result.assessment.anomaly_score == 0


def test_assessment_validates_shared_contract_and_versions_evidence(sample_factory):
    scorer = _scorer(sample_factory)
    samples = [
        sample_factory(second=index, velocity=0.1 + index * 0.01)
        for index in range(8)
    ]

    result = scorer.assess(
        samples, now=datetime(2026, 8, 12, 13, 0, 8, tzinfo=timezone.utc)
    )

    assert isinstance(result, AssetConditionAssessment)
    assert result.model.version == "1.0.1"
    assert result.model.config_hash.startswith("sha256:")
    assert result.assessment.score_semantics == "relative_to_historical_baseline_not_failure_probability"
    assert result.human_validation_required
    assert result.component_tag is None
    assert result.recommendation is None
    assert result.evidence
    assert all(item.id.startswith("ev-v1-") for item in result.evidence)
    assert all(item.feature != "acceleration" for item in result.evidence)


def test_identical_replay_produces_identical_json(sample_factory):
    scorer = _scorer(sample_factory)
    samples = [sample_factory(second=index, velocity=0.1) for index in range(6)]
    now = datetime(2026, 8, 12, 13, 0, 6, tzinfo=timezone.utc)

    first = scorer.assess(samples, now=now).model_dump_json(by_alias=True)
    second = scorer.assess(samples, now=now).model_dump_json(by_alias=True)

    assert first == second


def test_stale_source_never_falls_back_to_mechanical_alert(sample_factory):
    scorer = _scorer(sample_factory)
    samples = [
        sample_factory(second=index, velocity=10, quality_flags=["stale_source"])
        for index in range(6)
    ]

    result = scorer.assess(
        samples, now=datetime(2026, 8, 12, 13, 0, 6, tzinfo=timezone.utc)
    )

    assert result.quality.status == "insufficient_data"
    assert result.assessment.status == "insufficient_data"


def test_public_single_assessment_boundary_rejects_multisensor_input(sample_factory):
    scorer = _scorer(sample_factory)
    samples = [
        sample_factory(second=0, sensor_id="s1"),
        sample_factory(second=1, sensor_id="s2"),
        sample_factory(second=2, sensor_id="s1"),
    ]

    with pytest.raises(ValueError, match="single sensor"):
        scorer.assess(
            samples, now=datetime(2026, 8, 12, 13, 0, 3, tzinfo=timezone.utc)
        )


@pytest.mark.skipif(not EXPORTER_AVAILABLE, reason="covered by the VS6A RED tracer")
def test_live_and_historical_paths_share_the_exact_evidence_builder(sample_factory):
    from twinops.ml.evidence import build_assessment_evidence

    scorer = _scorer(sample_factory)
    samples = [
        sample_factory(second=index, velocity=0.1 + index * 0.01)
        for index in range(8)
    ]
    now = datetime(2026, 8, 12, 13, 0, 8, tzinfo=timezone.utc)
    result = scorer.assess(samples, now=now)
    relevant = curate_samples(samples, gap_seconds=15)
    features = compute_trailing_features(relevant, FEATURE_CONFIG)
    scored = scorer.baseline.score(features)

    shared = build_assessment_evidence(
        scored.iloc[-1],
        scorer.baseline,
        window_seconds=FEATURE_CONFIG.long_window_seconds,
    )

    assert tuple(result.evidence) == shared
    assert [item.feature for item in shared] == list(scorer.baseline.config.feature_columns)
    assert [item.unit for item in shared] == ["mm/s", "mm/s/s", "mm/s", "degC"]


@pytest.mark.performance
def test_features_and_inference_p95_is_at_most_100_ms(sample_factory):
    scorer = _scorer(sample_factory)
    samples = [
        sample_factory(second=index, velocity=0.1 + (index % 10) * 0.001)
        for index in range(1000)
    ]
    now = datetime(2026, 8, 12, 13, 16, 40, tzinfo=timezone.utc)
    durations = []
    for _ in range(7):
        started = perf_counter()
        scorer.assess(samples, now=now)
        durations.append((perf_counter() - started) * 1000)

    p95 = sorted(durations)[-1]
    print(f"features+inference ms p50={sorted(durations)[3]:.2f} p95={p95:.2f} p99={p95:.2f}")
    assert p95 <= 100
