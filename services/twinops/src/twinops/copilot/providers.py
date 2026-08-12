"""Optional OpenAI-compatible explanation providers configured server-side."""

import json
import os
from typing import Protocol

import httpx

from .context import ExplanationContext
from .deterministic import ExplanationResponse


class ExplanationProvider(Protocol):
    async def explain(self, context: ExplanationContext) -> ExplanationResponse: ...


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        provider_name: str,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip():
            raise ValueError("provider base_url and model are required")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider_name = provider_name
        self.api_key = api_key
        self.client = client

    async def explain(self, context: ExplanationContext) -> ExplanationResponse:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        assessment = context.assessment.model_dump(by_alias=True, mode="json")
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Explique somente o assessment fornecido. Não recalcule escores, "
                        "não diagnostique causa raiz e cite apenas ids presentes em evidence. "
                        "Responda JSON com answer, evidenceRefs e limitations."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"question": context.question, "assessment": assessment},
                        ensure_ascii=False,
                    ),
                },
            ],
        }

        if self.client is not None:
            response = await self.client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return ExplanationResponse(
            answer=parsed["answer"],
            evidenceRefs=parsed.get("evidenceRefs", []),
            provider=self.provider_name,
            model=self.model,
            fallbackUsed=False,
            humanValidationRequired=True,
            limitations=parsed.get("limitations", []),
        )


def build_configured_providers(
    environ: dict[str, str] | None = None,
) -> list[ExplanationProvider]:
    env = os.environ if environ is None else environ
    providers: list[ExplanationProvider] = []

    local_url = env.get("LOCAL_LLM_BASE_URL")
    local_model = env.get("LOCAL_LLM_MODEL")
    if local_url and local_model:
        providers.append(
            OpenAICompatibleProvider(
                base_url=local_url,
                model=local_model,
                provider_name="local",
                api_key=env.get("LOCAL_LLM_API_KEY"),
            )
        )

    if env.get("EXTERNAL_LLM_ENABLED", "false").lower() == "true":
        external_url = env.get("EXTERNAL_LLM_BASE_URL")
        external_model = env.get("EXTERNAL_LLM_MODEL")
        if external_url and external_model:
            providers.append(
                OpenAICompatibleProvider(
                    base_url=external_url,
                    model=external_model,
                    provider_name="external",
                    api_key=env.get("EXTERNAL_LLM_API_KEY"),
                )
            )
    return providers
