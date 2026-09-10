"""Strict public HTTP contract for the asset-aware technical assistant."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


MAX_QUESTION_CHARACTERS = 500
MAX_HISTORY_ANSWER_CHARACTERS = 6_000
MAX_HISTORY_TURNS = 4

TrimmedQuestion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_QUESTION_CHARACTERS,
    ),
]
BoundedAnswer = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_HISTORY_ANSWER_CHARACTERS,
    ),
]


class _PublicModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class ConversationTurn(_PublicModel):
    question: TrimmedQuestion
    answer: BoundedAnswer


class AssistantQueryRequest(_PublicModel):
    question: TrimmedQuestion
    conversation_id: UUID | None = Field(default=None, alias="conversationId")
    history: list[ConversationTurn] = Field(
        default_factory=list,
        max_length=MAX_HISTORY_TURNS,
    )


class AssistantAnswer(_PublicModel):
    manual: BoundedAnswer
    current_state: BoundedAnswer = Field(alias="currentState")


class ManualCitation(_PublicModel):
    type: Literal["manual"] = "manual"
    chunk_id: str = Field(alias="chunkId", min_length=1)
    document_id: str = Field(alias="documentId", min_length=1)
    manufacturer: str = Field(min_length=1)
    equipment_model: str = Field(alias="equipmentModel", min_length=1)
    revision: str = Field(min_length=1)
    source_url: str = Field(alias="sourceUrl", min_length=1)
    page_start: int = Field(alias="pageStart", ge=1)
    page_end: int = Field(alias="pageEnd", ge=1)
    section: str | None
    excerpt: str = Field(min_length=1, max_length=500)
    content_hash: str = Field(
        alias="contentHash", pattern=r"^[0-9a-f]{64}$"
    )


class TelemetryCitation(_PublicModel):
    type: Literal["telemetry"] = "telemetry"
    assessment_id: str = Field(alias="assessmentId", min_length=1)
    evidence_id: str = Field(alias="evidenceId", min_length=1)
    feature: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    window_start: str = Field(alias="windowStart", min_length=1)
    window_end: str = Field(alias="windowEnd", min_length=1)
    received_at: str = Field(alias="receivedAt", min_length=1)
    freshness_ms: float = Field(alias="freshnessMs", ge=0)
    window_seconds: float | None = Field(default=None, alias="windowSeconds", ge=0)
    quality_status: str = Field(alias="qualityStatus", min_length=1)


AssistantCitation = Annotated[
    ManualCitation | TelemetryCitation,
    Field(discriminator="type"),
]


class CorpusAnchor(_PublicModel):
    corpus_id: str = Field(alias="corpusId", min_length=1)
    manufacturer: str = Field(min_length=1)
    equipment_model: str = Field(alias="equipmentModel", min_length=1)
    embedding_model: str = Field(alias="embeddingModel", min_length=1)
    embedding_dimensions: int = Field(alias="embeddingDimensions", gt=0)
    min_relevance_score: float = Field(alias="minRelevanceScore", ge=0, le=1)


class ModelAnchors(_PublicModel):
    embedding: str = Field(min_length=1)
    generation: str = Field(min_length=1)


class GenerationMetadata(_PublicModel):
    """Server-attested invocation; a configured model is not proof of a call."""

    status: Literal["generated", "fallback", "not_called"] = "not_called"
    model: str | None = None
    invocation_id: str | None = Field(default=None, alias="invocationId")
    latency_ms: float | None = Field(default=None, alias="latencyMs", ge=0)
    tool_calls: int = Field(default=0, alias="toolCalls", ge=0, le=2)


class AssistantQueryResponse(_PublicModel):
    answer: AssistantAnswer
    grounding_status: Literal[
        "grounded",
        "manual_insufficient",
        "operational_unavailable",
        "degraded_fallback",
        "out_of_scope",
    ] = Field(alias="groundingStatus")
    citations: list[AssistantCitation]
    corpus: CorpusAnchor | None
    models: ModelAnchors
    generation: GenerationMetadata = Field(default_factory=GenerationMetadata)
    fallback_used: bool = Field(alias="fallbackUsed")
    limitations: list[str]
    human_validation_required: Literal[True] = Field(
        default=True, alias="humanValidationRequired"
    )
    conversation_id: UUID = Field(alias="conversationId")
    trace_id: UUID = Field(alias="traceId")
    latency_ms: float = Field(alias="latencyMs", ge=0)
