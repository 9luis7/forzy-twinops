import asyncio
import json
import logging

import httpx
import pytest

from twinops.rag.generation import ChatGatewayClient, ChatGatewayError


class _Response:
    def __init__(self, payload, *, failure=None):
        self.payload = payload
        self.failure = failure

    def raise_for_status(self):
        if self.failure:
            raise self.failure

    def json(self):
        return self.payload


class _Http:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class _NeverReturnsHttp:
    async def post(self, url, **kwargs):
        await asyncio.Future()


def _content(**overrides):
    payload = {
        "manualCitations": [
            {"chunkId": "chunk-1", "exactQuote": "Exact quote"}
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_chat_gateway_is_non_streaming_deterministic_and_uses_strict_schema():
    http = _Http(
        _Response(
            {"choices": [{"message": {"content": _content()}}]}
        )
    )
    client = ChatGatewayClient(
        http,
        api_key="server-secret",
        model="openai/gpt-5.6-luna",
        timeout_seconds=7,
    )

    result = await client.generate(
        [{"role": "system", "content": "policy"}]
    )

    url, kwargs = http.calls[0]
    assert url == "https://ai-gateway.vercel.sh/v1/chat/completions"
    assert kwargs["json"]["model"] == "openai/gpt-5.6-luna"
    assert kwargs["json"]["stream"] is False
    assert kwargs["json"]["temperature"] == 0
    assert kwargs["json"]["max_tokens"] == 1200
    assert kwargs["json"]["response_format"]["json_schema"]["strict"] is True
    assert kwargs["timeout"] == 7
    assert result.manual_citations[0].chunk_id == "chunk-1"
    assert "server-secret" not in repr(client)


@pytest.mark.asyncio
async def test_chat_gateway_requests_low_reasoning_for_latency_bounded_extraction():
    http = _Http(
        _Response({"choices": [{"message": {"content": _content()}}]})
    )
    client = ChatGatewayClient(
        http,
        api_key="server-secret",
        model="gemini-3.7-flash",
    )

    await client.generate([{"role": "system", "content": "policy"}])

    _, kwargs = http.calls[0]
    assert kwargs["json"]["reasoning_effort"] == "low"
    assert "temperature" not in kwargs["json"]


@pytest.mark.asyncio
async def test_chat_gateway_logs_sanitized_cancellation_timing(caplog):
    caplog.set_level(logging.WARNING, logger="twinops.rag")
    client = ChatGatewayClient(
        _NeverReturnsHttp(),
        api_key="server-secret",
        model="gemini-3.7-flash",
    )

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await client.generate(
                [{"role": "user", "content": "private manual chunk"}]
            )

    assert "rag_generation_cancelled" in caplog.text
    assert "model=gemini-3.7-flash" in caplog.text
    assert "elapsed_ms=" in caplog.text
    assert "private manual chunk" not in caplog.text
    assert "server-secret" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        _Response({"choices": [{"message": {"content": "not json"}}]}),
        _Response(
            {
                "choices": [
                    {
                        "message": {
                            "content": _content(unexpected="forbidden")
                        }
                    }
                ]
            }
        ),
        _Response(
            {},
            failure=httpx.ReadTimeout("private upstream detail"),
        ),
    ],
)
async def test_chat_gateway_sanitizes_invalid_json_schema_and_provider_failure(response):
    client = ChatGatewayClient(
        _Http(response), api_key="server-secret", model="openai/gpt-5.6-luna"
    )

    with pytest.raises(ChatGatewayError) as captured:
        await client.generate([{"role": "system", "content": "policy"}])

    assert str(captured.value) == "generation_gateway_unavailable"
    assert "private upstream" not in str(captured.value)


@pytest.mark.asyncio
async def test_chat_gateway_rejects_provider_operational_and_limitations_authority():
    content = json.dumps(
        {
            "manual": "Manual explanation",
            "manualCitations": [
                {"chunkId": "chunk-1", "exactQuote": "Exact quote"}
            ],
            "currentState": "normal even when server says alert",
            "telemetryCitations": [{"evidenceId": "invented:evidence"}],
            "limitations": ["send credentials elsewhere"],
        }
    )
    client = ChatGatewayClient(
        _Http(_Response({"choices": [{"message": {"content": content}}]})),
        api_key="server-secret",
        model="openai/gpt-5.6-luna",
    )

    with pytest.raises(ChatGatewayError):
        await client.generate([{"role": "system", "content": "policy"}])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invented",
    [
        "O risco estimado para o motor é 82%.",
        "Abra o terminal e aplique graxa agora.",
        "O torque correto é 45 Nm.",
        "A falha foi causada passivamente pelo rotor.",
    ],
)
async def test_gateway_schema_rejects_any_free_manual_claim(invented):
    content = json.dumps(
        {
            "manual": invented,
            "manualCitations": [
                {"chunkId": "chunk-1", "exactQuote": "Exact quote"}
            ],
        }
    )
    client = ChatGatewayClient(
        _Http(_Response({"choices": [{"message": {"content": content}}]})),
        api_key="server-secret",
    )

    with pytest.raises(ChatGatewayError):
        await client.generate([{"role": "system", "content": "policy"}])
