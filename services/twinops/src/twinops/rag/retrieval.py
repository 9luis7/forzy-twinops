"""Exact hybrid retrieval over one immutable active corpus version."""

import asyncio
from dataclasses import dataclass
import math
from time import perf_counter

from twinops.rag.embeddings import EmbeddingClient
from twinops.rag.models import RagCorpus, RetrievalCandidate
from twinops.rag.repository import RagRepository
from twinops.rag.telemetry import log_rag_stage


VECTOR_CANDIDATE_LIMIT = 12
LEXICAL_CANDIDATE_LIMIT = 12
FINAL_HIT_LIMIT = 6
RRF_CONSTANT = 60


class CorpusUnavailableError(RuntimeError):
    """Sanitized failure raised before provider work when corpus use is unsafe."""


@dataclass(frozen=True)
class FusedRetrievalHit:
    candidate: RetrievalCandidate
    relevance_score: float
    vector_rank: int | None
    lexical_rank: int | None
    absolute_score: float = 0.0

    @property
    def rank_score(self) -> float:
        return self.relevance_score


@dataclass(frozen=True)
class RetrievalResult:
    corpus: RagCorpus
    vector_candidates: tuple[RetrievalCandidate, ...]
    lexical_candidates: tuple[RetrievalCandidate, ...]
    hits: tuple[FusedRetrievalHit, ...]
    threshold: float
    sufficient: bool


class HybridRetriever:
    def __init__(
        self,
        repository: RagRepository,
        embeddings: EmbeddingClient,
        *,
        manufacturer: str,
        equipment_model: str,
    ) -> None:
        if not manufacturer.strip() or not equipment_model.strip():
            raise ValueError("public manual identity is required")
        self.repository = repository
        self.embeddings = embeddings
        self.manufacturer = manufacturer
        self.equipment_model = equipment_model

    def healthy(self, asset_id: str) -> bool:
        try:
            corpus = self.repository.get_active_corpus(asset_id)
            self._validate_corpus(corpus, asset_id)
            return True
        except Exception:
            return False

    async def prepare(
        self, asset_id: str, *, trace_id: str | None = None
    ) -> RagCorpus:
        started = perf_counter()
        try:
            corpus = await asyncio.to_thread(
                self.repository.get_active_corpus, asset_id
            )
            self._validate_corpus(corpus, asset_id)
            assert corpus is not None
        except BaseException as error:
            log_rag_stage(
                "corpus_lookup",
                outcome=_failure_outcome(error),
                duration_ms=(perf_counter() - started) * 1000,
                asset_id=asset_id,
                trace_id=trace_id,
            )
            raise
        log_rag_stage(
            "corpus_lookup",
            outcome="ok",
            duration_ms=(perf_counter() - started) * 1000,
            asset_id=asset_id,
            corpus_id=corpus.corpus_id,
            trace_id=trace_id,
        )
        return corpus

    async def retrieve(
        self,
        asset_id: str,
        query: str,
        *,
        corpus: RagCorpus | None = None,
        trace_id: str | None = None,
    ) -> RetrievalResult:
        corpus = corpus or await self.prepare(asset_id, trace_id=trace_id)
        self._validate_corpus(corpus, asset_id)
        embedding_started = perf_counter()
        try:
            query_vector = (await self.embeddings.embed([query]))[0]
        except BaseException as error:
            log_rag_stage(
                "query_embedding",
                outcome=_failure_outcome(error),
                duration_ms=(perf_counter() - embedding_started) * 1000,
                corpus_id=corpus.corpus_id,
                model=self.embeddings.model,
                count=1,
                trace_id=trace_id,
            )
            raise
        log_rag_stage(
            "query_embedding",
            outcome="ok",
            duration_ms=(perf_counter() - embedding_started) * 1000,
            corpus_id=corpus.corpus_id,
            model=self.embeddings.model,
            count=1,
            trace_id=trace_id,
        )
        vector_work = _timed_search(
            "vector_search",
            self.repository.exact_vector_search,
            corpus_id=corpus.corpus_id,
            trace_id=trace_id,
            query_embedding=query_vector,
            limit=VECTOR_CANDIDATE_LIMIT,
        )
        lexical_work = _timed_search(
            "lexical_search",
            self.repository.lexical_search,
            corpus_id=corpus.corpus_id,
            trace_id=trace_id,
            query=query,
            limit=LEXICAL_CANDIDATE_LIMIT,
        )
        vector_rows, lexical_rows = await asyncio.gather(
            vector_work, lexical_work
        )
        vector_candidates = tuple(vector_rows)
        lexical_candidates = tuple(lexical_rows)
        fusion_started = perf_counter()
        try:
            ranked_hits = reciprocal_rank_fusion(
                vector_candidates,
                lexical_candidates,
                limit=FINAL_HIT_LIMIT,
            )
        except Exception:
            log_rag_stage(
                "fusion",
                outcome="invalid_response",
                duration_ms=(perf_counter() - fusion_started) * 1000,
                corpus_id=corpus.corpus_id,
                count=len(vector_candidates) + len(lexical_candidates),
                trace_id=trace_id,
            )
            raise
        log_rag_stage(
            "fusion",
            outcome="ok",
            duration_ms=(perf_counter() - fusion_started) * 1000,
            corpus_id=corpus.corpus_id,
            count=len(ranked_hits),
            trace_id=trace_id,
        )
        hits = tuple(
            hit
            for hit in ranked_hits
            if hit.absolute_score >= corpus.min_relevance_score
        )
        return RetrievalResult(
            corpus=corpus,
            vector_candidates=vector_candidates,
            lexical_candidates=lexical_candidates,
            hits=hits,
            threshold=corpus.min_relevance_score,
            sufficient=bool(hits),
        )

    def _validate_corpus(
        self, corpus: RagCorpus | None, asset_id: str
    ) -> None:
        if corpus is None or corpus.status != "published":
            raise CorpusUnavailableError("active_corpus_unavailable")
        if (
            corpus.asset_id != asset_id
            or corpus.manufacturer != self.manufacturer
            or corpus.equipment_model != self.equipment_model
            or corpus.embedding_model != self.embeddings.model
            or corpus.embedding_dimensions != self.embeddings.dimensions
        ):
            raise CorpusUnavailableError("corpus_incompatible")
        if (
            not math.isfinite(corpus.min_relevance_score)
            or corpus.min_relevance_score <= 0
        ):
            raise CorpusUnavailableError("corpus_not_calibrated")


