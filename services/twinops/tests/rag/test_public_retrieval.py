import asyncio
import json
from dataclasses import replace
from datetime import datetime, timezone
import time

import pytest

from twinops.rag.models import RagChunk, RagCorpus, RagDocument
from twinops.rag.repository import InMemoryRagRepository
from twinops.rag.retrieval import (
    CorpusUnavailableError,
    HybridRetriever,
    RetrievalCandidate,
    reciprocal_rank_fusion,
)


ASSET_ID = "forzy-motor-01"


class _Embeddings:
    def __init__(self, *, model="embed-v1", dimensions=3, vector=(1.0, 0.0, 0.0)):
        self.model = model
        self.dimensions = dimensions
        self.vector = vector
        self.calls = []

    async def embed(self, texts):
        self.calls.append(tuple(texts))
        return tuple(self.vector for _ in texts)


def _corpus(corpus_id, *, model="embed-v1", dimensions=3, threshold=0.2):
    return RagCorpus.draft(
        corpus_id=corpus_id,
        asset_id=ASSET_ID,
        manufacturer="WEG",
        equipment_model="W22",
        embedding_model=model,
        embedding_dimensions=dimensions,
        min_relevance_score=threshold,
    )


def _retriever(repository, embeddings, *, manufacturer="WEG", equipment_model="W22"):
    return HybridRetriever(
        repository,
        embeddings,
        manufacturer=manufacturer,
        equipment_model=equipment_model,
    )


def _document(corpus_id, document_id="doc-1", sha="a" * 64):
    return RagDocument(
        document_id=document_id,
        corpus_id=corpus_id,
        manufacturer="WEG",
        equipment_model="W22",
        revision="2026-01",
        language="en",
        source_url="https://manufacturer.example/manual.pdf",
        sha256=sha,
        page_count=20,
        coverage_pages=20,
    )


def _chunk(corpus_id, document_id, ordinal, *, text, embedding):
    return RagChunk(
        chunk_id=f"chunk-{corpus_id}-{ordinal:02d}",
        corpus_id=corpus_id,
        document_id=document_id,
        ordinal=ordinal,
        text=text,
        page_start=ordinal + 1,
        page_end=ordinal + 1,
        section="MAINTENANCE",
        content_hash=f"{ordinal + 1:064x}",
        token_count=len(text.split()),
        embedding=embedding,
    )


def _candidate(identifier, score=0.0):
    corpus_id = "c1"
    document = _document(corpus_id)
    chunk = replace(
        _chunk(
            corpus_id,
            document.document_id,
            int(identifier.rsplit("-", 1)[-1]),
            text=f"fixture {identifier}",
            embedding=(1.0, 0.0, 0.0),
        ),
        chunk_id=identifier,
    )
    return RetrievalCandidate(chunk=chunk, document=document, source_score=score)


def test_rrf_uses_both_top_12_lists_returns_top_6_and_has_stable_ties():
    vector = [_candidate(f"chunk-{index:02d}") for index in range(12)]
    lexical = [_candidate(f"chunk-{index:02d}") for index in range(11, -1, -1)]

    fused = reciprocal_rank_fusion(vector, lexical, limit=6)

    assert len(fused) == 6
    assert [item.candidate.chunk.chunk_id for item in fused] == [
        "chunk-00",
        "chunk-11",
        "chunk-01",
        "chunk-10",
        "chunk-02",
        "chunk-09",
    ]
    assert all(0.0 <= item.relevance_score <= 1.0 for item in fused)


