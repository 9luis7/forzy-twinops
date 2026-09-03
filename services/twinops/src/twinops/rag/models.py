"""Immutable domain records for versioned technical-manual corpora."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math
import re
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator


_SHA256 = re.compile(r"[0-9a-f]{64}")
CANONICAL_RAG_ASSET_ID = "forzy-motor-01"


def _non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{field_name} must be timezone-aware")


class DocumentMetadata(BaseModel):
    """Required provenance supplied by the administrator for one manual."""

    model_config = ConfigDict(str_strip_whitespace=True)

    manufacturer: str
    equipment_model: str
    revision: str
    language: str
    source_url: str

    @field_validator("manufacturer", "equipment_model", "revision", "language")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("metadata fields must not be empty")
        return value

    @field_validator("source_url")
    @classmethod
    def require_https_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            raise ValueError("source URL must use https") from None
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError("source URL must use https")
        return value


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page number must be positive")
        if not isinstance(self.text, str):
            raise ValueError("page text must be a string")


@dataclass(frozen=True)
class ExtractedPdf:
    sha256: str
    pages: tuple[ExtractedPage, ...]
    page_count: int
    coverage_pages: int

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.sha256) is None:
            raise ValueError("PDF sha256 must be lowercase hexadecimal")
        if self.page_count != len(self.pages) or self.page_count < 1:
            raise ValueError("PDF page count is inconsistent")
        if not 1 <= self.coverage_pages <= self.page_count:
            raise ValueError("PDF coverage is inconsistent")


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    text: str
    page_start: int
    page_end: int
    section: str | None
    content_hash: str
    token_count: int

    def __post_init__(self) -> None:
        if self.ordinal < 0 or self.page_start < 1 or self.page_end < self.page_start:
            raise ValueError("chunk draft position is invalid")
        _non_empty(self.text, "chunk draft text")
        if self.section is not None:
            _non_empty(self.section, "chunk draft section")
        if _SHA256.fullmatch(self.content_hash) is None or self.token_count < 1:
            raise ValueError("chunk draft hash/token count is invalid")


@dataclass(frozen=True)
class RagCorpus:
    corpus_id: str
    asset_id: str
    manufacturer: str
    equipment_model: str
    embedding_model: str
    embedding_dimensions: int
    chunk_target_tokens: int = 700
    chunk_overlap_tokens: int = 100
    min_relevance_score: float = 0.0
    status: Literal["draft", "published"] = "draft"
    created_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        _non_empty(self.corpus_id, "corpus id")
        if self.asset_id != CANONICAL_RAG_ASSET_ID:
            raise ValueError("unsupported RAG asset")
        _non_empty(self.manufacturer, "manufacturer")
        _non_empty(self.equipment_model, "equipment model")
        _non_empty(self.embedding_model, "embedding model")
        if self.embedding_dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")
        if (
            self.chunk_target_tokens <= self.chunk_overlap_tokens
            or self.chunk_overlap_tokens < 0
        ):
            raise ValueError("chunk target must exceed non-negative overlap")
        if not math.isfinite(self.min_relevance_score) or not (
            0 <= self.min_relevance_score <= 1
        ):
            raise ValueError("minimum relevance score must be finite in [0, 1]")
        _aware(self.created_at, "created at")
        if self.status == "draft" and self.published_at is not None:
            raise ValueError("draft corpus cannot have publication time")
        if self.status == "published":
            if self.published_at is None:
                raise ValueError("published corpus requires publication time")
            _aware(self.published_at, "published at")
        if self.status not in {"draft", "published"}:
            raise ValueError("unknown corpus status")

    @classmethod
    def draft(
        cls,
        *,
        corpus_id: str,
        asset_id: str,
        manufacturer: str,
        equipment_model: str,
        embedding_model: str,
        embedding_dimensions: int,
        chunk_target_tokens: int = 700,
        chunk_overlap_tokens: int = 100,
        min_relevance_score: float = 0.0,
        created_at: datetime | None = None,
    ) -> Self:
        if embedding_dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")
        if chunk_target_tokens <= chunk_overlap_tokens or chunk_overlap_tokens < 0:
            raise ValueError("chunk target must exceed non-negative overlap")
        return cls(
            corpus_id=corpus_id,
            asset_id=asset_id,
            manufacturer=manufacturer,
            equipment_model=equipment_model,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            chunk_target_tokens=chunk_target_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
            min_relevance_score=min_relevance_score,
            created_at=created_at or datetime.now(timezone.utc),
        )

    def published(self, at: datetime | None = None) -> Self:
        return replace(
            self,
            status="published",
            published_at=self.published_at or at or datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class RagDocument:
    document_id: str
    corpus_id: str
    manufacturer: str
    equipment_model: str
    revision: str
    language: str
    source_url: str
    sha256: str
    page_count: int
    coverage_pages: int

    def __post_init__(self) -> None:
        _non_empty(self.document_id, "document id")
        _non_empty(self.corpus_id, "corpus id")
        DocumentMetadata(
            manufacturer=self.manufacturer,
            equipment_model=self.equipment_model,
            revision=self.revision,
            language=self.language,
            source_url=self.source_url,
        )
        if _SHA256.fullmatch(self.sha256) is None:
            raise ValueError("document sha256 must be lowercase hexadecimal")
        if not 1 <= self.page_count <= 400:
            raise ValueError("document page count must be between 1 and 400")
        if not 1 <= self.coverage_pages <= self.page_count:
            raise ValueError("document coverage must be within page count")


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    corpus_id: str
    document_id: str
    ordinal: int
    text: str
    page_start: int
    page_end: int
    section: str | None
    content_hash: str
    token_count: int
    embedding: tuple[float, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.chunk_id, "chunk id"),
            (self.corpus_id, "corpus id"),
            (self.document_id, "document id"),
        ):
            _non_empty(value, name)
        if self.ordinal < 0:
            raise ValueError("chunk ordinal must be non-negative")
        _non_empty(self.text, "chunk text")
        if self.page_start < 1 or self.page_end < self.page_start:
            raise ValueError("chunk page range is invalid")
        if self.section is not None:
            _non_empty(self.section, "chunk section")
        if _SHA256.fullmatch(self.content_hash) is None:
            raise ValueError("chunk hash must be lowercase hexadecimal")
        if self.token_count < 1:
            raise ValueError("chunk token count must be positive")
        if not self.embedding or not all(
            math.isfinite(float(value)) for value in self.embedding
        ):
            raise ValueError("chunk embedding must contain finite values")


@dataclass(frozen=True)
class CorpusCoverage:
    corpus_id: str
    document_count: int
    page_count: int
    coverage_pages: int
    chunk_count: int

    def __post_init__(self) -> None:
        _non_empty(self.corpus_id, "corpus id")
        if min(
            self.document_count,
            self.page_count,
            self.coverage_pages,
            self.chunk_count,
        ) < 0 or self.coverage_pages > self.page_count:
            raise ValueError("corpus coverage is invalid")


@dataclass(frozen=True)
class ActiveCorpusChange:
    asset_id: str
    corpus_id: str
    previous_corpus_id: str | None
    activated_at: datetime

    def __post_init__(self) -> None:
        if self.asset_id != CANONICAL_RAG_ASSET_ID:
            raise ValueError("unsupported RAG asset")
        _non_empty(self.corpus_id, "corpus id")
        _aware(self.activated_at, "activated at")


@dataclass(frozen=True)
class UploadedDocument:
    document: RagDocument
    coverage: CorpusCoverage


@dataclass(frozen=True)
class RetrievalCandidate:
    """One corpus-scoped chunk with immutable document provenance."""

    chunk: RagChunk
    document: RagDocument
    source_score: float

    def __post_init__(self) -> None:
        if self.chunk.corpus_id != self.document.corpus_id:
            raise ValueError("retrieval candidate crosses corpus boundaries")
        if self.chunk.document_id != self.document.document_id:
            raise ValueError("retrieval candidate crosses document boundaries")
        if not math.isfinite(self.source_score):
            raise ValueError("retrieval source score must be finite")
