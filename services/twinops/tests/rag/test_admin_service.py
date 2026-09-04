import asyncio
import threading
import time

import pytest

from twinops.rag.admin_service import DuplicateDocumentError, RagAdminService
from twinops.rag.generation import (
    GeneratedAssistantPayload,
    GeneratedManualReference,
)
from twinops.rag.models import DocumentMetadata
from twinops.rag.operational import TrustedOperationalContext
from twinops.rag.repository import InMemoryRagRepository

from .pdf_factory import searchable_pdf


class _Embeddings:
    model = "embed-v1"
    dimensions = 3

    async def embed(self, texts):
        return tuple((0.1, 0.2, 0.3) for _ in texts)


class _SlowQueryEmbeddings(_Embeddings):
    async def embed(self, texts):
        await asyncio.sleep(0.08)
        return await super().embed(texts)


class _SlowChat:
    model = "generation-v1"

    async def generate(self, messages):
        await asyncio.sleep(0.08)
        payload = messages[-1]["content"]
        chunk_id = payload.split('"chunkId": "', 1)[1].split('"', 1)[0]
        return GeneratedAssistantPayload(
            manualCitations=[
                GeneratedManualReference(
                    chunkId=chunk_id,
                    exactQuote="MAINTENANCE bearing lubrication",
                )
            ]
        )


def _metadata():
    return DocumentMetadata(
        manufacturer="WEG",
        equipment_model="W22",
        revision="2026-01",
        language="en",
        source_url="https://manufacturer.example/manual.pdf",
    )


@pytest.mark.asyncio
async def test_admin_flow_stays_draft_until_explicit_publish_and_supports_reactivation():
    repository = InMemoryRagRepository()
    service = RagAdminService(
        repository,
        _Embeddings(),
        manufacturer="WEG",
        equipment_model="W22",
    )
    first = service.create_draft(
        asset_id="forzy-motor-01", min_relevance_score=0.2
    )
    uploaded = await service.upload_document(
        first.corpus_id,
        filename="manual.pdf",
        content_type="application/pdf",
        payload=searchable_pdf("MAINTENANCE bearing lubrication"),
        metadata=_metadata(),
    )

    assert repository.get_active_corpus("forzy-motor-01") is None
    assert uploaded.document.sha256
    assert uploaded.coverage.coverage_pages == 1
    assert uploaded.coverage.chunk_count == 1
    assert service.test_retrieval is not None

    first_activation = service.publish(first.corpus_id)
    second = service.create_draft(
        asset_id="forzy-motor-01", min_relevance_score=0.2
    )
    await service.upload_document(
        second.corpus_id,
        filename="manual-v2.pdf",
        content_type="application/pdf",
        payload=searchable_pdf("MAINTENANCE revised interval"),
        metadata=DocumentMetadata(
            **{**_metadata().model_dump(), "revision": "2026-02"}
        ),
    )
    second_activation = service.publish(second.corpus_id)
    rollback = service.reactivate(first.corpus_id)

    assert first_activation.previous_corpus_id is None
    assert second_activation.previous_corpus_id == first.corpus_id
    assert rollback.previous_corpus_id == second.corpus_id


@pytest.mark.asyncio
async def test_duplicate_sha_is_rejected_before_embedding_is_repeated():
    repository = InMemoryRagRepository()
    embeddings = _Embeddings()
    service = RagAdminService(
        repository,
        embeddings,
        manufacturer="WEG",
        equipment_model="W22",
    )
    corpus = service.create_draft(asset_id="forzy-motor-01")
    payload = searchable_pdf("searchable manual")
    await service.upload_document(
        corpus.corpus_id,
        filename="manual.pdf",
        content_type="application/pdf",
        payload=payload,
        metadata=_metadata(),
    )

    with pytest.raises(DuplicateDocumentError):
        await service.upload_document(
            corpus.corpus_id,
            filename="copy.pdf",
            content_type="application/pdf",
            payload=payload,
            metadata=_metadata(),
        )


