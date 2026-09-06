from dataclasses import replace

import pytest

from twinops.rag.admin_service import RagAdminService
from twinops.rag.errors import (
    CorpusCompatibilityError,
    CorpusNotFoundError,
    InvalidAdminInputError,
)
from twinops.rag.models import DocumentMetadata, RagChunk, RagCorpus, RagDocument
from twinops.rag.repository import InMemoryRagRepository

from .pdf_factory import searchable_pdf


MANUFACTURER = "Approved Manufacturer"
EQUIPMENT_MODEL = "Approved Model"


class _TrackingEmbeddings:
    def __init__(self, *, model="embed-v1", dimensions=3, failure=None):
        self.model = model
        self.dimensions = dimensions
        self.failure = failure
        self.calls = []

    async def embed(self, texts):
        self.calls.append(tuple(texts))
        if self.failure is not None:
            raise self.failure
        return tuple(tuple(0.1 for _ in range(self.dimensions)) for _ in texts)


def _service(repository, embeddings, **overrides):
    return RagAdminService(
        repository,
        embeddings,
        manufacturer=overrides.get("manufacturer", MANUFACTURER),
        equipment_model=overrides.get("equipment_model", EQUIPMENT_MODEL),
        embedding_batch_size=overrides.get("embedding_batch_size", 32),
    )


def _metadata(**overrides):
    values = {
        "manufacturer": MANUFACTURER,
        "equipment_model": EQUIPMENT_MODEL,
        "revision": "2026-01",
        "language": "en",
        "source_url": "https://manufacturer.example/manual.pdf",
    }
    values.update(overrides)
    return DocumentMetadata(**values)


@pytest.mark.asyncio
async def test_upload_model_mismatch_fails_before_pdf_or_gateway_work():
    repository = InMemoryRagRepository()
    original_embeddings = _TrackingEmbeddings(model="embed-v1", dimensions=3)
    corpus = _service(repository, original_embeddings).create_draft(
        asset_id="forzy-motor-01"
    )
    incompatible = _TrackingEmbeddings(model="embed-v2", dimensions=3)
    service = _service(repository, incompatible)

    with pytest.raises(CorpusCompatibilityError):
        await service.upload_document(
            corpus.corpus_id,
            filename="manual.pdf",
            content_type="application/pdf",
            payload=b"not-even-parsed",
            metadata=_metadata(),
        )

    assert incompatible.calls == []
    assert repository.coverage(corpus.corpus_id).document_count == 0


@pytest.mark.asyncio
async def test_retrieval_model_mismatch_fails_before_gateway_or_search():
    repository = InMemoryRagRepository()
    corpus = _service(
        repository, _TrackingEmbeddings(model="embed-v1", dimensions=3)
    ).create_draft(asset_id="forzy-motor-01")
    incompatible = _TrackingEmbeddings(model="embed-v2", dimensions=3)

    with pytest.raises(CorpusCompatibilityError):
        await _service(repository, incompatible).test_retrieval(
            corpus.corpus_id, "bearing", limit=6
        )

    assert incompatible.calls == []


@pytest.mark.asyncio
async def test_document_identity_must_match_corpus_before_embedding():
    repository = InMemoryRagRepository()
    embeddings = _TrackingEmbeddings()
    service = _service(repository, embeddings)
    corpus = service.create_draft(asset_id="forzy-motor-01")

    with pytest.raises(CorpusCompatibilityError):
        await service.upload_document(
            corpus.corpus_id,
            filename="manual.pdf",
            content_type="application/pdf",
            payload=searchable_pdf("searchable manual"),
            metadata=_metadata(equipment_model="Wrong Model"),
        )

    assert embeddings.calls == []
    assert repository.coverage(corpus.corpus_id).document_count == 0


@pytest.mark.asyncio
async def test_second_manual_cannot_mix_a_different_model_into_corpus():
    repository = InMemoryRagRepository()
    embeddings = _TrackingEmbeddings()
    service = _service(repository, embeddings)
    corpus = service.create_draft(asset_id="forzy-motor-01")
    await service.upload_document(
        corpus.corpus_id,
        filename="manual.pdf",
        content_type="application/pdf",
        payload=searchable_pdf("first searchable manual"),
        metadata=_metadata(),
    )

    with pytest.raises(CorpusCompatibilityError):
        await service.upload_document(
            corpus.corpus_id,
            filename="other-model.pdf",
            content_type="application/pdf",
            payload=searchable_pdf("second searchable manual"),
            metadata=_metadata(equipment_model="Wrong Model"),
        )

    assert repository.coverage(corpus.corpus_id).document_count == 1
    assert len(embeddings.calls) == 1


@pytest.mark.asyncio
async def test_chunk_character_limit_fails_before_gateway_work():
    repository = InMemoryRagRepository()
    embeddings = _TrackingEmbeddings()
    service = _service(repository, embeddings)
    corpus = service.create_draft(asset_id="forzy-motor-01")

    with pytest.raises(ValueError, match="characters"):
        await service.upload_document(
            corpus.corpus_id,
            filename="manual.pdf",
            content_type="application/pdf",
            payload=searchable_pdf("x" * 16_001),
            metadata=_metadata(),
        )

    assert embeddings.calls == []


