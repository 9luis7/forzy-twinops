import asyncio

import pytest

from twinops.copilot.deterministic import ExplanationResponse
from twinops.copilot.service import CopilotService

from .test_deterministic import _assessment
from twinops.copilot.context import build_explanation_context


def _response(provider: str, refs: list[str] | None = None) -> ExplanationResponse:
    return ExplanationResponse(
        answer="Explicação limitada às evidências fornecidas.",
        evidenceRefs=refs if refs is not None else ["ev-1"],
        provider=provider,
        model="test-model",
        fallbackUsed=False,
        humanValidationRequired=True,
        limitations=[],
    )


class StubProvider:
    def __init__(self, *, response=None, error=None, delay=0):
        self.response = response
        self.error = error
        self.delay = delay

    async def explain(self, context):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.response


@pytest.mark.asyncio
async def test_local_failure_uses_enabled_external_provider():
    context = build_explanation_context("O que mudou?", _assessment())
    service = CopilotService(
        [
            StubProvider(error=TimeoutError()),
            StubProvider(response=_response("external")),
        ]
    )

    result = await service.explain(context)

    assert result.provider == "external"
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_all_provider_failures_use_deterministic():
    context = build_explanation_context("O que mudou?", _assessment())
    result = await CopilotService(
        [StubProvider(error=TimeoutError())]
    ).explain(context)

    assert result.provider == "deterministic"
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_provider_cannot_cite_unknown_evidence():
    context = build_explanation_context("O que mudou?", _assessment())
    result = await CopilotService(
        [StubProvider(response=_response("local", ["invented-ref"]))]
    ).explain(context)

    assert result.provider == "deterministic"
    assert result.evidence_refs == ["ev-1"]


@pytest.mark.asyncio
async def test_timeout_is_bounded_per_provider():
    context = build_explanation_context("O que mudou?", _assessment())
    result = await CopilotService(
        [StubProvider(response=_response("slow"), delay=0.1)],
        timeout_seconds=0.01,
    ).explain(context)

    assert result.provider == "deterministic"
