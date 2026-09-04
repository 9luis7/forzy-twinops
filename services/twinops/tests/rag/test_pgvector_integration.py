import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from scripts.check_rag_postgres import _verify_constraints
from twinops.rag.models import RagChunk, RagCorpus, RagDocument
from twinops.rag.repository import PostgresRagRepository


DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
pytestmark = pytest.mark.postgres


def _skip_without_disposable_database():
    if not DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is required for disposable pgvector integration")


def _corpus(corpus_id):
    return RagCorpus.draft(
        corpus_id=corpus_id,
        asset_id="forzy-motor-01",
        manufacturer="WEG",
        equipment_model="W22",
        embedding_model="google/text-multilingual-embedding-002",
        embedding_dimensions=3,
        min_relevance_score=0.2,
    )


def _document(document_id, corpus_id, sha):
    return RagDocument(
        document_id=document_id,
        corpus_id=corpus_id,
        manufacturer="WEG",
        equipment_model="W22",
        revision="2026-01",
        language="en",
        source_url="https://manufacturer.example/manual.pdf",
        sha256=sha,
        page_count=1,
        coverage_pages=1,
    )


def _chunk(chunk_id, corpus_id, document_id, text, embedding):
    return RagChunk(
        chunk_id=chunk_id,
        corpus_id=corpus_id,
        document_id=document_id,
        ordinal=0,
        text=text,
        page_start=1,
        page_end=1,
        section="MAINTENANCE",
        content_hash="c" * 64,
        token_count=4,
        embedding=embedding,
    )


def test_migration_and_repository_flow_against_disposable_pgvector_database():
    _skip_without_disposable_database()
    migration = (
        Path(__file__).parents[2] / "migrations" / "003_rag_asset_aware_v1.sql"
    ).read_text(encoding="utf-8")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(migration)
        extension = connection.execute(
            "SELECT extversion FROM pg_extension WHERE extname='vector'"
        ).fetchone()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename LIKE 'rag_%'"
            ).fetchall()
        }
        approximate = connection.execute(
            "SELECT COUNT(*) FROM pg_indexes WHERE schemaname='public' "
            "AND (indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%ivfflat%')"
        ).fetchone()[0]
        constraint_kinds = {
            (row[0], row[1])
            for row in connection.execute(
                "SELECT rel.relname,con.contype FROM pg_constraint con "
                "JOIN pg_class rel ON rel.oid=con.conrelid "
                "JOIN pg_namespace ns ON ns.oid=rel.relnamespace "
                "WHERE ns.nspname='public' AND rel.relname LIKE 'rag_%'"
            ).fetchall()
        }
        constraint_definitions = connection.execute(
            "SELECT rel.relname,con.conname,pg_get_constraintdef(con.oid,true) "
            "FROM pg_constraint con "
            "JOIN pg_class rel ON rel.oid=con.conrelid "
            "JOIN pg_namespace ns ON ns.oid=rel.relnamespace "
            "WHERE ns.nspname='public' AND rel.relname LIKE 'rag_%'"
        ).fetchall()
    assert extension is not None
    assert tables == {"rag_corpora", "rag_documents", "rag_chunks", "rag_active_corpus"}
    assert approximate == 0
    assert {
        ("rag_corpora", "c"), ("rag_corpora", "p"), ("rag_corpora", "u"),
        ("rag_documents", "c"), ("rag_documents", "f"),
        ("rag_documents", "p"), ("rag_documents", "u"),
        ("rag_chunks", "c"), ("rag_chunks", "f"),
        ("rag_chunks", "p"), ("rag_chunks", "u"),
        ("rag_active_corpus", "f"), ("rag_active_corpus", "p"),
    } <= constraint_kinds
    _verify_constraints(constraint_definitions)

    repository = PostgresRagRepository(DATABASE_URL)
    corpus_ids = [str(uuid4()), str(uuid4())]
    for index, corpus_id in enumerate(corpus_ids):
        document_id = str(uuid4())
        repository.create_corpus(_corpus(corpus_id))
        repository.add_document(
            _document(document_id, corpus_id, str(index + 1) * 64),
            [
                _chunk(
                    str(uuid4()), corpus_id, document_id,
                    "bearing lubrication interval", (1.0, 0.0, 0.0),
                )
            ],
        )

    vector_hits = repository.exact_vector_search(
        corpus_ids[0], query_embedding=(1.0, 0.0, 0.0), limit=12
    )
    lexical_hits = repository.lexical_search(
        corpus_ids[0], query="bearing", limit=12
    )
    assert len(vector_hits) == len(lexical_hits) == 1
    assert vector_hits[0].chunk.corpus_id == corpus_ids[0]
    assert lexical_hits[0].document.equipment_model == "W22"

    first = repository.publish_corpus("forzy-motor-01", corpus_ids[0])
    second = repository.publish_corpus("forzy-motor-01", corpus_ids[1])
    rollback = repository.activate_published_corpus("forzy-motor-01", corpus_ids[0])
    assert first.previous_corpus_id is None
    assert second.previous_corpus_id == corpus_ids[0]
    assert rollback.previous_corpus_id == corpus_ids[1]
    assert repository.get_active_corpus("forzy-motor-01").corpus_id == corpus_ids[0]
