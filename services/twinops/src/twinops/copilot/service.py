"""Ordered provider fallback with evidence validation."""

import asyncio
from collections.abc import Callable, Sequence

from .context import ExplanationContext
from .deterministic import ExplanationResponse, deterministic_explanation
from .providers import ExplanationProvider


class CopilotService:
    def __init__(
        self,
        providers: Sequence[ExplanationProvider],
        deterministic: Callable[
            [ExplanationContext], ExplanationResponse
        ] = deterministic_explanation,
        *,
        timeout_seconds: float = 8.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.providers = tuple(providers)
        self.deterministic = deterministic
        self.timeout_seconds = timeout_seconds

    async def explain(self, context: ExplanationContext) -> ExplanationResponse:
        had_failure = False
        for provider in self.providers:
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    response = await provider.explain(context)
                if not set(response.evidence_refs).issubset(
                    context.allowed_evidence_refs
                ):
                    raise ValueError("provider cited unknown evidence")
                if had_failure:
                    response = response.model_copy(update={"fallback_used": True})
                return response
            except (Exception, asyncio.CancelledError) as error:
                if isinstance(error, asyncio.CancelledError):
                    raise
                had_failure = True

        fallback = self.deterministic(context)
        return fallback.model_copy(
            update={"fallback_used": bool(self.providers) or had_failure}
        )
