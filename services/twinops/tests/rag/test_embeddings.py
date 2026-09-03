from unittest.mock import AsyncMock

import httpx
import pytest

from twinops.rag.embeddings import EmbeddingGatewayClient, EmbeddingGatewayError


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
