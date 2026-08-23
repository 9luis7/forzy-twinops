from pathlib import Path

from twinops.ml.artifacts import load_artifact_bundle


_MANIFEST_HASH = "sha256:fe2cbd7e1b576f04b2c6380e41ecb7c97df7faa5084c39c4b0d16db786afe7f0"
_MODEL_HASH = "sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba"


def test_deployed_artifact_bundle_matches_runtime_trust_anchors():
    project_root = Path(__file__).resolve().parents[4]

    bundle = load_artifact_bundle(
        project_root / "artifacts" / "ml" / "real-forzy",
        expected_manifest_hash=_MANIFEST_HASH,
        expected_model_hash=_MODEL_HASH,
    )

    assert bundle.manifest["model"]["version"] == "1.0.1"
