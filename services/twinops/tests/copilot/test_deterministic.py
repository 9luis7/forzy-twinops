from twinops.contracts.models import AssetConditionAssessment
from twinops.copilot.context import build_explanation_context
from twinops.copilot.deterministic import deterministic_explanation


def _assessment(*, status: str = "watch", quality: str = "ok") -> AssetConditionAssessment:
    return AssetConditionAssessment.model_validate(
        {
            "schemaVersion": "1.0",
            "assessmentId": "123e4567-e89b-42d3-a456-426614174000",
            "assetTag": "MOTOR-01",
            "sensorId": "s1",
            "window": {
                "start": "2026-08-12T15:00:00Z",
                "end": "2026-08-12T15:01:00Z",
                "receivedAt": "2026-08-12T15:01:01Z",
                "freshnessMs": 1000.0,
            },
            "quality": {"status": quality, "flags": []},
            "operatingContext": {"state": "steady", "estimated": True},
            "assessment": {
                "status": status,
                "anomalyScore": 0.72,
                "deteriorationScore": 0.41,
                "scoreSemantics": "relative_to_historical_baseline_not_failure_probability",
                "episodeId": "episode-7",
                "persistenceSeconds": 45.0,
            },
            "componentTag": None,
            "recommendation": "Inspecionar a tendência de vibração.",
            "humanValidationRequired": True,
            "evidence": [
                {
                    "id": "ev-1",
                    "feature": "velocity_rms_ewma",
                    "value": 0.08,
                    "unit": "mm/s",
                    "baseline": 0.04,
                    "deviation": 0.04,
                    "direction": "up",
                    "windowSeconds": 60.0,
                }
            ],
            "model": {
                "name": "robust-baseline",
                "version": "0.1.0",
                "configHash": "sha256:" + "a" * 64,
                "trainedUntil": "2026-08-11T15:00:00Z",
            },
            "limitations": ["Sem rótulos de falha confirmados."],
        }
    )


def test_deterministic_response_only_cites_known_evidence():
    context = build_explanation_context("O que mudou?", _assessment())

    response = deterministic_explanation(context)

    assert response.evidence_refs == ["ev-1"]
    assert response.provider == "deterministic"
    assert "probabilidade de falha" not in response.answer.lower()
    assert "velocity_rms_ewma" in response.answer


def test_insufficient_data_requests_data_recovery_without_mechanical_action():
    context = build_explanation_context(
        "O que devo fazer?",
        _assessment(status="insufficient_data", quality="insufficient_data"),
    )

    response = deterministic_explanation(context)

    assert "recompor a janela" in response.answer.lower()
    assert "validar a aquisição" in response.answer.lower()
    assert "inspecionar" not in response.answer.lower()
    assert response.human_validation_required is True


def test_question_must_not_be_blank():
    try:
        build_explanation_context("   ", _assessment())
    except ValueError as error:
        assert "question" in str(error)
    else:
        raise AssertionError("blank question should be rejected")
