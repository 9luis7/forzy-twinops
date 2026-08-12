"""Build the smallest trusted context an explanation provider may use."""

from dataclasses import dataclass

from twinops.contracts.models import AssetConditionAssessment


@dataclass(frozen=True, slots=True)
class ExplanationContext:
    question: str
    assessment: AssetConditionAssessment
    allowed_evidence_refs: frozenset[str]


def build_explanation_context(
    question: str, assessment: AssetConditionAssessment
) -> ExplanationContext:
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must not be blank")

    return ExplanationContext(
        question=normalized_question,
        assessment=assessment,
        allowed_evidence_refs=frozenset(item.id for item in assessment.evidence),
    )
