"""Trusted runtime construction for the predictive assessment scorer."""

from pathlib import Path

from twinops.ml.artifacts import load_artifact_bundle
from twinops.ml.features import FeatureConfig
from twinops.ml.scorer import AssessmentScorer, ScorerConfig


def load_assessment_scorer(
    artifact_path: str | Path,
    *,
    expected_manifest_hash: str,
    expected_model_hash: str,
) -> AssessmentScorer:
    """Load a scorer only after caller-pinned manifest and model hashes pass."""

    bundle = load_artifact_bundle(
        artifact_path,
        expected_manifest_hash=expected_manifest_hash,
        expected_model_hash=expected_model_hash,
    )
    try:
        feature_config = FeatureConfig(**bundle.config["features"])
        scorer_config = ScorerConfig(**bundle.config["scorer"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("artifact runtime configuration is invalid") from exc
    return AssessmentScorer(
        bundle.pipeline,
        feature_config=feature_config,
        config=scorer_config,
    )
