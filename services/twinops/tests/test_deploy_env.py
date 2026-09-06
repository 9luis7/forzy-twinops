import pytest

from scripts import verify_env
from scripts.verify_env import verify_deploy_env


def _valid_deploy_env(**overrides):
    env = {
        "DATABASE_URL": (
            "postgresql://user:secret@ep-demo-pooler.example.neon.tech/db"
            "?sslmode=require"
        ),
        "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
        "TWINOPS_ML_ARTIFACT_PATH": "artifacts/ml/real-forzy",
        "TWINOPS_ML_MANIFEST_HASH": (
            "sha256:fe2cbd7e1b576f04b2c6380e41ecb7c97df7faa5084c39c4b0d16db786afe7f0"
        ),
        "TWINOPS_ML_MODEL_HASH": (
            "sha256:68d00121edbf8c4c01cf7cd231cd57c4c8eff25661135494e3c791ca78e562ba"
        ),
    }
    env.update(overrides)
    return env


def test_deploy_requires_database_upstream_and_pinned_artifact_hashes():
    report = verify_deploy_env({})

    assert set(report.missing) == {
        "DATABASE_URL",
        "TWINOPS_UPSTREAM_BASE_URL",
        "TWINOPS_ML_ARTIFACT_PATH",
        "TWINOPS_ML_MANIFEST_HASH",
        "TWINOPS_ML_MODEL_HASH",
    }
    assert report.invalid == ()
    assert report.ok is False


def test_deploy_rejects_untrusted_values_by_variable_name_only():
    env = {
        "DATABASE_URL": "postgresql://user:secret@database.invalid/db?sslmode=disable",
        "TWINOPS_UPSTREAM_BASE_URL": "http://upstream.invalid",
        "TWINOPS_ML_ARTIFACT_PATH": "artifacts/ml/untrusted",
        "TWINOPS_ML_MANIFEST_HASH": f"sha256:{'1' * 64}",
        "TWINOPS_ML_MODEL_HASH": f"sha256:{'2' * 64}",
        "TWINOPS_ASSET_ID": "fictional-asset",
        "TWINOPS_TIMEZONE": "UTC",
        "TWINOPS_POLL_INTERVAL_SECONDS": "0",
        "TWINOPS_REQUEST_TIMEOUT_SECONDS": "nan",
    }

    report = verify_deploy_env(env)

    assert report.missing == ()
    assert set(report.invalid) == set(env)
    assert report.ok is False
    assert "secret" not in repr(report)
    assert "database.invalid" not in repr(report)
    assert "upstream.invalid" not in repr(report)


def test_deploy_accepts_pooled_tls_neon_and_exact_runtime_anchors():
    report = verify_deploy_env(_valid_deploy_env())

    assert report.ok is True
    assert report.missing == ()
    assert report.invalid == ()
    assert "secret" not in repr(report)


def test_enabled_rag_requires_every_backend_anchor_by_variable_name_only():
    report = verify_deploy_env(_valid_deploy_env(TWINOPS_RAG_ENABLED="true"))

    assert set(report.missing) == {
        "AI_GATEWAY_API_KEY",
        "TWINOPS_RAG_EMBEDDING_DIMENSIONS",
        "TWINOPS_RAG_EMBEDDING_MODEL",
        "TWINOPS_RAG_EQUIPMENT_MODEL",
        "TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS",
        "TWINOPS_RAG_GENERATION_MODEL",
        "TWINOPS_RAG_MANUFACTURER",
        "TWINOPS_RAG_QUERY_TIMEOUT_SECONDS",
    }
    assert report.invalid == ()


def test_enabled_rag_accepts_vercel_oidc_instead_of_a_static_gateway_key():
    report = verify_deploy_env(
        _valid_deploy_env(
            TWINOPS_RAG_ENABLED="true",
            VERCEL_OIDC_TOKEN="short-lived-oidc-token",
            TWINOPS_RAG_MANUFACTURER="WEG",
            TWINOPS_RAG_EQUIPMENT_MODEL="W22",
            TWINOPS_RAG_EMBEDDING_MODEL="google/text-multilingual-embedding-002",
            TWINOPS_RAG_EMBEDDING_DIMENSIONS="768",
            TWINOPS_RAG_GENERATION_MODEL="openai/gpt-5.6-luna",
            TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS="10",
            TWINOPS_RAG_QUERY_TIMEOUT_SECONDS="10",
        )
    )

    assert report.ok is True
    assert report.missing == ()
    assert report.invalid == ()


