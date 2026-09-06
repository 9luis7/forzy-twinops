from unittest.mock import AsyncMock
import logging

import httpx
import pytest

from twinops.rag import embeddings as embeddings_module
from twinops.rag.embeddings import EmbeddingGatewayClient, EmbeddingGatewayError
from twinops import main_v2
from twinops.config_v2 import SettingsV2


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_gateway_uses_openai_compatible_embeddings_contract_without_logging(caplog):
    http = AsyncMock()
    http.post.return_value = _Response(
        {"data": [{"index": 1, "embedding": [0.3, 0.4]}, {"index": 0, "embedding": [0.1, 0.2]}]}
    )
    client = EmbeddingGatewayClient(
        http,
        api_key="top-secret",
        model="google/text-multilingual-embedding-002",
        dimensions=2,
        timeout_seconds=3.0,
    )

    result = await client.embed(["private first", "private second"])

    assert result == ((0.1, 0.2), (0.3, 0.4))
    args, kwargs = http.post.await_args
    assert args[0].endswith("/embeddings")
    assert kwargs["headers"]["Authorization"] == "Bearer top-secret"
    assert kwargs["json"]["model"] == "google/text-multilingual-embedding-002"
    assert kwargs["json"]["dimensions"] == 2
    assert kwargs["timeout"] == 3.0
    assert "private first" not in caplog.text
    assert "top-secret" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"index": 0, "embedding": [0.1]}]},
        {"data": [{"index": 1, "embedding": [0.1, 0.2]}]},
        {"data": [{"index": 0, "embedding": [float("nan"), 0.2]}]},
    ],
)
async def test_gateway_rejects_malformed_or_wrong_dimension_payload(payload):
    http = AsyncMock()
    http.post.return_value = _Response(payload)
    client = EmbeddingGatewayClient(
        http, api_key="secret", model="embed-v1", dimensions=2
    )

    with pytest.raises(EmbeddingGatewayError):
        await client.embed(["text"])


@pytest.mark.asyncio
async def test_gateway_sanitizes_transport_failure():
    http = AsyncMock()
    http.post.side_effect = httpx.TimeoutException("private payload timed out")
    client = EmbeddingGatewayClient(
        http, api_key="secret", model="embed-v1", dimensions=2
    )

    with pytest.raises(EmbeddingGatewayError) as caught:
        await client.embed(["private payload"])

    assert str(caught.value) == "embedding_gateway_unavailable"


@pytest.mark.asyncio
async def test_gemini_uses_native_batch_contract_with_fixed_dimension_and_task_type(
    caplog,
):
    client_type = getattr(embeddings_module, "GeminiEmbeddingClient", None)
    assert client_type is not None, "direct Gemini embedding client is missing"
    http = AsyncMock()
    http.post.return_value = _Response(
        {"embeddings": [{"values": [0.1, 0.2]}, {"values": [0.3, 0.4]}]}
    )
    client = client_type(
        http,
        api_key="gemini-secret",
        model="gemini-embedding-2",
        dimensions=2,
        task_type="RETRIEVAL_DOCUMENT",
        timeout_seconds=4.0,
    )

    result = await client.embed(["private first", "private second"])

    assert result == ((0.1, 0.2), (0.3, 0.4))
    args, kwargs = http.post.await_args
    assert args[0] == (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-embedding-2:batchEmbedContents"
    )
    assert kwargs["headers"] == {
        "x-goog-api-key": "gemini-secret",
        "Content-Type": "application/json",
    }
    assert kwargs["json"] == {
        "requests": [
            {
                "model": "models/gemini-embedding-2",
                "content": {"parts": [{"text": "private first"}]},
                "embedContentConfig": {
                    "outputDimensionality": 2,
                    "taskType": "RETRIEVAL_DOCUMENT",
                },
            },
            {
                "model": "models/gemini-embedding-2",
                "content": {"parts": [{"text": "private second"}]},
                "embedContentConfig": {
                    "outputDimensionality": 2,
                    "taskType": "RETRIEVAL_DOCUMENT",
                },
            },
        ]
    }
    assert kwargs["timeout"] == 4.0
    assert "private first" not in caplog.text
    assert "gemini-secret" not in caplog.text


@pytest.mark.asyncio
async def test_gemini_composition_separates_document_and_query_embedding_tasks():
    builder = getattr(main_v2, "_build_embedding_clients", None)
    assert builder is not None, "RAG embedding client composition is missing"
    http = AsyncMock()
    http.post.side_effect = [
        _Response({"embeddings": [{"values": [0.1, 0.2]}]}),
        _Response({"embeddings": [{"values": [0.3, 0.4]}]}),
    ]
    settings = SettingsV2.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "TWINOPS_RAG_PROVIDER": "gemini",
            "GEMINI_API_KEY": "gemini-secret",
            "TWINOPS_RAG_EMBEDDING_DIMENSIONS": "2",
        }
    )

    document_client, query_client = builder(http, settings)
    assert document_client is not None
    assert query_client is not None
    await document_client.embed(["manual text"])
    await query_client.embed(["operator question"])

    first = http.post.await_args_list[0].kwargs["json"]["requests"][0]
    second = http.post.await_args_list[1].kwargs["json"]["requests"][0]
    assert first["embedContentConfig"]["taskType"] == "RETRIEVAL_DOCUMENT"
    assert second["embedContentConfig"]["taskType"] == "RETRIEVAL_QUERY"


@pytest.mark.asyncio
async def test_gemini_logs_only_sanitized_http_status_on_provider_failure(caplog):
    http = AsyncMock()
    request = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-embedding-2:batchEmbedContents",
    )
    http.post.return_value = httpx.Response(
        429,
        request=request,
        json={"error": {"message": "private provider detail"}},
    )
    client = embeddings_module.GeminiEmbeddingClient(
        http,
        api_key="gemini-secret",
        model="gemini-embedding-2",
        dimensions=2,
        task_type="RETRIEVAL_DOCUMENT",
        max_rate_limit_retries=0,
    )

    with caplog.at_level(logging.WARNING, logger="twinops.rag"):
        with pytest.raises(EmbeddingGatewayError) as caught:
            await client.embed(["private manual text"])

    assert str(caught.value) == "embedding_gateway_unavailable"
    assert "gemini_embedding_failed status_code=429" in caplog.text
    assert "gemini-secret" not in caplog.text
    assert "private manual text" not in caplog.text
    assert "private provider detail" not in caplog.text


@pytest.mark.asyncio
async def test_gemini_retries_one_rate_limited_batch_after_sanitized_delay(
    monkeypatch,
    caplog,
):
    http = AsyncMock()
    request = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-embedding-2:batchEmbedContents",
    )
    http.post.side_effect = [
        httpx.Response(429, request=request, json={"error": {"message": "private"}}),
        _Response({"embeddings": [{"values": [0.1, 0.2]}]}),
    ]
    sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep)
    client = embeddings_module.GeminiEmbeddingClient(
        http,
        api_key="gemini-secret",
        model="gemini-embedding-2",
        dimensions=2,
        task_type="RETRIEVAL_DOCUMENT",
        max_rate_limit_retries=1,
        rate_limit_retry_seconds=61.0,
    )

    with caplog.at_level(logging.WARNING, logger="twinops.rag"):
        result = await client.embed(["private manual text"])

    assert result == ((0.1, 0.2),)
    assert http.post.await_count == 2
    sleep.assert_awaited_once_with(61.0)
    assert "gemini_embedding_rate_limited retry=1" in caplog.text
    assert "gemini-secret" not in caplog.text
    assert "private manual text" not in caplog.text
    assert "private" not in caplog.text
