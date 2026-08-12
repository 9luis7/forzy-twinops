"""Deterministic explanation that remains available without an LLM."""

from pydantic import BaseModel, ConfigDict, Field

from .context import ExplanationContext


class ExplanationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    answer: str
    evidence_refs: list[str] = Field(alias="evidenceRefs")
    provider: str
    model: str | None = None
    latency_ms: float | None = Field(default=None, alias="latencyMs", ge=0)
    ttft_ms: float | None = Field(default=None, alias="ttftMs", ge=0)
    fallback_used: bool = Field(default=False, alias="fallbackUsed")
    human_validation_required: bool = Field(alias="humanValidationRequired")
    limitations: list[str]


def _format_evidence(context: ExplanationContext) -> str:
    if not context.assessment.evidence:
        return "Nenhuma evidência quantitativa válida está disponível nesta janela."

    return " ".join(
        f"{item.feature} = {item.value:g} {item.unit} (ref. {item.id})."
        for item in context.assessment.evidence
    )


def deterministic_explanation(context: ExplanationContext) -> ExplanationResponse:
    assessment = context.assessment
    evidence_refs = [
        item.id
        for item in assessment.evidence
        if item.id in context.allowed_evidence_refs
    ]

    if (
        assessment.quality.status == "insufficient_data"
        or assessment.assessment.status == "insufficient_data"
    ):
        answer = (
            "Os dados desta janela são insuficientes para interpretar a condição do ativo. "
            "É necessário recompor a janela e validar a aquisição antes de sugerir uma ação "
            "mecânica. "
            + _format_evidence(context)
        )
    else:
        answer = (
            f"A avaliação atual está em {assessment.assessment.status}, com qualidade "
            f"{assessment.quality.status}. {_format_evidence(context)} "
            "Os escores representam desvio relativo ao histórico observado; a conclusão "
            "requer validação humana."
        )

    limitations = list(assessment.limitations)
    limitations.append(
        "A explicação descreve evidências do assessment e não diagnostica causa raiz."
    )
    return ExplanationResponse(
        answer=answer,
        evidenceRefs=evidence_refs,
        provider="deterministic",
        model=None,
        fallbackUsed=False,
        humanValidationRequired=True,
        limitations=limitations,
    )