def test_enabled_direct_gemini_rag_requires_and_accepts_its_backend_secret():
    common = {
        "TWINOPS_RAG_ENABLED": "true",
        "TWINOPS_RAG_PROVIDER": "gemini",
        "TWINOPS_RAG_MANUFACTURER": "WEG",
        "TWINOPS_RAG_EQUIPMENT_MODEL": "W22",
        "TWINOPS_RAG_EMBEDDING_MODEL": "gemini-embedding-2",
        "TWINOPS_RAG_EMBEDDING_DIMENSIONS": "768",
        "TWINOPS_RAG_GENERATION_MODEL": "gemini-3.5-flash-lite",
        "TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS": "10",
        "TWINOPS_RAG_QUERY_TIMEOUT_SECONDS": "10",
    }

    missing = verify_deploy_env(_valid_deploy_env(**common))
    valid = verify_deploy_env(
        _valid_deploy_env(**common, GEMINI_API_KEY="direct-gemini-secret")
    )

    assert missing.missing == ("GEMINI_API_KEY",)
    assert missing.invalid == ()
    assert valid.ok is True
    assert "direct-gemini-secret" not in repr(valid)


def test_enabled_rag_rejects_wrong_models_identity_dimensions_and_timeouts_safely():
    env = _valid_deploy_env(
        TWINOPS_RAG_ENABLED="true",
        AI_GATEWAY_API_KEY="never-print-this",
        TWINOPS_RAG_MANUFACTURER=" WEG",
        TWINOPS_RAG_EQUIPMENT_MODEL="",
        TWINOPS_RAG_EMBEDDING_MODEL="other/embed",
        TWINOPS_RAG_EMBEDDING_DIMENSIONS="0",
        TWINOPS_RAG_GENERATION_MODEL="other/chat",
        TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS="11",
        TWINOPS_RAG_QUERY_TIMEOUT_SECONDS="12",
    )

    report = verify_deploy_env(env)

    assert set(report.invalid) == {
        "TWINOPS_RAG_MANUFACTURER",
        "TWINOPS_RAG_EMBEDDING_MODEL",
        "TWINOPS_RAG_EMBEDDING_DIMENSIONS",
        "TWINOPS_RAG_GENERATION_MODEL",
        "TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS",
        "TWINOPS_RAG_QUERY_TIMEOUT_SECONDS",
    }
    assert report.missing == ("TWINOPS_RAG_EQUIPMENT_MODEL",)
    assert "never-print-this" not in repr(report)


def test_rag_admin_flags_are_valid_only_for_preview_and_public_ui_has_no_secret():
    common = _valid_deploy_env(
        RAG_ADMIN_ENABLED="true",
        VITE_RAG_ADMIN_ENABLED="true",
        VERCEL_ENV="production",
        AI_GATEWAY_API_KEY="backend-only",
        TWINOPS_RAG_MANUFACTURER="WEG",
        TWINOPS_RAG_EQUIPMENT_MODEL="W22",
        TWINOPS_RAG_EMBEDDING_MODEL="google/text-multilingual-embedding-002",
        TWINOPS_RAG_EMBEDDING_DIMENSIONS="768",
        TWINOPS_RAG_GENERATION_MODEL="openai/gpt-5.6-luna",
        TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS="10",
        TWINOPS_RAG_QUERY_TIMEOUT_SECONDS="10",
        RAG_PREVIEW_DATABASE_NAME="twinops_preview",
        RAG_PREVIEW_DATABASE_USER="preview_user",
    )

    invalid = verify_deploy_env(common)
    common["VERCEL_ENV"] = "preview"
    valid = verify_deploy_env(common)

    assert set(invalid.invalid) == {"RAG_ADMIN_ENABLED", "VERCEL_ENV", "VITE_RAG_ADMIN_ENABLED"}
    assert valid.ok is True
    assert not any(name.startswith("VITE_") and "KEY" in name for name in common)


def test_preview_admin_requires_external_database_identity_allowlist_by_name():
    report = verify_deploy_env(
        _valid_deploy_env(
            RAG_ADMIN_ENABLED="true",
            VITE_RAG_ADMIN_ENABLED="true",
            VERCEL_ENV="preview",
            AI_GATEWAY_API_KEY="backend-only",
            TWINOPS_RAG_MANUFACTURER="WEG",
            TWINOPS_RAG_EQUIPMENT_MODEL="W22",
            TWINOPS_RAG_EMBEDDING_MODEL="google/text-multilingual-embedding-002",
            TWINOPS_RAG_EMBEDDING_DIMENSIONS="768",
            TWINOPS_RAG_GENERATION_MODEL="openai/gpt-5.6-luna",
            TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS="10",
            TWINOPS_RAG_QUERY_TIMEOUT_SECONDS="10",
        )
    )

    assert set(report.missing) == {
        "RAG_PREVIEW_DATABASE_NAME",
        "RAG_PREVIEW_DATABASE_USER",
    }
    assert report.invalid == ()