async def _timed_search(
    stage,
    operation,
    *,
    corpus_id: str,
    trace_id: str | None = None,
    **kwargs,
):
    started = perf_counter()
    try:
        rows = await asyncio.to_thread(operation, corpus_id, **kwargs)
    except BaseException as error:
        log_rag_stage(
            stage,
            outcome=_failure_outcome(error),
            duration_ms=(perf_counter() - started) * 1000,
            corpus_id=corpus_id,
            trace_id=trace_id,
        )
        raise
    log_rag_stage(
        stage,
        outcome="ok",
        duration_ms=(perf_counter() - started) * 1000,
        corpus_id=corpus_id,
        count=len(rows),
        trace_id=trace_id,
    )
    return rows


def _failure_outcome(error: BaseException) -> str:
    if isinstance(error, asyncio.CancelledError):
        return "cancelled"
    if isinstance(error, TimeoutError):
        return "timeout"
    return "unavailable"


def reciprocal_rank_fusion(
    vector_candidates: list[RetrievalCandidate] | tuple[RetrievalCandidate, ...],
    lexical_candidates: list[RetrievalCandidate] | tuple[RetrievalCandidate, ...],
    *,
    limit: int = FINAL_HIT_LIMIT,
) -> list[FusedRetrievalHit]:
    """Fuse ranks with RRF(k=60), normalized to [0, 1], then stable IDs."""

    if not 1 <= limit <= FINAL_HIT_LIMIT:
        raise ValueError("final retrieval limit must be between 1 and 6")
    rankings = (
        tuple(vector_candidates[:VECTOR_CANDIDATE_LIMIT]),
        tuple(lexical_candidates[:LEXICAL_CANDIDATE_LIMIT]),
    )
    by_id: dict[str, RetrievalCandidate] = {}
    ranks: dict[str, list[int | None]] = {}
    scores: dict[str, float] = {}
    absolute_scores: dict[str, float] = {}
    for source_index, ranking in enumerate(rankings):
        for rank, candidate in enumerate(ranking, start=1):
            identifier = candidate.chunk.chunk_id
            existing = by_id.get(identifier)
            if existing is not None and (
                existing.chunk.corpus_id != candidate.chunk.corpus_id
                or existing.chunk.document_id != candidate.chunk.document_id
            ):
                raise ValueError("retrieval identity collision")
            by_id[identifier] = candidate
            ranks.setdefault(identifier, [None, None])[source_index] = rank
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (
                RRF_CONSTANT + rank
            )
            source_score = float(candidate.source_score)
            if not math.isfinite(source_score):
                source_score = 0.0
            absolute_scores[identifier] = max(
                absolute_scores.get(identifier, 0.0),
                min(1.0, max(0.0, source_score)),
            )

    maximum = 2.0 / (RRF_CONSTANT + 1)
    fused = [
        FusedRetrievalHit(
            candidate=candidate,
            relevance_score=min(1.0, scores[identifier] / maximum),
            vector_rank=ranks[identifier][0],
            lexical_rank=ranks[identifier][1],
            absolute_score=absolute_scores[identifier],
        )
        for identifier, candidate in by_id.items()
    ]
    return sorted(
        fused,
        key=lambda item: (
            -item.relevance_score,
            item.candidate.chunk.chunk_id,
        ),
    )[:limit]
