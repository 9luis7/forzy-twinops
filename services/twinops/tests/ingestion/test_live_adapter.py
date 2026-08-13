from datetime import datetime, timezone
from pathlib import Path

import pytest

from twinops.config import Settings
from twinops.ingestion.live_adapter import InvalidSensorPayload, adapt_live_payload


SLOT = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
RECEIVED = datetime(2026, 8, 12, 15, 0, 1, tzinfo=timezone.utc)


def test_adapts_exact_s1_payload_and_preserves_zero_and_raw():
    raw = {"dados1": {"Velocidade": 0.04, "Aceleração": 0.0, "Temperatura": 34}}

    sample = adapt_live_payload(
        sensor_id="s1",
        payload=raw,
        scheduled_at=SLOT,
        received_at=RECEIVED,
        asset_tag="MTR-BMB-042",
    )
    body = sample.model_dump(mode="json", by_alias=True)

    assert body["source"] == "forzy-live"
    assert body["scheduledAt"] == "2026-08-12T15:00:00Z"
    assert body["observedAt"] is None
    assert body["receivedAt"] == "2026-08-12T15:00:01Z"
    assert body["measurements"]["vibrationVelocityRms"]["value"] == 0.04
    assert body["measurements"]["vibrationAcceleration"]["value"] == 0.0
    assert body["measurements"]["vibrationAcceleration"]["statistic"] == "unknown"
    assert body["raw"] == raw
    assert body["payloadHash"].startswith("sha256:")
    assert len(body["payloadHash"]) == 71
    assert body["provenance"] == {
        "sourceSystem": "forzy-api",
        "ingestedAt": body["receivedAt"],
    }


@pytest.mark.parametrize("bad", [None, "0.04", float("inf"), float("nan")])
def test_rejects_non_finite_or_non_numeric_velocity(bad):
    with pytest.raises(InvalidSensorPayload, match="Velocidade"):
        adapt_live_payload(
            sensor_id="s2",
            payload={
                "dados2": {
                    "Velocidade": bad,
                    "Aceleração": 0.0,
                    "Temperatura": 35,
                }
            },
            scheduled_at=SLOT,
            received_at=RECEIVED,
            asset_tag="MTR-BMB-042",
        )


def test_settings_are_server_side_and_validate_positive_intervals(tmp_path):
    settings = Settings.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://example.invalid/",
            "TWINOPS_DATABASE_PATH": str(tmp_path / "telemetry.db"),
            "TWINOPS_POLL_INTERVAL_SECONDS": "7.5",
        }
    )
    assert settings.upstream_base_url == "https://example.invalid"
    assert settings.database_path == tmp_path / "telemetry.db"
    assert settings.poll_interval_seconds == 7.5
    with pytest.raises(ValueError, match="positive"):
        Settings.from_env(
            {
                "TWINOPS_UPSTREAM_BASE_URL": "https://example.invalid",
                "TWINOPS_POLL_INTERVAL_SECONDS": "0",
            }
        )


@pytest.mark.parametrize("invalid", ["nan", "inf", "-inf"])
def test_settings_reject_non_finite_intervals(invalid):
    with pytest.raises(ValueError, match="finite"):
        Settings.from_env(
            {
                "TWINOPS_UPSTREAM_BASE_URL": "https://example.invalid",
                "TWINOPS_POLL_INTERVAL_SECONDS": invalid,
            }
        )


def test_rejects_gigantic_integer_as_invalid_sensor_payload():
    with pytest.raises(InvalidSensorPayload, match="Velocidade"):
        adapt_live_payload(
            sensor_id="s1",
            payload={
                "dados1": {
                    "Velocidade": 10**400,
                    "Aceleração": 0.0,
                    "Temperatura": 35,
                }
            },
            scheduled_at=SLOT,
            received_at=RECEIVED,
            asset_tag="MTR-BMB-042",
        )


def test_contract_validation_errors_are_translated_to_invalid_sensor_payload():
    with pytest.raises(InvalidSensorPayload, match="contract validation failed"):
        adapt_live_payload(
            sensor_id="s1",
            payload={
                "dados1": {
                    "Velocidade": 0.04,
                    "Aceleração": 0.0,
                    "Temperatura": 35,
                }
            },
            scheduled_at=SLOT,
            received_at=RECEIVED,
            asset_tag="",
        )


@pytest.mark.parametrize("timezone_name", ["Invalid/Nowhere", ""])
def test_settings_validate_timezone_during_startup(timezone_name):
    with pytest.raises(ValueError, match="TIMEZONE"):
        Settings.from_env(
            {
                "TWINOPS_UPSTREAM_BASE_URL": "https://example.invalid",
                "TWINOPS_TIMEZONE": timezone_name,
            }
        )


def test_settings_requires_complete_ml_trust_anchors():
    with pytest.raises(ValueError, match="ML artifact settings must be provided together"):
        Settings.from_env(
            {
                "TWINOPS_UPSTREAM_BASE_URL": "https://invalid.example",
                "TWINOPS_ML_ARTIFACT_PATH": "artifacts/ml/real-forzy",
            }
        )

    settings = Settings.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://invalid.example",
            "TWINOPS_ML_ARTIFACT_PATH": "artifacts/ml/real-forzy",
            "TWINOPS_ML_MANIFEST_HASH": f"sha256:{'1' * 64}",
            "TWINOPS_ML_MODEL_HASH": f"sha256:{'2' * 64}",
        }
    )

    assert settings.ml_artifact_path == Path("artifacts/ml/real-forzy")