def test_preview_database_identity_allowlist_rejects_untrimmed_values_safely():
    env = _valid_deploy_env(
        RAG_ADMIN_ENABLED="true",
        VERCEL_ENV="preview",
        AI_GATEWAY_API_KEY="backend-only",
        TWINOPS_RAG_MANUFACTURER="WEG",
        TWINOPS_RAG_EQUIPMENT_MODEL="W22",
        TWINOPS_RAG_EMBEDDING_MODEL="google/text-multilingual-embedding-002",
        TWINOPS_RAG_EMBEDDING_DIMENSIONS="768",
        TWINOPS_RAG_GENERATION_MODEL="openai/gpt-5.6-luna",
        TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS="10",
        TWINOPS_RAG_QUERY_TIMEOUT_SECONDS="10",
        RAG_PREVIEW_DATABASE_NAME=" twinops_preview",
        RAG_PREVIEW_DATABASE_USER="preview_user ",
    )

    report = verify_deploy_env(env)

    assert set(report.invalid) == {
        "RAG_PREVIEW_DATABASE_NAME",
        "RAG_PREVIEW_DATABASE_USER",
    }
    assert "twinops_preview" not in repr(report)
    assert "preview_user" not in repr(report)


@pytest.mark.parametrize(
    "database_url",
    [
        (
            "postgresql://user:secret@ep-demo-pooler.example.neon.tech/db"
            "?sslmode=require&sslmode=disable"
        ),
        (
            "postgresql://user:secret@ep-demo-pooler.example.neon.tech/db"
            "?sslmode=disable&sslmode=require"
        ),
        (
            "postgresql://user:secret@ep-demo-pooler.example.neon.tech/db"
            "?ssl%6dode=require&sslmode=disable"
        ),
        (
            "postgresql://user:secret@ep-demo-pooler.example.neon.tech/db"
            "?sslmode=require#"
        ),
        "postgresql://user:secret@ep-demo-pooler.example.neon.tech/db",
    ],
)
def test_deploy_rejects_missing_or_duplicate_sslmode(database_url):
    report = verify_deploy_env(_valid_deploy_env(DATABASE_URL=database_url))

    assert report.invalid == ("DATABASE_URL",)


def test_deploy_accepts_one_percent_encoded_safe_sslmode():
    report = verify_deploy_env(
        _valid_deploy_env(
            DATABASE_URL=(
                "postgresql://user:secret@ep-demo-pooler.example.neon.tech/db"
                "?sslmode=%72equire"
            )
        )
    )

    assert report.ok is True


@pytest.mark.parametrize(
    "upstream_url",
    [
        "https://user:secret@example.ngrok-free.app",
        "https://example.ngrok-free.app/path",
        "https://example.ngrok-free.app?token=secret",
        "https://example.ngrok-free.app?",
        "https://example.ngrok-free.app#fragment",
        "https://example.ngrok-free.app#",
        "https://example.ngrok-free.app\\@attacker.invalid",
        "https://example.ngrok-free.app:0",
        "https://example.ngrok-free.app:70000",
        " https://example.ngrok-free.app",
    ],
)
def test_deploy_rejects_upstream_values_that_are_not_clean_https_origins(
    upstream_url,
):
    report = verify_deploy_env(
        _valid_deploy_env(TWINOPS_UPSTREAM_BASE_URL=upstream_url)
    )

    assert report.invalid == ("TWINOPS_UPSTREAM_BASE_URL",)


@pytest.mark.parametrize(
    "upstream_url",
    [
        "https://example.ngrok-free.app",
        "https://example.ngrok-free.app/",
        "https://example.ngrok-free.app:443",
        "https://[2001:db8::1]:8443/",
    ],
)
def test_deploy_accepts_clean_https_origins(upstream_url):
    report = verify_deploy_env(
        _valid_deploy_env(TWINOPS_UPSTREAM_BASE_URL=upstream_url)
    )

    assert report.ok is True


def test_verify_env_cli_reports_names_without_file_values(tmp_path, capsys):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        'DATABASE_URL="postgresql://user:secret@ep-demo-pooler.example.neon.tech/db?sslmode=require"\n',
        encoding="utf-8",
    )

    result = verify_env.main(["--file", str(env_file)])

    captured = capsys.readouterr()
    assert result == 1
    assert captured.err == ""
    assert captured.out.strip() == (
        "deploy_env_failed "
        "missing=TWINOPS_ML_ARTIFACT_PATH,TWINOPS_ML_MANIFEST_HASH,"
        "TWINOPS_ML_MODEL_HASH,TWINOPS_UPSTREAM_BASE_URL invalid=-"
    )
    assert "secret" not in captured.out
    assert "neon.tech" not in captured.out
