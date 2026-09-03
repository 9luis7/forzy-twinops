from pathlib import Path
from datetime import datetime, timezone

from twinops.rag.repository import PostgresRagRepository


class _Result:
    def __init__(self, *, one=None, all_rows=None):
        self._one = one
        self._all = [] if all_rows is None else all_rows

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class _Connection:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, parameters):
        self.calls.append((sql, parameters))
        if "FROM rag_corpora WHERE corpus_id" in sql:
            return _Result(
                one={
                    "corpus_id": "c1",
                    "asset_id": "forzy-motor-01",
                    "manufacturer": "Approved Manufacturer",
                    "equipment_model": "Approved Model",
                    "status": "draft",
                    "embedding_model": "embed-v1",
                    "embedding_dimensions": 3,
                    "chunk_target_tokens": 700,
                    "chunk_overlap_tokens": 100,
                    "min_relevance_score": 0.2,
                    "created_at": datetime(2026, 9, 3, tzinfo=timezone.utc),
                    "published_at": None,
                }
            )
        return _Result(all_rows=[])


class _ActivationConnection(_Connection):
    def execute(self, sql, parameters):
        self.calls.append((sql, parameters))
        if "FROM rag_corpora WHERE corpus_id" in sql:
            return _Result(
                one={
                    "corpus_id": "c2",
                    "asset_id": "forzy-motor-01",
                    "manufacturer": "Approved Manufacturer",
                    "equipment_model": "Approved Model",
                    "status": "draft",
                    "embedding_model": "embed-v2",
                    "embedding_dimensions": 3,
                    "chunk_target_tokens": 700,
                    "chunk_overlap_tokens": 100,
                    "min_relevance_score": 0.2,
                    "created_at": datetime(2026, 9, 3, tzinfo=timezone.utc),
                    "published_at": None,
                }
            )
        if "manufacturer<>" in sql:
            return _Result(one=None)
        if "SELECT 1 FROM rag_documents" in sql:
            return _Result(one={"exists": 1})
        if "FROM rag_active_corpus" in sql:
            return _Result(one={"corpus_id": "c1"})
        return _Result()


def test_postgres_preview_keeps_query_and_vector_out_of_sql_text():
    calls = []
    repository = PostgresRagRepository(
        "postgresql://unused",
        connection_factory=lambda: _Connection(calls),
    )
    untrusted_query = "bearing'); DROP TABLE rag_chunks; --"

    repository.preview_search(
        "c1",
        query=untrusted_query,
        query_embedding=(0.1, 0.2, 0.3),
        limit=6,
    )

    search_sql, parameters = calls[-1]
    assert untrusted_query not in search_sql
    assert untrusted_query in parameters
    assert "%s::vector" in search_sql
    assert parameters[-1] == 6


def test_migration_is_additive_enables_pgvector_and_has_no_approximate_index():
    migration = (
        Path(__file__).parents[2]
        / "migrations"
        / "003_rag_asset_aware_v1.sql"
    ).read_text(encoding="utf-8")
    normalized = migration.lower()

    assert "create extension if not exists vector" in normalized
    for table in (
        "rag_corpora",
        "rag_documents",
        "rag_chunks",
        "rag_active_corpus",
    ):
        assert f"create table if not exists {table}" in normalized
    assert "using gin" in normalized
    assert "manufacturer text not null" in normalized
    assert "equipment_model text not null" in normalized
    assert "foreign key (corpus_id, manufacturer, equipment_model)" in normalized
    assert "check (asset_id = 'forzy-motor-01')" in normalized
    assert "foreign key (corpus_id, asset_id)" in normalized
    assert "using hnsw" not in normalized
    assert "using ivfflat" not in normalized
    assert "drop table" not in normalized
    assert "alter table" not in normalized


def test_postgres_publication_serializes_pointer_changes_by_asset():
    calls = []
    repository = PostgresRagRepository(
        "postgresql://unused",
        connection_factory=lambda: _ActivationConnection(calls),
    )

    changed = repository.publish_corpus("forzy-motor-01", "c2")

    lock_index = next(
        index
        for index, (sql, _) in enumerate(calls)
        if "pg_advisory_xact_lock" in sql
    )
    pointer_read_index = next(
        index
        for index, (sql, _) in enumerate(calls)
        if "FROM rag_active_corpus" in sql
    )
    assert lock_index < pointer_read_index
    assert calls[lock_index][1] == ("forzy-motor-01",)
    assert any("manufacturer<>" in sql for sql, _ in calls)
    assert changed.previous_corpus_id == "c1"
