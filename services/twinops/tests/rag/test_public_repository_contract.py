from datetime import datetime, timezone
from unittest.mock import Mock

from twinops.rag import repository as repository_module
from twinops.rag.repository import PostgresRagRepository, _lexical_websearch_query


class _Result:
    def __init__(self, *, one=None, rows=None):
        self.one = one
        self.rows = [] if rows is None else rows

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, calls):
        self.calls = calls
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.closed = True
        return False

    def execute(self, sql, parameters):
        self.calls.append((sql, parameters))
        if (
            "SELECT r.* FROM rag_active_corpus" in sql
            or "SELECT * FROM rag_corpora WHERE corpus_id" in sql
        ):
            return _Result(one=_corpus_row())
        return _Result(rows=[])


def _corpus_row():
    return {
        "corpus_id": "00000000-0000-4000-8000-000000000001",
        "asset_id": "forzy-motor-01",
        "manufacturer": "WEG",
        "equipment_model": "W22",
        "status": "published",
        "embedding_model": "embed-v1",
        "embedding_dimensions": 3,
        "chunk_target_tokens": 700,
        "chunk_overlap_tokens": 100,
        "min_relevance_score": 0.2,
        "created_at": datetime(2026, 9, 3, tzinfo=timezone.utc),
        "published_at": datetime(2026, 9, 3, tzinfo=timezone.utc),
    }


def test_postgres_vector_search_is_exact_parameterized_and_limited_to_12():
    calls = []
    repository = PostgresRagRepository(
        "postgresql://unused", connection_factory=lambda: _Connection(calls)
    )

    repository.exact_vector_search(
        "00000000-0000-4000-8000-000000000001",
        query_embedding=(0.1, 0.2, 0.3),
        limit=12,
    )

    sql, parameters = calls[-1]
    assert "embedding <=> %s::vector" in sql
    assert "hnsw" not in sql.casefold()
    assert "ivfflat" not in sql.casefold()
    assert parameters[-1] == 12


def test_postgres_lexical_search_filters_with_simple_websearch_and_parameters():
    calls = []
    repository = PostgresRagRepository(
        "postgresql://unused", connection_factory=lambda: _Connection(calls)
    )
    untrusted = "bearing'); DROP TABLE rag_chunks; --"

    repository.lexical_search(
        "00000000-0000-4000-8000-000000000001",
        query=untrusted,
        limit=12,
    )

    sql, parameters = calls[-1]
    normalized = " ".join(sql.split())
    assert "search_vector @@ websearch_to_tsquery('simple',%s)" in normalized
    assert untrusted not in sql
    assert parameters[0] == "bearing OR drop OR table OR rag_chunks"
    assert parameters[2] == parameters[0]
    assert parameters[-1] == 12


def test_lexical_query_uses_informative_or_terms_for_natural_language():
    assert _lexical_websearch_query(
        "Que verificações documentadas existem para aquecimento excessivo?"
    ) == "verificações OR documentadas OR aquecimento OR excessivo"


def test_each_public_db_operation_sets_local_statement_timeout_and_closes_connection():
    connections = []

    def connection_factory():
        connection = _Connection([])
        connections.append(connection)
        return connection

    repository = PostgresRagRepository(
        "postgresql://unused",
        connection_factory=connection_factory,
        statement_timeout_ms=250,
    )

    repository.get_active_corpus("forzy-motor-01")
    repository.exact_vector_search(
        "00000000-0000-4000-8000-000000000001",
        query_embedding=(0.1, 0.2, 0.3),
        limit=12,
    )
    repository.lexical_search(
        "00000000-0000-4000-8000-000000000001",
        query="bearing",
        limit=12,
    )

    assert connections
    for connection in connections:
        first_sql, first_parameters = connection.calls[0]
        assert "set_config('statement_timeout'" in first_sql
        assert first_parameters == ("250",)
        assert connection.closed is True


def test_rag_postgres_connect_is_bounded_before_statement_timeout(monkeypatch):
    connection = _Connection([])
    connect = Mock(return_value=connection)
    monkeypatch.setattr(repository_module.psycopg, "connect", connect)
    repository = PostgresRagRepository(
        "redacted",
        connect_timeout_seconds=2,
        statement_timeout_ms=2_000,
    )

    with repository._connection():
        pass

    connect.assert_called_once_with(
        "redacted",
        row_factory=repository_module.dict_row,
        connect_timeout=2,
    )
    assert connection.closed is True
