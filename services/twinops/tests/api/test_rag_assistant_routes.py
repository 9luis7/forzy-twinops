from datetime import datetime, timezone
import json
import time
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from twinops.config_v2 import SettingsV2
from twinops.main_v2 import create_app_v2
from twinops.rag.public_models import (
    AssistantAnswer,
    AssistantQueryResponse,
    ModelAnchors,
)
from twinops.rag.public_service import RagAssistantService
from twinops.rag.request_limits import MAX_ASSISTANT_REQUEST_BYTES
from twinops.rag.retrieval import CorpusUnavailableError


NOW = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)


class _Repository:
    def __init__(self, *, delay=0.0):
        self.delay = delay
        self.latest_calls = []
        self.history_calls = []

    def latest(self, asset_id):
        if self.delay:
            time.sleep(self.delay)
        self.latest_calls.append(asset_id)
        return []

    def history(self, query):
        if self.delay:
            time.sleep(self.delay)
        self.history_calls.append(query)
        return []

    def health(self, sensor_id):
        return None


class _Refresh:
    async def refresh(self, now):
        raise AssertionError("assistant must not refresh telemetry")


class _Assistant:
    def __init__(self, *, healthy=True, failure=None):
        self._healthy = healthy
        self.failure = failure
        self.calls = []
        self.health_calls = 0
        self.e2e_calls = 0

    def is_healthy(self, asset_id):
        self.health_calls += 1
        return self._healthy

    async def query(self, asset_id, request, *, operational):
        self.calls.append((asset_id, request, operational))
        if self.failure:
            raise self.failure
        return self._response()

    async def query_with_operational_loader(
        self,
        asset_id,
        request,
        *,
        operational_loader,
        started_at,
    ):
        self.e2e_calls += 1
        if not self._healthy:
            raise CorpusUnavailableError("corpus_incompatible")
        operational = await operational_loader()
        self.calls.append((asset_id, request, operational))
        if self.failure:
            raise self.failure
        return self._response()

    @staticmethod
    def _response():
        return AssistantQueryResponse(
            answer=AssistantAnswer(
                manual="Segundo o manual, use somente evidência citada.",
                currentState=(
                    "O assessment operacional atual está indisponível; não é "
                    "seguro inferir o estado do equipamento."
                ),
            ),
            groundingStatus="operational_unavailable",
            citations=[],
            corpus=None,
            models=ModelAnchors(
                embedding="embed-v1", generation="openai/gpt-5.6-luna"
            ),
            fallbackUsed=False,
            limitations=["Validação humana obrigatória."],
            humanValidationRequired=True,
            conversationId="00000000-0000-4000-8000-000000000001",
            traceId="00000000-0000-4000-8000-000000000002",
            latencyMs=1.2,
        )


class _UnavailableRetriever:
    def __init__(self, error):
        self.error = error
        self.prepare_calls = 0

    def healthy(self, asset_id):
        return False

    async def prepare(self, asset_id):
        self.prepare_calls += 1
        raise self.error

    async def retrieve(self, asset_id, question, *, corpus=None):
        raise AssertionError("refusal must precede retrieval")


class _NoChat:
    model = "openai/gpt-5.6-luna"

    async def generate(self, messages):
        raise AssertionError("refusal must precede Gateway")


def _client(
    *,
    enabled=True,
    assistant=None,
    environment="production",
    api_key="server-only-secret",
    repository=None,
):
    repository = repository or _Repository()
    settings = SettingsV2(
        upstream_base_url="https://upstream.invalid",
        vercel_environment=environment,
        rag_enabled=enabled,
        ai_gateway_api_key=api_key,
        rag_manufacturer="WEG",
        rag_equipment_model="W22",
    )
    app = create_app_v2(
        repository=repository,
        settings=settings,
        refresh_service=_Refresh(),
        assessment_scorer=None,
        clock=lambda: NOW,
        rag_assistant_service=assistant,
    )
    return TestClient(app), repository


def test_public_assistant_route_works_in_production_and_uses_server_snapshot():
    assistant = _Assistant()
    client, repository = _client(assistant=assistant, environment="production")

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        json={"question": "Qual é o estado atual?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["groundingStatus"] == "operational_unavailable"
    UUID(body["conversationId"])
    UUID(body["traceId"])
    assert assistant.calls[0][2].available is False
    assert repository.latest_calls
    assert repository.history_calls


def test_browser_cannot_submit_assessment_telemetry_corpus_or_citations():
    assistant = _Assistant()
    client, _ = _client(assistant=assistant)

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        json={
            "question": "estado",
            "assessment": {"status": "alert"},
            "telemetry": [],
            "corpus": "attacker",
            "citations": [],
        },
    )

    assert response.status_code == 422
    assert assistant.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": "x" * 501},
        {
            "question": "ok",
            "history": [{"question": "q", "answer": "a"} for _ in range(5)],
        },
    ],
)
def test_invalid_question_and_history_are_422_before_service(payload):
    assistant = _Assistant()
    client, _ = _client(assistant=assistant)

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query", json=payload
    )

    assert response.status_code == 422
    assert assistant.calls == []


