"""Administrative orchestration for draft ingestion and atomic publication."""

import asyncio
from time import perf_counter

from uuid import uuid4

from twinops.rag.chunking import chunk_pages
from twinops.rag.embeddings import EmbeddingClient
from twinops.rag.generation import ChatClient
from twinops.rag.errors import (
    CorpusCompatibilityError,
    CorpusConflictError,
    CorpusNotFoundError,
    InvalidAdminInputError,
)
from twinops.rag.models import (
    ActiveCorpusChange,
    CANONICAL_RAG_ASSET_ID,
    CorpusCoverage,
    DocumentMetadata,
    RagChunk,
    RagCorpus,
    RagDocument,
    UploadedDocument,
)
from twinops.rag.operational import TrustedOperationalContext
from twinops.rag.public_models import AssistantQueryRequest, AssistantQueryResponse
from twinops.rag.public_service import RagAssistantService
from twinops.rag.pdf import extract_searchable_pdf
from twinops.rag.repository import RagRepository
from twinops.rag.retrieval import (
    FINAL_HIT_LIMIT,
    LEXICAL_CANDIDATE_LIMIT,
    VECTOR_CANDIDATE_LIMIT,
    FusedRetrievalHit,
    RetrievalResult,
    reciprocal_rank_fusion,
)


MAX_EMBEDDING_BATCH_SIZE = 64


class DuplicateDocumentError(CorpusConflictError):
    def __init__(self) -> None:
        super().__init__("duplicate_document")


class _StaticAcceptanceRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result

    def healthy(self, asset_id: str) -> bool:
        return asset_id == self.result.corpus.asset_id

    async def retrieve(self, asset_id: str, query: str, *, corpus=None):
        if asset_id != self.result.corpus.asset_id:
            raise ValueError("acceptance asset mismatch")
        return self.result


