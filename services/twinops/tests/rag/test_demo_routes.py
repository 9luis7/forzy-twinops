from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from twinops.rag.demo_routes import create_demo_rag_router
from twinops.rag.request_limits import MAX_ASSISTANT_REQUEST_BYTES
from .test_demo_service import service


@pytest.fixture
def client():
    app = FastAPI()
    app.state.demo_assistant_service = service()
    app.include_router(create_demo_rag_router())
    return TestClient(app)


URL = "/api/demo/v1/runs/run/assistant/query"
AUTH = {"Authorization": "Bearer secret"}


def test_http_contract_no_store_and_validated_citations(client):
    response = client.post(URL, headers=AUTH, json={"question": "rolamentos", "contextRevision": 8})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"contextRevision", "sourceRow", "observedAt", "response"}
    assert response.json()["response"]["citations"][0]["type"] == "manual"


@pytest.mark.parametrize("fields", [{}, {"contextRevision": 1}, {"contextRevision": 9}])
def test_missing_and_stale_revision_captures_newest_server_context(client, fields):
    response = client.post(URL, headers=AUTH, json={"question": "estado", **fields})
    assert response.status_code == 200
    assert response.json()["contextRevision"] == 8
    assert response.json()["sourceRow"] == 150
    assert response.json()["response"]["generation"]["status"] == "generated"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("field", ["measurements", "operational", "assessment", "assetId"])
def test_client_cannot_inject_operational_context(client, field):
    response = client.post(URL, headers=AUTH, json={"question": "estado", "contextRevision": 8, field: {}})
    assert response.status_code == 422


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer bad"}])
def test_auth_does_not_expose_run(client, headers):
    response = client.post(URL, headers=headers, json={"question": "estado", "contextRevision": 8})
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"


def test_request_size_is_bounded_before_parsing_including_stream(client):
    for content in (b"x" * (MAX_ASSISTANT_REQUEST_BYTES + 1),
                    (b"x" * 4096 for _ in range(MAX_ASSISTANT_REQUEST_BYTES // 4096 + 2))):
        response = client.post(URL, headers=AUTH, content=content)
        assert response.status_code == 413
        assert response.headers["cache-control"] == "no-store"


def test_question_and_history_bounds(client):
    response = client.post(URL, headers=AUTH, json={"question": "x" * 501, "contextRevision": 8})
    assert response.status_code == 422
    response = client.post(URL, headers=AUTH, json={"question": "estado", "contextRevision": 8,
                                                   "history": [{"question": "q", "answer": "a"}] * 5})
    assert response.status_code == 422


def test_recommendation_requires_empty_object_and_returns_terminal_event(client):
    url = "/api/demo/v1/runs/run/events/event-1/recommendation"
    assert client.post(url, headers=AUTH, json={"measurements": {}}).status_code == 422
    response = client.post(url, headers=AUTH, json={})
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert client.post(url, headers=AUTH, json={}).json() == response.json()
