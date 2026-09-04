from pathlib import Path


ROOT = Path(__file__).parents[3]


def test_ci_uses_disposable_versioned_pgvector_service_for_only_the_rag_integration():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "rag-pgvector:" in workflow
    assert "image: pgvector/pgvector:0.8.6-pg16-bookworm" in workflow
    assert (
        "TEST_DATABASE_URL: "
        "postgresql://twinops_test:twinops_test@localhost:5432/twinops_test"
    ) in workflow
    assert "003_rag_asset_aware_v1.sql" in workflow
    assert "tests/rag/test_pgvector_integration.py" in workflow
    assert "secrets.TEST_DATABASE_URL" not in workflow


def test_ci_runs_hashed_deploy_install_and_bundled_browser_fake_e2e():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "python -m pip install --require-hashes -r requirements.txt" in workflow
    assert "rag-e2e:" in workflow
    assert "npx playwright install --with-deps chromium" in workflow
    assert "npm run test:e2e:rag" in workflow