class RagAdminService:
    def __init__(
        self,
        repository: RagRepository,
        embeddings: EmbeddingClient,
        *,
        query_embeddings: EmbeddingClient | None = None,
        manufacturer: str,
        equipment_model: str,
        embedding_batch_size: int = 32,
        acceptance_chat: ChatClient | None = None,
        query_timeout_seconds: float = 10.0,
    ) -> None:
        if (
            not manufacturer.strip()
            or manufacturer != manufacturer.strip()
            or not equipment_model.strip()
            or equipment_model != equipment_model.strip()
        ):
            raise ValueError("approved manual identity must not be empty")
        if not 1 <= embedding_batch_size <= MAX_EMBEDDING_BATCH_SIZE:
            raise ValueError("embedding batch size is out of range")
        if not 0 < query_timeout_seconds <= 11:
            raise ValueError("query timeout must be in (0, 11]")
        if not embeddings.model.strip() or embeddings.dimensions <= 0:
            raise ValueError("embedding client anchors are invalid")
        query_client = query_embeddings or embeddings
        if (
            query_client.model != embeddings.model
            or query_client.dimensions != embeddings.dimensions
        ):
            raise ValueError("query embedding client is incompatible")
        self.repository = repository
        self.embeddings = embeddings
        self.query_embeddings = query_client
        self.manufacturer = manufacturer
        self.equipment_model = equipment_model
        self.embedding_batch_size = embedding_batch_size
        self.acceptance_chat = acceptance_chat
        self.query_timeout_seconds = query_timeout_seconds

    def create_draft(
        self,
        *,
        asset_id: str,
        chunk_target_tokens: int = 700,
        chunk_overlap_tokens: int = 100,
        min_relevance_score: float = 0.0,
    ) -> RagCorpus:
        if asset_id != CANONICAL_RAG_ASSET_ID:
            raise InvalidAdminInputError("asset_not_found")
        try:
            corpus = RagCorpus.draft(
                corpus_id=str(uuid4()),
                asset_id=asset_id,
                manufacturer=self.manufacturer,
                equipment_model=self.equipment_model,
                embedding_model=self.embeddings.model,
                embedding_dimensions=self.embeddings.dimensions,
                chunk_target_tokens=chunk_target_tokens,
                chunk_overlap_tokens=chunk_overlap_tokens,
                min_relevance_score=min_relevance_score,
            )
        except ValueError:
            raise InvalidAdminInputError(
                "invalid_corpus_configuration"
            ) from None
        return self.repository.create_corpus(corpus)

    async def upload_document(
        self,
        corpus_id: str,
        *,
        filename: str,
        content_type: str | None,
        payload: bytes,
        metadata: DocumentMetadata,
    ) -> UploadedDocument:
        if not filename or not filename.casefold().endswith(".pdf"):
            raise InvalidAdminInputError("invalid_document_filename")
        corpus = self._require_corpus(corpus_id)
        self._require_compatible(corpus)
        if corpus.status != "draft":
            raise CorpusConflictError("corpus_immutable")
        if (
            metadata.manufacturer != corpus.manufacturer
            or metadata.equipment_model != corpus.equipment_model
        ):
            raise CorpusCompatibilityError()
        extracted = extract_searchable_pdf(payload, content_type=content_type)
        if (
            self.repository.find_document_by_sha256(
                corpus_id, extracted.sha256
            )
            is not None
        ):
            raise DuplicateDocumentError()
        drafts = chunk_pages(
            extracted.pages,
            target_tokens=corpus.chunk_target_tokens,
            overlap_tokens=corpus.chunk_overlap_tokens,
        )
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(drafts), self.embedding_batch_size):
            batch = drafts[start : start + self.embedding_batch_size]
            vectors.extend(await self.embeddings.embed([item.text for item in batch]))
        document_id = str(uuid4())
        document = RagDocument(
            document_id=document_id,
            corpus_id=corpus_id,
            manufacturer=metadata.manufacturer,
            equipment_model=metadata.equipment_model,
            revision=metadata.revision,
            language=metadata.language,
            source_url=metadata.source_url,
            sha256=extracted.sha256,
            page_count=extracted.page_count,
            coverage_pages=extracted.coverage_pages,
        )
        chunks = tuple(
            RagChunk(
                chunk_id=str(uuid4()),
                corpus_id=corpus_id,
                document_id=document_id,
                ordinal=draft.ordinal,
                text=draft.text,
                page_start=draft.page_start,
                page_end=draft.page_end,
                section=draft.section,
                content_hash=draft.content_hash,
                token_count=draft.token_count,
                embedding=tuple(vector),
            )
            for draft, vector in zip(drafts, vectors, strict=True)
        )
        try:
            self.repository.add_document(document, chunks)
        except ValueError as exc:
            if "duplicate" in str(exc):
                raise DuplicateDocumentError() from None
            raise CorpusConflictError("corpus_write_conflict") from None
        return UploadedDocument(document, self.repository.coverage(corpus_id))

    def coverage(self, corpus_id: str) -> CorpusCoverage:
        self._require_corpus(corpus_id)
        return self.repository.coverage(corpus_id)

    async def test_retrieval(
        self, corpus_id: str, query: str, *, limit: int = 6
    ) -> list[FusedRetrievalHit]:
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            raise InvalidAdminInputError("invalid_retrieval_query")
        if not 1 <= limit <= FINAL_HIT_LIMIT:
            raise InvalidAdminInputError("invalid_retrieval_limit")
        corpus = self._require_corpus(corpus_id)
        self._require_compatible(corpus)
        vector = (await self.query_embeddings.embed([query]))[0]
        vector_work = asyncio.to_thread(
            self.repository.exact_vector_search,
            corpus_id,
            query_embedding=vector,
            limit=VECTOR_CANDIDATE_LIMIT,
        )
        lexical_work = asyncio.to_thread(
            self.repository.lexical_search,
            corpus_id,
            query=query,
            limit=LEXICAL_CANDIDATE_LIMIT,
        )
        vector_candidates, lexical_candidates = await asyncio.gather(
            vector_work, lexical_work
        )
        return reciprocal_rank_fusion(
            vector_candidates,
            lexical_candidates,
            limit=limit,
        )

    async def test_answer(
        self,
        corpus_id: str,
        question: str,
        *,
        operational: TrustedOperationalContext,
        started_at: float | None = None,
    ) -> tuple[AssistantQueryResponse, tuple[FusedRetrievalHit, ...]]:
        started = perf_counter() if started_at is None else started_at
        if self.acceptance_chat is None:
            raise RuntimeError("acceptance_chat_unavailable")
        corpus = self._require_corpus(corpus_id)
        self._require_compatible(corpus)
        raw_hits = tuple(await self.test_retrieval(corpus_id, question, limit=6))
        filtered_hits = tuple(
            hit
            for hit in raw_hits
            if hit.absolute_score >= corpus.min_relevance_score
        )
        retrieval = RetrievalResult(
            corpus=corpus,
            vector_candidates=(),
            lexical_candidates=(),
            hits=filtered_hits,
            threshold=corpus.min_relevance_score,
            sufficient=bool(filtered_hits),
        )
        assistant = RagAssistantService(
            _StaticAcceptanceRetriever(retrieval),
            self.acceptance_chat,
            query_timeout_seconds=max(
                0.001,
                self.query_timeout_seconds - (perf_counter() - started),
            ),
        )
        response = await assistant.query(
            corpus.asset_id,
            AssistantQueryRequest(question=question),
            operational=operational,
        )
        return response, raw_hits

    def publish(self, corpus_id: str) -> ActiveCorpusChange:
        corpus = self._require_corpus(corpus_id)
        self._require_compatible(corpus)
        try:
            return self.repository.publish_corpus(corpus.asset_id, corpus_id)
        except ValueError:
            raise CorpusConflictError("corpus_not_publishable") from None

    def reactivate(self, corpus_id: str) -> ActiveCorpusChange:
        corpus = self._require_corpus(corpus_id)
        self._require_compatible(corpus)
        try:
            return self.repository.activate_published_corpus(
                corpus.asset_id, corpus_id
            )
        except ValueError:
            raise CorpusConflictError("corpus_not_reactivatable") from None

    def _require_corpus(self, corpus_id: str) -> RagCorpus:
        corpus = self.repository.get_corpus(corpus_id)
        if corpus is None:
            raise CorpusNotFoundError()
        return corpus

    def _require_compatible(self, corpus: RagCorpus) -> None:
        if (
            corpus.embedding_model != self.embeddings.model
            or corpus.embedding_dimensions != self.embeddings.dimensions
            or corpus.manufacturer != self.manufacturer
            or corpus.equipment_model != self.equipment_model
        ):
            raise CorpusCompatibilityError()