def test_service_rejects_noncanonical_asset_and_invalid_batch_size():
    repository = InMemoryRagRepository()
    embeddings = _TrackingEmbeddings()
    service = _service(repository, embeddings)

    with pytest.raises(InvalidAdminInputError):
        service.create_draft(asset_id="other-motor")
    with pytest.raises(ValueError, match="batch"):
        _service(repository, embeddings, embedding_batch_size=0)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RagCorpus.draft(
            corpus_id="",
            asset_id="forzy-motor-01",
            manufacturer=MANUFACTURER,
            equipment_model=EQUIPMENT_MODEL,
            embedding_model="embed-v1",
            embedding_dimensions=3,
        ),
        lambda: RagCorpus.draft(
            corpus_id="c1",
            asset_id="other-motor",
            manufacturer=MANUFACTURER,
            equipment_model=EQUIPMENT_MODEL,
            embedding_model="embed-v1",
            embedding_dimensions=3,
        ),
        lambda: RagCorpus.draft(
            corpus_id="c1",
            asset_id="forzy-motor-01",
            manufacturer=MANUFACTURER,
            equipment_model=EQUIPMENT_MODEL,
            embedding_model="",
            embedding_dimensions=3,
        ),
        lambda: RagCorpus.draft(
            corpus_id="c1",
            asset_id="forzy-motor-01",
            manufacturer=MANUFACTURER,
            equipment_model=EQUIPMENT_MODEL,
            embedding_model="embed-v1",
            embedding_dimensions=3,
            min_relevance_score=float("nan"),
        ),
    ],
)
def test_corpus_domain_rejects_invalid_identity_and_version_anchors(factory):
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize(
    "changes",
    [
        {"manufacturer": ""},
        {"page_count": 0},
        {"coverage_pages": 2},
        {"source_url": "http://manufacturer.example/manual.pdf"},
    ],
)
def test_document_domain_matches_database_invariants(changes):
    values = {
        "document_id": "d1",
        "corpus_id": "c1",
        "manufacturer": MANUFACTURER,
        "equipment_model": EQUIPMENT_MODEL,
        "revision": "1",
        "language": "en",
        "source_url": "https://manufacturer.example/manual.pdf",
        "sha256": "a" * 64,
        "page_count": 1,
        "coverage_pages": 1,
    }
    values.update(changes)

    with pytest.raises(ValueError):
        RagDocument(**values)


@pytest.mark.parametrize(
    "changes",
    [
        {"ordinal": -1},
        {"text": ""},
        {"page_start": 0},
        {"page_end": 0},
        {"token_count": 0},
        {"embedding": (0.1, float("nan"), 0.3)},
    ],
)
def test_chunk_domain_and_fake_reject_invalid_records(changes):
    values = {
        "chunk_id": "x1",
        "corpus_id": "c1",
        "document_id": "d1",
        "ordinal": 0,
        "text": "bearing lubrication",
        "page_start": 1,
        "page_end": 1,
        "section": "MAINTENANCE",
        "content_hash": "b" * 64,
        "token_count": 2,
        "embedding": (0.1, 0.2, 0.3),
    }
    values.update(changes)

    with pytest.raises(ValueError):
        RagChunk(**values)


def test_fake_rejects_document_identity_mismatch_even_if_service_is_bypassed():
    repository = InMemoryRagRepository()
    corpus = RagCorpus.draft(
        corpus_id="c1",
        asset_id="forzy-motor-01",
        manufacturer=MANUFACTURER,
        equipment_model=EQUIPMENT_MODEL,
        embedding_model="embed-v1",
        embedding_dimensions=3,
    )
    repository.create_corpus(corpus)
    document = RagDocument(
        document_id="d1",
        corpus_id="c1",
        manufacturer=MANUFACTURER,
        equipment_model="Wrong Model",
        revision="1",
        language="en",
        source_url="https://manufacturer.example/manual.pdf",
        sha256="a" * 64,
        page_count=1,
        coverage_pages=1,
    )

    with pytest.raises(ValueError, match="identity"):
        repository.add_document(document, [])


@pytest.mark.asyncio
@pytest.mark.parametrize(("query", "limit"), [("", 6), ("x" * 501, 6), ("ok", 0), ("ok", 13)])
async def test_retrieval_validates_input_before_gateway(query, limit):
    repository = InMemoryRagRepository()
    embeddings = _TrackingEmbeddings()
    service = _service(repository, embeddings)
    corpus = service.create_draft(asset_id="forzy-motor-01")

    with pytest.raises(InvalidAdminInputError):
        await service.test_retrieval(corpus.corpus_id, query, limit=limit)

    assert embeddings.calls == []


@pytest.mark.asyncio
async def test_missing_corpus_retrieval_never_calls_gateway():
    embeddings = _TrackingEmbeddings()
    service = _service(InMemoryRagRepository(), embeddings)

    with pytest.raises(CorpusNotFoundError):
        await service.test_retrieval("missing", "bearing", limit=6)

    assert embeddings.calls == []


def test_corpus_status_and_timestamp_consistency_is_a_domain_invariant():
    draft = RagCorpus.draft(
        corpus_id="c1",
        asset_id="forzy-motor-01",
        manufacturer=MANUFACTURER,
        equipment_model=EQUIPMENT_MODEL,
        embedding_model="embed-v1",
        embedding_dimensions=3,
    )

    with pytest.raises(ValueError, match="publication time"):
        replace(draft, status="published")
