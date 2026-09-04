import pytest

from twinops.config_v2 import SettingsV2


def test_rag_admin_is_disabled_by_default_and_gateway_secret_is_not_repr_exposed():
    settings = SettingsV2.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "AI_GATEWAY_API_KEY": "top-secret",
        }
    )

    assert settings.rag_admin_enabled is False
    assert settings.rag_enabled is False
    assert settings.vercel_environment is None
    assert settings.rag_embedding_model == "google/text-multilingual-embedding-002"
    assert settings.rag_generation_model == "openai/gpt-5.6-luna"
    assert settings.rag_query_timeout_seconds <= 11
    assert "top-secret" not in repr(settings)


def test_preview_admin_configuration_is_explicit_and_version_anchors_are_loaded():
    settings = SettingsV2.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "VERCEL_ENV": "preview",
            "RAG_ADMIN_ENABLED": "true",
            "TWINOPS_RAG_MANUFACTURER": "Approved Manufacturer",
            "TWINOPS_RAG_EQUIPMENT_MODEL": "Approved Model",
            "TWINOPS_RAG_EMBEDDING_MODEL": "embed-v2",
            "TWINOPS_RAG_EMBEDDING_DIMENSIONS": "1024",
            "TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS": "7.5",
        }
    )

    assert settings.vercel_environment == "preview"
    assert settings.rag_admin_enabled is True
    assert settings.rag_embedding_model == "embed-v2"
    assert settings.rag_embedding_dimensions == 1024
    assert settings.rag_gateway_timeout_seconds == 7.5
    assert settings.rag_manufacturer == "Approved Manufacturer"
    assert settings.rag_equipment_model == "Approved Model"


@pytest.mark.parametrize(
    "overrides",
    [
        {"RAG_ADMIN_ENABLED": "yes"},
        {"VERCEL_ENV": "staging"},
        {"TWINOPS_RAG_EMBEDDING_DIMENSIONS": "0"},
        {"TWINOPS_RAG_GATEWAY_TIMEOUT_SECONDS": "nan"},
        {"TWINOPS_RAG_ENABLED": "yes"},
        {"TWINOPS_RAG_QUERY_TIMEOUT_SECONDS": "11.1"},
        {"TWINOPS_RAG_QUERY_TIMEOUT_SECONDS": "0.5"},
        {"TWINOPS_RAG_GENERATION_MODEL": ""},
    ],
)
def test_invalid_rag_environment_configuration_fails_closed(overrides):
    with pytest.raises(ValueError):
        SettingsV2.from_env(
            {
                "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
                **overrides,
            }
        )


def test_public_rag_configuration_is_explicit_and_secret_stays_backend_only():
    settings = SettingsV2.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "TWINOPS_RAG_ENABLED": "true",
            "TWINOPS_RAG_GENERATION_MODEL": "openai/gpt-5.6-luna",
            "TWINOPS_RAG_QUERY_TIMEOUT_SECONDS": "9.5",
            "AI_GATEWAY_API_KEY": "never-print-this",
            "TWINOPS_RAG_MANUFACTURER": "WEG",
            "TWINOPS_RAG_EQUIPMENT_MODEL": "W22",
        }
    )

    assert settings.rag_enabled is True
    assert settings.rag_query_timeout_seconds == 9.5
    assert "never-print-this" not in repr(settings)


def test_public_rag_uses_vercel_oidc_when_static_gateway_key_is_absent():
    settings = SettingsV2.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "TWINOPS_RAG_ENABLED": "true",
            "VERCEL_OIDC_TOKEN": "short-lived-oidc-token",
            "TWINOPS_RAG_MANUFACTURER": "WEG",
            "TWINOPS_RAG_EQUIPMENT_MODEL": "W22",
        }
    )

    assert settings.ai_gateway_api_key == "short-lived-oidc-token"
    assert "short-lived-oidc-token" not in repr(settings)


def test_direct_gemini_provider_uses_backend_secret_and_provider_defaults():
    settings = SettingsV2.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "TWINOPS_RAG_PROVIDER": "gemini",
            "GEMINI_API_KEY": "direct-gemini-secret",
        }
    )

    assert settings.rag_provider == "gemini"
    assert settings.rag_api_key == "direct-gemini-secret"
    assert settings.rag_embedding_model == "gemini-embedding-2"
    assert settings.rag_generation_model == "gemini-3.5-flash-lite"
    assert settings.rag_chat_base_url == (
        "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    assert "direct-gemini-secret" not in repr(settings)


def test_unknown_rag_provider_fails_closed():
    with pytest.raises(ValueError, match="TWINOPS_RAG_PROVIDER"):
        SettingsV2.from_env(
            {
                "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
                "TWINOPS_RAG_PROVIDER": "unknown",
            }
        )


@pytest.mark.parametrize(
    "identity",
    [
        {},
        {"TWINOPS_RAG_MANUFACTURER": "WEG"},
        {"TWINOPS_RAG_EQUIPMENT_MODEL": "W22"},
    ],
)
def test_enabled_public_rag_requires_both_exact_manual_identity_anchors(identity):
    with pytest.raises(ValueError, match="approved manufacturer"):
        SettingsV2.from_env(
            {
                "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
                "TWINOPS_RAG_ENABLED": "true",
                **identity,
            }
        )


@pytest.mark.parametrize(
    "identity",
    [
        {"TWINOPS_RAG_MANUFACTURER": "Approved Manufacturer"},
        {"TWINOPS_RAG_EQUIPMENT_MODEL": "Approved Model"},
        {},
    ],
)
def test_enabled_admin_requires_both_approved_manual_identity_anchors(identity):
    with pytest.raises(ValueError, match="approved manufacturer"):
        SettingsV2.from_env(
            {
                "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
                "VERCEL_ENV": "preview",
                "RAG_ADMIN_ENABLED": "true",
                **identity,
            }
        )