@pytest.mark.asyncio
async def test_public_retrieval_uses_only_active_compatible_corpus_and_top_12_per_source():
    repository = InMemoryRagRepository()
    for corpus_id, sha, prefix in (
        ("c-old", "a" * 64, "old"),
        ("c-active", "b" * 64, "active"),
    ):
        corpus = _corpus(corpus_id)
        repository.create_corpus(corpus)
        document = _document(corpus_id, f"doc-{corpus_id}", sha)
        chunks = [
            _chunk(
                corpus_id,
                document.document_id,
                ordinal,
                text=f"{prefix} bearing lubrication item {ordinal}",
                embedding=(1.0, float(ordinal) / 100.0, 0.0),
            )
            for ordinal in range(15)
        ]
        repository.add_document(document, chunks)
        repository.publish_corpus(ASSET_ID, corpus_id)

    embeddings = _Embeddings()
    retriever = _retriever(repository, embeddings)

    result = await retriever.retrieve(ASSET_ID, "bearing lubrication")

    assert result.corpus.corpus_id == "c-active"
    assert len(result.vector_candidates) == 12
    assert len(result.lexical_candidates) == 12
    assert len(result.hits) == 6
    assert {item.candidate.chunk.corpus_id for item in result.hits} == {"c-active"}
    assert embeddings.calls == [("bearing lubrication",)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "dimensions"),
    [("embed-v2", 3), ("embed-v1", 2)],
)
async def test_incompatible_active_corpus_fails_before_embedding(model, dimensions):
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1"))
    document = _document("c1")
    repository.add_document(
        document,
        [
            _chunk(
                "c1",
                document.document_id,
                0,
                text="bearing lubrication",
                embedding=(1.0, 0.0, 0.0),
            )
        ],
    )
    repository.publish_corpus(ASSET_ID, "c1")
    embeddings = _Embeddings(model=model, dimensions=dimensions)

    with pytest.raises(CorpusUnavailableError, match="corpus_incompatible"):
        await _retriever(repository, embeddings).retrieve(ASSET_ID, "bearing")

    assert embeddings.calls == []


@pytest.mark.asyncio
async def test_missing_active_corpus_fails_before_embedding():
    repository = InMemoryRagRepository()
    embeddings = _Embeddings()

    with pytest.raises(CorpusUnavailableError, match="active_corpus_unavailable"):
        await _retriever(repository, embeddings).retrieve(ASSET_ID, "bearing")

    assert embeddings.calls == []


@pytest.mark.asyncio
async def test_pt_query_can_retrieve_an_english_chunk_through_vector_search():
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1"))
    document = _document("c1")
    repository.add_document(
        document,
        [
            _chunk(
                "c1",
                document.document_id,
                0,
                text="Inspect bearing lubrication before startup.",
                embedding=(1.0, 0.0, 0.0),
            )
        ],
    )
    repository.publish_corpus(ASSET_ID, "c1")

    result = await _retriever(repository, _Embeddings()).retrieve(
        ASSET_ID, "Como verificar a lubrificacao do rolamento?"
    )

    assert result.hits[0].candidate.chunk.text.startswith("Inspect bearing")


@pytest.mark.asyncio
async def test_persisted_threshold_marks_manual_insufficient():
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1", threshold=0.95))
    document = _document("c1")
    repository.add_document(
        document,
        [
            _chunk(
                "c1",
                document.document_id,
                0,
                text="unrelated electrical data",
                embedding=(0.0, 1.0, 0.0),
            )
        ],
    )
    repository.publish_corpus(ASSET_ID, "c1")

    result = await _retriever(repository, _Embeddings()).retrieve(
        ASSET_ID, "bearing"
    )

    assert result.sufficient is False
    assert result.threshold == 0.95


