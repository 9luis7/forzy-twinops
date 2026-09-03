from dataclasses import replace

import pytest

from twinops.rag.models import RagChunk, RagCorpus, RagDocument
from twinops.rag.repository import InMemoryRagRepository


def _corpus(corpus_id, *, asset_id="forzy-motor-01", model="embed-v1", dimension=3):
    return RagCorpus.draft(
        corpus_id=corpus_id,
        asset_id=asset_id,
        manufacturer="WEG",
        equipment_model="W22",
        embedding_model=model,
        embedding_dimensions=dimension,
    )


def _document(document_id, corpus_id, sha256):
    return RagDocument(
        document_id=document_id,
        corpus_id=corpus_id,
        manufacturer="WEG",
        equipment_model="W22",
        revision="1",
        language="en",
        source_url="https://manufacturer.example/manual.pdf",
        sha256=sha256,
        page_count=1,
        coverage_pages=1,
    )


def _chunk(chunk_id, corpus_id, document_id, embedding):
    return RagChunk(
        chunk_id=chunk_id,
        corpus_id=corpus_id,
        document_id=document_id,
        ordinal=0,
        text="bearing lubrication",
        page_start=1,
        page_end=1,
        section="MAINTENANCE",
        content_hash="a" * 64,
        token_count=2,
        embedding=embedding,
    )


def test_repository_rejects_duplicate_document_sha256():
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1"))
    repository.add_document(_document("d1", "c1", "a" * 64), [])

    with pytest.raises(ValueError, match="duplicate"):
        repository.add_document(_document("d2", "c1", "a" * 64), [])


def test_same_document_sha_can_be_reindexed_in_a_new_corpus_version():
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1", model="embed-v1", dimension=3))
    repository.create_corpus(_corpus("c2", model="embed-v2", dimension=2))

    repository.add_document(_document("d1", "c1", "a" * 64), [])
    repository.add_document(_document("d2", "c2", "a" * 64), [])

    assert repository.coverage("c1").document_count == 1
    assert repository.coverage("c2").document_count == 1


def test_repository_isolates_chunks_by_corpus_model_and_dimension():
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1", model="embed-v1", dimension=3))
    repository.create_corpus(_corpus("c2", model="embed-v2", dimension=2))
    document = _document("d1", "c1", "a" * 64)

    with pytest.raises(ValueError, match="dimension"):
        repository.add_document(
            document,
            [_chunk("x", "c1", "d1", (0.1, 0.2))],
        )
    with pytest.raises(ValueError, match="corpus"):
        repository.add_document(
            document,
            [_chunk("x", "c2", "d1", (0.1, 0.2))],
        )


def test_publish_and_rollback_swap_active_pointer_without_mutating_versions():
    repository = InMemoryRagRepository()
    for corpus_id, sha in (("c1", "a" * 64), ("c2", "b" * 64)):
        repository.create_corpus(_corpus(corpus_id))
        repository.add_document(_document(f"d-{corpus_id}", corpus_id, sha), [])

    first = repository.publish_corpus("forzy-motor-01", "c1")
    second = repository.publish_corpus("forzy-motor-01", "c2")
    rolled_back = repository.activate_published_corpus("forzy-motor-01", "c1")

    assert first.previous_corpus_id is None
    assert second.previous_corpus_id == "c1"
    assert rolled_back.previous_corpus_id == "c2"
    assert repository.get_active_corpus("forzy-motor-01").corpus_id == "c1"
    assert repository.get_corpus("c1").status == "published"
    assert repository.get_corpus("c2").status == "published"


def test_draft_cannot_be_activated_as_a_rollback():
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1"))

    with pytest.raises(ValueError, match="published"):
        repository.activate_published_corpus("forzy-motor-01", "c1")


def test_published_version_must_use_explicit_reactivation_path():
    repository = InMemoryRagRepository()
    repository.create_corpus(_corpus("c1"))
    repository.add_document(_document("d1", "c1", "a" * 64), [])
    repository.publish_corpus("forzy-motor-01", "c1")

    with pytest.raises(ValueError, match="draft"):
        repository.publish_corpus("forzy-motor-01", "c1")


def test_coverage_and_preview_search_are_scoped_to_requested_corpus():
    repository = InMemoryRagRepository()
    for corpus_id, sha, text in (
        ("c1", "a" * 64, "bearing lubrication"),
        ("c2", "b" * 64, "electrical isolation"),
    ):
        repository.create_corpus(_corpus(corpus_id))
        document = _document(f"d-{corpus_id}", corpus_id, sha)
        chunk = replace(
            _chunk(f"x-{corpus_id}", corpus_id, document.document_id, (0.1, 0.2, 0.3)),
            text=text,
        )
        repository.add_document(document, [chunk])

    assert repository.coverage("c1").chunk_count == 1
    results = repository.preview_search(
        "c1", query="bearing", query_embedding=(0.1, 0.2, 0.3), limit=6
    )
    assert [item.corpus_id for item in results] == ["c1"]
    assert [item.text for item in results] == ["bearing lubrication"]
