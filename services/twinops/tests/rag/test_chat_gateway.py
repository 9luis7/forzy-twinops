import asyncio
import json
import logging

import httpx
import pytest

from twinops import main_v2
from twinops.config_v2 import SettingsV2
from twinops.rag import generation as generation_module
from twinops.rag.generation import ChatGatewayClient, ChatGatewayError


class _Response:
    def __init__(self, payload, *, failure=None, status_code=200):
        self.payload = payload
        self.failure = failure
        self.status_code = status_code

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
async def test_chat_gateway_requests_minimal_reasoning_for_flash_lite_latency():
    http = _Http(
        _Response({"choices": [{"message": {"content": _content()}}]})
    )
    client = ChatGatewayClient(
        http,
        api_key="server-secret",
        model="gemini-3.5-flash-lite",
    )

    await client.generate([{"role": "system", "content": "policy"}])

    _, kwargs = http.calls[0]
    assert kwargs["json"]["reasoning_effort"] == "minimal"
    assert "temperature" not in kwargs["json"]


@pytest.mark.asyncio
async def test_native_gemini_chat_uses_fixed_schema_and_minimal_thinking():
    client_type = getattr(generation_module, "GeminiChatClient", None)
    assert client_type is not None, "native Gemini chat client is missing"
    http = _Http(
        _Response(
            {
                "candidates": [
                    {"content": {"parts": [{"text": _content()}]}}
                ]
            }
        )
    )
    client = client_type(
        http,
        api_key="server-secret",
        model="gemini-3.5-flash-lite",
        timeout_seconds=7,
    )

    result = await client.generate(
        [
            {"role": "system", "content": "fixed policy"},
            {"role": "user", "content": "fixed evidence"},
        ]
    )

    url, kwargs = http.calls[0]
    assert url == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.5-flash-lite:generateContent"
    )
    assert kwargs["headers"]["x-goog-api-key"] == "server-secret"
    assert kwargs["json"]["systemInstruction"] == {
        "parts": [{"text": "fixed policy"}]
    }
    assert kwargs["json"]["contents"] == [
        {"role": "user", "parts": [{"text": "fixed evidence"}]}
    ]
    config = kwargs["json"]["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingLevel": "MINIMAL"}
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"]["additionalProperties"] is False
    assert "responseFormat" not in config
    assert config["maxOutputTokens"] == 1200
    assert kwargs["timeout"] == 7
    assert result.manual_citations[0].chunk_id == "chunk-1"


@pytest.mark.asyncio
async def test_native_gemini_25_flash_lite_disables_thinking_by_budget():
    http = _Http(
        _Response(
            {
                "candidates": [
                    {"content": {"parts": [{"text": _content()}]}}
                ]
            }
        )
    )
    client = generation_module.GeminiChatClient(
        http,
        api_key="server-secret",
        model="gemini-2.5-flash-lite",
    )

    await client.generate(
        [
            {"role": "system", "content": "fixed policy"},
            {"role": "user", "content": "fixed evidence"},
        ]
    )

    _, kwargs = http.calls[0]
    assert kwargs["json"]["generationConfig"]["thinkingConfig"] == {
        "thinkingBudget": 0
    }


def test_chat_composition_selects_native_gemini_and_preserves_gateway_client():
    builder = getattr(main_v2, "_build_chat_client", None)
    assert builder is not None, "RAG chat client composition is missing"
    http = _Http(_Response({}))
    gemini = SettingsV2.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "TWINOPS_RAG_PROVIDER": "gemini",
            "GEMINI_API_KEY": "gemini-secret",
        }
    )
    gateway = SettingsV2.from_env(
        {
            "TWINOPS_UPSTREAM_BASE_URL": "https://upstream.invalid",
            "AI_GATEWAY_API_KEY": "gateway-secret",
        }
    )

    gemini_client = builder(http, gemini)
    gateway_client = builder(http, gateway)

    assert isinstance(gemini_client, generation_module.GeminiChatClient)
    assert isinstance(gateway_client, ChatGatewayClient)


@pytest.mark.asyncio
async def test_chat_gateway_propagates_cancellation_without_logging_content(caplog):
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
@pytest.mark.parametrize(
    ("response", "reason", "status_code"),
    [
        (
            _Response(
                {},
                failure=httpx.ReadTimeout("private timeout detail"),
            ),
            "timeout",
            None,
        ),
        (
            _Response(
                {},
                failure=httpx.HTTPStatusError(
                    "private body",
                    request=httpx.Request("POST", "https://provider.invalid"),
                    response=httpx.Response(503),
                ),
                status_code=503,
            ),
            "http_status",
            503,
        ),
        (
            _Response(
                {},
                failure=httpx.ConnectError("private transport detail"),
            ),
            "transport",
            None,
        ),
        (_Response({"choices": []}), "invalid_response", None),
    ],
)
async def test_chat_gateway_preserves_only_sanitized_internal_failure_category(
    response, reason, status_code
):
    client = ChatGatewayClient(
        _Http(response), api_key="server-secret", model="gemini-3.7-flash"
    )

    with pytest.raises(ChatGatewayError) as captured:
        await client.generate([{"role": "user", "content": "private prompt"}])

    assert str(captured.value) == "generation_gateway_unavailable"
    assert captured.value.reason == reason
    assert captured.value.status_code == status_code
    assert "private" not in repr(captured.value)


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
