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
    assert settings.vercel_environment is None
    assert settings.rag_embedding_model == "google/text-multilingual-embedding-002"
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