def test_wrong_asset_is_404_without_assistant_or_snapshot_work():
    assistant = _Assistant()
    client, repository = _client(assistant=assistant)

    response = client.post(
        "/api/v2/assets/other/assistant/query", json={"question": "estado"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "asset_not_found"}
    assert assistant.calls == []
    assert repository.latest_calls == []


@pytest.mark.parametrize(
    ("enabled", "assistant"),
    [(False, _Assistant()), (True, None), (True, _Assistant(healthy=False))],
)
def test_disabled_or_unhealthy_assistant_returns_sanitized_503(enabled, assistant):
    client, _ = _client(enabled=enabled, assistant=assistant)

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        json={"question": "estado"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "rag_unavailable"}
    assert "secret" not in response.text


def test_missing_active_corpus_maps_to_sanitized_503():
    assistant = _Assistant(
        failure=CorpusUnavailableError("private active corpus details")
    )
    client, _ = _client(assistant=assistant)

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        json={"question": "estado"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "rag_unavailable"}
    assert "private" not in response.text


def test_enabled_flag_without_backend_gateway_key_is_unavailable():
    assistant = _Assistant(healthy=True)
    client, _ = _client(enabled=True, assistant=assistant, api_key=None)

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        json={"question": "estado"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "rag_unavailable"}
    assert assistant.calls == []


def test_snapshot_capability_requires_flag_service_health_and_active_compatibility():
    healthy_client, _ = _client(enabled=True, assistant=_Assistant(healthy=True))
    unhealthy_client, _ = _client(enabled=True, assistant=_Assistant(healthy=False))
    disabled_client, _ = _client(enabled=False, assistant=_Assistant(healthy=True))

    healthy = healthy_client.get("/api/v2/assets/forzy-motor-01/snapshot")
    unhealthy = unhealthy_client.get("/api/v2/assets/forzy-motor-01/snapshot")
    disabled = disabled_client.get("/api/v2/assets/forzy-motor-01/snapshot")

    assert healthy.json()["capabilities"]["copilot"] is True
    assert unhealthy.json()["capabilities"]["copilot"] is False
    assert disabled.json()["capabilities"]["copilot"] is False


def test_identity_mismatch_keeps_capability_false_and_public_query_is_sanitized():
    assistant = _Assistant(healthy=False)
    client, _ = _client(assistant=assistant)

    snapshot = client.get("/api/v2/assets/forzy-motor-01/snapshot")
    query = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        json={"question": "bearing"},
    )

    assert snapshot.json()["capabilities"]["copilot"] is False
    assert query.status_code == 503
    assert query.json() == {"detail": "rag_unavailable"}


@pytest.mark.parametrize(
    "error",
    [
        CorpusUnavailableError("active_corpus_unavailable"),
        CorpusUnavailableError("corpus_incompatible"),
    ],
)
def test_public_post_refuses_prohibited_intent_before_missing_or_wrong_corpus(error):
    retriever = _UnavailableRetriever(error)
    service = RagAssistantService(retriever, _NoChat(), query_timeout_seconds=1)
    client, repository = _client(assistant=service)

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        json={"question": "Identifique o motivo determinante da vibração."},
    )

    assert response.status_code == 200
    assert response.json()["groundingStatus"] == "out_of_scope"
    assert response.json()["citations"] == []
    assert retriever.prepare_calls == 0
    assert repository.latest_calls == []
    assert repository.history_calls == []


def test_public_post_refusal_does_not_require_enabled_rag_or_gateway_service():
    client, repository = _client(
        enabled=False,
        assistant=None,
        api_key=None,
    )

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        json={"question": "Há 82% de possibilidade de o motor parar."},
    )

    assert response.status_code == 200
    assert response.json()["groundingStatus"] == "out_of_scope"
    assert response.json()["citations"] == []
    assert repository.latest_calls == []
    assert repository.history_calls == []


def test_public_post_uses_one_async_preflight_and_reports_latency_from_route_entry():
    assistant = _Assistant()
    repository = _Repository(delay=0.02)
    client, _ = _client(assistant=assistant, repository=repository)

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        json={"question": "bearing"},
    )

    assert response.status_code == 200
    assert assistant.health_calls == 0
    assert assistant.e2e_calls == 1
    assert response.json()["latencyMs"] >= 35


def test_public_post_rejects_oversized_body_before_json_parser_without_echo():
    secret = "sensitive-request-body" * (MAX_ASSISTANT_REQUEST_BYTES // 10)
    client, _ = _client(assistant=_Assistant())

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        json={"question": "bearing", "unexpected": secret},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "assistant_request_too_large"}
    assert secret[:100] not in response.text


@pytest.mark.parametrize("ensure_ascii", [False, True])
def test_largest_valid_multibyte_and_escaped_requests_fit_the_byte_cap(ensure_ascii):
    client, _ = _client(assistant=_Assistant())
    payload = {
        "question": "😀" * 500,
        "history": [
            {"question": "😀" * 500, "answer": "😀" * 6000}
            for _ in range(4)
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=ensure_ascii).encode("utf-8")

    response = client.post(
        "/api/v2/assets/forzy-motor-01/assistant/query",
        content=encoded,
        headers={"content-type": "application/json"},
    )

    assert len(encoded) <= MAX_ASSISTANT_REQUEST_BYTES
    assert response.status_code == 200
