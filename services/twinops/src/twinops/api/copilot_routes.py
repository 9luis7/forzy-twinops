"""Thin HTTP boundary for evidence-bound explanations."""

from time import perf_counter

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated

from twinops.contracts.models import AssetConditionAssessment
from twinops.copilot.context import build_explanation_context
from twinops.copilot.deterministic import ExplanationResponse
from twinops.copilot.service import CopilotService


Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)

    question: Question
    asset_tag: str = Field(alias="assetTag", min_length=1)
    assessment: AssetConditionAssessment
    conversation_id: str | None = Field(default=None, alias="conversationId")


def create_copilot_router(service: CopilotService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])

    @router.post("/explain", response_model=ExplanationResponse)
    async def explain(request: ExplainRequest) -> ExplanationResponse:
        if request.asset_tag != request.assessment.asset_tag:
            raise HTTPException(
                status_code=422,
                detail="assetTag must match assessment.assetTag",
            )
        started = perf_counter()
        context = build_explanation_context(request.question, request.assessment)
        response = await service.explain(context)
        return response.model_copy(
            update={"latency_ms": (perf_counter() - started) * 1000}
        )

    return router
