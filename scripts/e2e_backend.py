"""Prepare an isolated real-history database and serve the TwinOps API."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import uvicorn


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "twinops" / "src"))

from twinops.config import Settings  # noqa: E402
from twinops.ingestion.forzy_history import import_forzy_history  # noqa: E402
from twinops.main import create_app  # noqa: E402
from twinops.ml.artifacts import compute_file_hash  # noqa: E402
from twinops.ml.runtime import load_assessment_scorer  # noqa: E402
from twinops.storage.sqlite_repository import SQLiteTelemetryRepository  # noqa: E402


EXPECTED_MANIFEST_HASH = (
    "sha256:3319936da354fe9bb1ec37755940688abacd57876a44bfeda3e1d78fef39aed5"
)
EXPECTED_MODEL_HASH = (
    "sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba"
)


def main() -> None:
    source = Path(
        os.environ.get(
            "E2E_FORZY_CSV",
            ROOT / "docs" / "History_32026-05-19T11-46-10-920.csv",
        )
    ).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"E2E Forzy CSV not found: {source}")

    temp_dir = (ROOT / "tmp" / "e2e").resolve()
    temp_dir.mkdir(parents=True, exist_ok=True)
    database_path = temp_dir / "twinops.sqlite3"
    reuse_database = os.environ.get("E2E_REUSE_DATABASE") == "1"
    if database_path.exists() and not reuse_database:
        database_path.unlink()

    artifact_path = (ROOT / "artifacts" / "ml" / "real-forzy").resolve()
    manifest_hash = compute_file_hash(artifact_path / "feature-manifest.json")
    model_hash = compute_file_hash(artifact_path / "pipeline.joblib")
    if manifest_hash != EXPECTED_MANIFEST_HASH or model_hash != EXPECTED_MODEL_HASH:
        raise RuntimeError("E2E ML artifact hashes do not match the trusted anchors")
    scorer = load_assessment_scorer(
        artifact_path,
        expected_manifest_hash=EXPECTED_MANIFEST_HASH,
        expected_model_hash=EXPECTED_MODEL_HASH,
    )

    settings = Settings(
        upstream_base_url="https://e2e.invalid",
        database_path=database_path,
        ml_artifact_path=artifact_path,
        ml_manifest_hash=EXPECTED_MANIFEST_HASH,
        ml_model_hash=EXPECTED_MODEL_HASH,
    )
    repository = SQLiteTelemetryRepository(database_path)
    repository.initialize()
    if reuse_database:
        print("E2E_DATABASE_REUSED", flush=True)
    else:
        report = import_forzy_history(
            source,
            repository,
            asset_tag=settings.asset_tag,
            timezone_name=settings.timezone_name,
            received_at=datetime.now(timezone.utc),
        )
        if report.rows_read != 7183 or report.samples_inserted != 14366:
            raise RuntimeError(f"unexpected E2E import report: {report}")
        print(f"E2E_IMPORT_READY {report}", flush=True)

    uvicorn.run(
        create_app(repository, settings, assessment_scorer=scorer),
        host="127.0.0.1",
        port=8000,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
