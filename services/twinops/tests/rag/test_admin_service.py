import pytest

from twinops.rag.admin_service import DuplicateDocumentError, RagAdminService
from twinops.rag.models import DocumentMetadata
from twinops.rag.repository import InMemoryRagRepository

from .pdf_factory import searchable_pdf


class _Embeddings:
    model = "embed-v1"
    dimensions = 3

    async def embed(self, texts):
        return tuple((0.1, 0.2, 0.3) for _ in texts)


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
    first = service.create_draft(asset_id="forzy-motor-01")
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
    second = service.create_draft(asset_id="forzy-motor-01")
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
