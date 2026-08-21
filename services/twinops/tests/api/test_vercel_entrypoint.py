import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from fastapi import FastAPI

from twinops import main_v2


_MANIFEST_HASH = "sha256:3319936da354fe9bb1ec37755940688abacd57876a44bfeda3e1d78fef39aed5"
_MODEL_HASH = "sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba"


def test_vercel_python_runtime_is_pinned_for_binary_wheels():
    repository_root = Path(__file__).parents[4]

    assert (repository_root / ".python-version").read_text(encoding="utf-8").strip() == "3.12"


def test_vercel_requirements_only_include_runtime_science_dependencies():
    repository_root = Path(__file__).parents[4]
    requirements = {
        line.strip()
        for line in (repository_root / "requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "joblib>=1.4,<2" in requirements
    assert not any(line.startswith("scipy") for line in requirements)
    assert not any(line.startswith("scikit-learn") for line in requirements)


def test_vercel_function_excludes_local_secrets_and_nonruntime_files():
    repository_root = Path(__file__).parents[4]
    config = json.loads((repository_root / "vercel.json").read_text(encoding="utf-8"))
    exclude_files = config["functions"]["api/index.py"]["excludeFiles"]

    for pattern in (
        ".env",
        ".env.*",
        ".agents/**",
        "services/twinops/tests/**",
        "real-forzy/source-summary.json",
    ):
        assert pattern in exclude_files


def test_real_runtime_assessment_does_not_import_training_dependencies():
    expected = _run_real_runtime_assessment(block_training_dependencies=False)
    runtime_only = _run_real_runtime_assessment(block_training_dependencies=True)

    assert runtime_only == expected


def test_vercel_entrypoint_exposes_fastapi_without_external_io(monkeypatch):
    def forbidden_io(*args, **kwargs):
        raise AssertionError("Vercel entrypoint import must not perform external I/O")

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("TWINOPS_STARTUP_VALIDATE_ONLY", "1")
    monkeypatch.setenv("TWINOPS_UPSTREAM_BASE_URL", "https://upstream.invalid")
    monkeypatch.setenv("DATABASE_URL", "postgresql://runtime.invalid/twinops")
    monkeypatch.setenv("TWINOPS_ML_ARTIFACT_PATH", "artifacts/ml/real-forzy")
    monkeypatch.setenv("TWINOPS_ML_MANIFEST_HASH", f"sha256:{'1' * 64}")
    monkeypatch.setenv("TWINOPS_ML_MODEL_HASH", f"sha256:{'2' * 64}")
    monkeypatch.setattr(main_v2.PostgresTelemetryRepository, "initialize", forbidden_io)
    monkeypatch.setattr(main_v2.httpx, "AsyncClient", forbidden_io)
    monkeypatch.setattr(main_v2, "load_assessment_scorer", forbidden_io)
    sys.modules.pop("api.index", None)

    module = importlib.import_module("api.index")

    assert isinstance(module.app, FastAPI)


def test_vercel_entrypoint_bootstraps_bundled_twinops_source():
    repository_root = Path(__file__).parents[4]
    command = """
import runpy
import sys

sys.path = [
    item for item in sys.path
    if not item.replace('\\\\', '/').endswith('/services/twinops/src')
]
runpy.run_path('api/index.py')
print('imported')
"""
    env = {
        **os.environ,
        "VERCEL": "1",
        "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
        "DATABASE_URL": "postgresql://runtime.invalid/twinops",
    }

    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=repository_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "imported"


def _run_real_runtime_assessment(*, block_training_dependencies: bool) -> dict:
    repository_root = Path(__file__).parents[4]
    command = textwrap.dedent(
        """
        from datetime import datetime, timedelta, timezone
        import json
        from pathlib import Path
        import sys
        """
    )
    if block_training_dependencies:
        command += textwrap.dedent(
            """
            import importlib.abc

            class TrainingDependencyBlocker(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path, target=None):
                    if fullname.partition('.')[0] in {'scipy', 'sklearn'}:
                        raise ModuleNotFoundError(
                            f'training-only dependency imported: {fullname}'
                        )
                    return None

            sys.meta_path.insert(0, TrainingDependencyBlocker())
            """
        )
    command += textwrap.dedent(
        f"""
        from twinops.contracts.models import CanonicalSensorReading
        from twinops.ml.runtime import load_assessment_scorer

        root = Path.cwd()
        scorer = load_assessment_scorer(
            root / 'artifacts' / 'ml' / 'real-forzy',
            expected_manifest_hash='{_MANIFEST_HASH}',
            expected_model_hash='{_MODEL_HASH}',
        )
        base = datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)
        samples = []
        for second in range(4):
            instant = base + timedelta(seconds=second)
            timestamp = instant.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            samples.append(CanonicalSensorReading.model_validate({{
                'schemaVersion': '1.0',
                'readingId': f'00000000-0000-4000-8000-{{second:012d}}',
                'source': 'forzy-csv',
                'assetTag': 'MTR-BMB-042',
                'sensorId': 's1',
                'scheduledAt': None,
                'observedAt': timestamp,
                'receivedAt': timestamp,
                'measurements': {{
                    'vibrationVelocityRms': {{
                        'value': 0.1 + second * 0.001,
                        'unit': 'mm/s',
                        'semanticConfidence': 'inferred_from_datasheet',
                    }},
                    'vibrationAcceleration': {{
                        'value': 0.0,
                        'unit': 'g',
                        'statistic': 'unknown',
                        'semanticConfidence': 'unconfirmed',
                    }},
                    'temperature': {{
                        'value': 30.0 + second * 0.01,
                        'unit': 'degC',
                        'semanticConfidence': 'inferred_from_datasheet',
                    }},
                }},
                'qualityFlags': [],
                'payloadHash': f'sha256:{{second:064x}}',
                'raw': {{}},
                'provenance': {{
                    'sourceSystem': 'deploy-runtime-test',
                    'ingestedAt': timestamp,
                }},
            }}))
        result = scorer.assess(samples, now=base + timedelta(seconds=3))
        print(json.dumps(result.model_dump(mode='json', by_alias=True), sort_keys=True))
        """
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(repository_root / "services" / "twinops" / "src"),
    }

    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=repository_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)