@pytest.mark.asyncio
async def test_uncalibrated_zero_threshold_cannot_be_published():
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1", threshold=0.0))
    document = _document("c1")
    repository.add_document(
        document,
        [
            _chunk(
                "c1",
                document.document_id,
                0,
                text="bearing",
                embedding=(1.0, 0.0, 0.0),
            )
        ],
    )
    embeddings = _Embeddings()

    with pytest.raises(ValueError, match="positive calibrated relevance threshold"):
        repository.publish_corpus(ASSET_ID, "c1")
    assert embeddings.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunk_vector", "expected"),
    [((1.0, 0.0, 0.0), True), ((0.0, 1.0, 0.0), False)],
)
async def test_absolute_vector_score_separates_semantic_from_orthogonal_without_lexical_match(
    chunk_vector, expected
):
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1", threshold=0.8))
    document = _document("c1")
    repository.add_document(
        document,
        [
            _chunk(
                "c1",
                document.document_id,
                0,
                text="English bearing guidance",
                embedding=chunk_vector,
            )
        ],
    )
    repository.publish_corpus(ASSET_ID, "c1")

    result = await _retriever(repository, _Embeddings()).retrieve(
        ASSET_ID, "orientação sem termos ingleses"
    )

    assert result.lexical_candidates == ()
    assert result.sufficient is expected
    if expected:
        assert result.hits[0].absolute_score >= 0.8
    else:
        assert result.hits == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("manufacturer", "equipment_model"),
    [("OtherCo", "W22"), ("WEG", "OtherMotor")],
)
async def test_public_manual_identity_mismatch_fails_before_embedding(
    manufacturer, equipment_model
):
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1", threshold=0.2))
    document = _document("c1")
    repository.add_document(document, [])
    repository.publish_corpus(ASSET_ID, "c1")
    embeddings = _Embeddings()
    retriever = _retriever(
        repository,
        embeddings,
        manufacturer=manufacturer,
        equipment_model=equipment_model,
    )

    assert retriever.healthy(ASSET_ID) is False
    with pytest.raises(CorpusUnavailableError, match="corpus_incompatible"):
        await retriever.retrieve(ASSET_ID, "bearing")
    assert embeddings.calls == []


class _SlowRepository(InMemoryRagRepository):
    def get_active_corpus(self, asset_id):
        time.sleep(0.1)
        return super().get_active_corpus(asset_id)

    def exact_vector_search(self, *args, **kwargs):
        time.sleep(0.1)
        return super().exact_vector_search(*args, **kwargs)

    def lexical_search(self, *args, **kwargs):
        time.sleep(0.1)
        return super().lexical_search(*args, **kwargs)


def _published_slow_repository():
    repository = _SlowRepository()
    corpus = _corpus("c1")
    repository.create_corpus(corpus)
    document = _document("c1")
    repository.add_document(
        document,
        [
            _chunk(
                "c1",
                document.document_id,
                0,
                text="bearing lubrication",
                embedding=(1.0, 0.0, 0.0),
            )
        ],
    )
    repository.publish_corpus(ASSET_ID, "c1")
    return repository


@pytest.mark.asyncio
async def test_sync_repository_preflight_does_not_block_event_loop():
    retriever = _retriever(_published_slow_repository(), _Embeddings())
    started = time.perf_counter()

    async def pulse():
        await asyncio.sleep(0.005)
        return time.perf_counter() - started

    _, pulse_delay = await asyncio.gather(retriever.prepare(ASSET_ID), pulse())

    assert pulse_delay < 0.05


@pytest.mark.asyncio
async def test_sync_repository_searches_do_not_block_event_loop():
    repository = _published_slow_repository()
    retriever = _retriever(repository, _Embeddings())
    corpus = await retriever.prepare(ASSET_ID)
    started = time.perf_counter()

    async def pulse():
        await asyncio.sleep(0.005)
        return time.perf_counter() - started

    _, pulse_delay = await asyncio.gather(
        retriever.retrieve(ASSET_ID, "bearing", corpus=corpus),
        pulse(),
    )

    assert pulse_delay < 0.05


@pytest.mark.asyncio
async def test_retrieval_logs_each_sanitized_stage_without_query_or_chunk(caplog):
    caplog.set_level("INFO", logger="twinops.rag")
    repository = _published_slow_repository()
    retriever = _retriever(repository, _Embeddings())
    secret_query = "bearing-query-secret-never-log"

    await retriever.retrieve(ASSET_ID, secret_query, trace_id="trace-1")

    payloads = [
        json.loads(record.message)
        for record in caplog.records
        if record.message.startswith("{")
    ]
    stages = {payload["stage"] for payload in payloads}
    assert {
        "corpus_lookup",
        "query_embedding",
        "vector_search",
        "lexical_search",
        "fusion",
    } <= stages
    assert all(payload["traceId"] == "trace-1" for payload in payloads)
    assert secret_query not in caplog.text
    assert "bearing lubrication" not in caplog.text
