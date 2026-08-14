from datetime import datetime, timezone
from pathlib import Path

import pytest

from twinops.config_v2 import SettingsV2
from twinops.ingestion.live_adapter_v2 import (
    InvalidSensorPayloadV2,
    adapt_live_payload_v2,
)


SCHEDULED = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
RECEIVED = datetime(2026, 8, 12, 15, 0, 1, tzinfo=timezone.utc)


def test_retrieval_time_becomes_explicit_assumed_observation():
    sample = adapt_live_payload_v2(
        sensor_id="s1",
        payload={"dados1": {"Velocidade": 0.04, "Acelera\u00e7\u00e3o": 0.0, "Temperatura": 34}},
        scheduled_at=SCHEDULED,
        received_at=RECEIVED,
    )

    assert sample.asset_id == "forzy-motor-01"
    assert sample.observed_at == sample.received_at
    assert sample.timestamp_quality == "assumed_from_retrieval"
    assert sample.provenance.source_timestamp_provided is False


def test_adapter_hashes_only_canonical_upstream_payload():
    payload = {"dados1": {"Temperatura": 34, "Acelera\u00e7\u00e3o": 0.0, "Velocidade": 0.04}}

    sample = adapt_live_payload_v2(
        sensor_id="s1",
        payload=payload,
        scheduled_at=SCHEDULED,
        received_at=RECEIVED,
    )

    assert sample.raw.model_dump() == {}
    assert sample.payload_hash == (
        "sha256:933ba7a1a167aefcb2725ec1a0335b8b7f4f8ef536f94f914a3fdf4abd94789d"
    )


@pytest.mark.parametrize("invalid", ["0.0", None, True, float("nan"), float("inf")])
def test_rejects_invalid_acceleration_values(invalid):
    with pytest.raises(InvalidSensorPayloadV2, match="Acelera\u00e7\u00e3o"):
        adapt_live_payload_v2(
            sensor_id="s1",
            payload={
                "dados1": {
                    "Velocidade": 0.04,
                    "Acelera\u00e7\u00e3o": invalid,
                    "Temperatura": 34,
                }
            },
            scheduled_at=SCHEDULED,
            received_at=RECEIVED,
        )


def test_rejects_missing_acceleration_key():
    with pytest.raises(InvalidSensorPayloadV2, match="Acelera\u00e7\u00e3o"):
        adapt_live_payload_v2(
            sensor_id="s1",
            payload={"dados1": {"Velocidade": 0.04, "Temperatura": 34}},
            scheduled_at=SCHEDULED,
            received_at=RECEIVED,
        )


def test_local_settings_allow_no_database_url_but_deploy_requires_one():
    settings = SettingsV2.from_env(
        {"TWINOPS_UPSTREAM_BASE_URL": "https://example.invalid/"}
    )

    assert settings.database_url is None
    assert settings.database_path.name == "twinops.sqlite3"
    assert settings.asset_id == "forzy-motor-01"
    with pytest.raises(ValueError, match="DATABASE_URL"):
        settings.for_deploy()


def test_deploy_settings_keep_complete_ml_trust_anchors():
    settings = SettingsV2.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://example.invalid",
            "DATABASE_URL": "postgresql://twinops:secret@example.invalid/twinops",
            "TWINOPS_ML_ARTIFACT_PATH": "artifacts/ml/real-forzy",
            "TWINOPS_ML_MANIFEST_HASH": f"sha256:{'1' * 64}",
            "TWINOPS_ML_MODEL_HASH": f"sha256:{'2' * 64}",
        }
    )

    assert settings.for_deploy() is settings
    assert settings.ml_artifact_path == Path("artifacts/ml/real-forzy")