@pytest.mark.asyncio
async def test_draft_retrieval_uses_public_hybrid_fusion_and_keeps_db_off_loop():
    loop_thread = threading.get_ident()

    class TrackingRepository(InMemoryRagRepository):
        def __init__(self):
            super().__init__()
            self.search_threads = []

        def exact_vector_search(self, *args, **kwargs):
            self.search_threads.append(threading.get_ident())
            return super().exact_vector_search(*args, **kwargs)

        def lexical_search(self, *args, **kwargs):
            self.search_threads.append(threading.get_ident())
            return super().lexical_search(*args, **kwargs)

    repository = TrackingRepository()
    service = RagAdminService(
        repository,
        _Embeddings(),
        manufacturer="WEG",
        equipment_model="W22",
    )
    corpus = service.create_draft(asset_id="forzy-motor-01")
    await service.upload_document(
        corpus.corpus_id,
        filename="manual.pdf",
        content_type="application/pdf",
        payload=searchable_pdf("MAINTENANCE bearing lubrication"),
        metadata=_metadata(),
    )

    hits = await service.test_retrieval(corpus.corpus_id, "bearing", limit=6)

    assert len(hits) == 1
    hit = hits[0]
    assert hit.candidate.chunk.corpus_id == corpus.corpus_id
    assert hit.candidate.document.manufacturer == "WEG"
    assert hit.absolute_score == pytest.approx(1.0)
    assert hit.rank_score == pytest.approx(1.0)
    assert hit.vector_rank == 1
    assert hit.lexical_rank == 1
    assert repository.search_threads
    assert all(thread_id != loop_thread for thread_id in repository.search_threads)


@pytest.mark.asyncio
async def test_answer_test_spends_one_budget_across_retrieval_and_generation():
    repository = InMemoryRagRepository()
    service = RagAdminService(
        repository,
        _Embeddings(),
        query_embeddings=_SlowQueryEmbeddings(),
        manufacturer="WEG",
        equipment_model="W22",
        acceptance_chat=_SlowChat(),
        query_timeout_seconds=0.1,
    )
    corpus = service.create_draft(
        asset_id="forzy-motor-01", min_relevance_score=0.2
    )
    await service.upload_document(
        corpus.corpus_id,
        filename="manual.pdf",
        content_type="application/pdf",
        payload=searchable_pdf("MAINTENANCE bearing lubrication"),
        metadata=_metadata(),
    )

    started = time.perf_counter()
    await asyncio.sleep(0.04)
    response, hits = await service.test_answer(
        corpus.corpus_id,
        "How should the bearing be lubricated?",
        operational=TrustedOperationalContext.unavailable(
            operational_state="unavailable"
        ),
        started_at=started,
    )
    elapsed = time.perf_counter() - started

    assert hits
    assert response.grounding_status == "manual_insufficient"
    assert response.fallback_used is False
    assert 0.1 <= elapsed < 0.19


@pytest.mark.asyncio
async def test_admin_uses_document_embeddings_for_ingestion_and_query_embeddings_for_tests():
    class TrackingEmbeddings(_Embeddings):
        def __init__(self):
            self.calls = []

        async def embed(self, texts):
            self.calls.append(tuple(texts))
            return await super().embed(texts)

    repository = InMemoryRagRepository()
    document_embeddings = TrackingEmbeddings()
    query_embeddings = TrackingEmbeddings()
    service = RagAdminService(
        repository,
        document_embeddings,
        query_embeddings=query_embeddings,
        manufacturer="WEG",
        equipment_model="W22",
    )
    corpus = service.create_draft(asset_id="forzy-motor-01")
    await service.upload_document(
        corpus.corpus_id,
        filename="manual.pdf",
        content_type="application/pdf",
        payload=searchable_pdf("MAINTENANCE bearing lubrication"),
        metadata=_metadata(),
    )

    await service.test_retrieval(corpus.corpus_id, "bearing", limit=6)

    assert len(document_embeddings.calls) == 1
    assert "bearing lubrication" in document_embeddings.calls[0][0]
    assert query_embeddings.calls == [("bearing",)]
