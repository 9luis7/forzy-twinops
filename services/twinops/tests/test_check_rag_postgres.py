from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_rag_postgres


MIGRATION_PATH = Path(__file__).parents[1] / "migrations" / "003_rag_asset_aware_v1.sql"
WRONG_MIGRATION = Path(__file__).parents[1] / "migrations" / "002_real_twin_v2.sql"
PREVIEW_ARGS = ["--target", "preview", "--migrate", str(MIGRATION_PATH)]
PRODUCTION_ARGS = ["--target", "production", "--migrate", str(MIGRATION_PATH)]
CONSTRAINTS = (
    ("rag_corpora", "rag_corpora_asset_check", "CHECK (asset_id = 'forzy-motor-01')"),
    ("rag_corpora", "rag_corpora_status_check", "CHECK (status IN ('draft','published'))"),
    ("rag_corpora", "rag_corpora_dimensions_check", "CHECK (embedding_dimensions > 0)"),
    ("rag_corpora", "rag_corpora_chunk_target_check", "CHECK (chunk_target_tokens > 0)"),
    ("rag_corpora", "rag_corpora_chunk_overlap_check", "CHECK (chunk_overlap_tokens >= 0 AND chunk_overlap_tokens < chunk_target_tokens)"),
    ("rag_corpora", "rag_corpora_relevance_check", "CHECK (min_relevance_score >= 0 AND min_relevance_score <= 1)"),
    ("rag_corpora", "rag_corpora_publication_check", "CHECK (status = 'draft' AND published_at IS NULL OR status = 'published' AND published_at IS NOT NULL)"),
    ("rag_corpora", "rag_corpora_manual_identity_key", "UNIQUE (corpus_id, manufacturer, equipment_model)"),
    ("rag_corpora", "rag_corpora_asset_identity_key", "UNIQUE (corpus_id, asset_id)"),
    ("rag_documents", "rag_documents_manual_identity_fkey", "FOREIGN KEY (corpus_id, manufacturer, equipment_model) REFERENCES rag_corpora(corpus_id, manufacturer, equipment_model)"),
    ("rag_documents", "rag_documents_sha_check", "CHECK (sha256 ~ '^[0-9a-f]{64}$')"),
    ("rag_documents", "rag_documents_pages_check", "CHECK (page_count >= 1 AND page_count <= 400)"),
    ("rag_documents", "rag_documents_coverage_check", "CHECK (coverage_pages >= 1 AND coverage_pages <= page_count)"),
    ("rag_documents", "rag_documents_identity_key", "UNIQUE (document_id, corpus_id)"),
    ("rag_documents", "rag_documents_corpus_sha_key", "UNIQUE (corpus_id, sha256)"),
    ("rag_chunks", "rag_chunks_corpus_fkey", "FOREIGN KEY (corpus_id) REFERENCES rag_corpora(corpus_id)"),
    ("rag_chunks", "rag_chunks_document_fkey", "FOREIGN KEY (document_id, corpus_id) REFERENCES rag_documents(document_id, corpus_id)"),
    ("rag_chunks", "rag_chunks_ordinal_check", "CHECK (ordinal >= 0)"),
    ("rag_chunks", "rag_chunks_text_check", "CHECK (text <> '')"),
    ("rag_chunks", "rag_chunks_page_start_check", "CHECK (page_start >= 1)"),
    ("rag_chunks", "rag_chunks_page_range_check", "CHECK (page_end >= page_start)"),
    ("rag_chunks", "rag_chunks_hash_check", "CHECK (content_hash ~ '^[0-9a-f]{64}$')"),
    ("rag_chunks", "rag_chunks_token_count_check", "CHECK (token_count > 0)"),
    ("rag_chunks", "rag_chunks_ordinal_key", "UNIQUE (corpus_id, document_id, ordinal)"),
    ("rag_active_corpus", "rag_active_corpus_pointer_fkey", "FOREIGN KEY (corpus_id, asset_id) REFERENCES rag_corpora(corpus_id, asset_id)"),
)


def _preview_env(database_url="postgresql://user:secret@database.invalid/twinops"):
    return {
        "DATABASE_URL": database_url,
        "RAG_PREVIEW_DATABASE_NAME": "twinops_preview",
        "RAG_PREVIEW_DATABASE_USER": "preview_user",
    }


def _production_env(database_url="postgresql://user:secret@database.invalid/twinops"):
    return {
        "DATABASE_URL": database_url,
        "RAG_PRODUCTION_DATABASE_NAME": "twinops_production",
        "RAG_PRODUCTION_DATABASE_USER": "production_user",
    }


class _Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(
        self,
        migration,
        *,
        approximate=0,
        constraints=CONSTRAINTS,
        fail_migration=False,
        identity=("twinops_preview", "preview_user"),
    ):
        self.migration = migration
        self.approximate = approximate
        self.constraints = constraints
        self.fail_migration = fail_migration
        self.calls = []
        self.rollbacks = 0
        self.identity = identity
        self.pgconn = SimpleNamespace(ssl_in_use=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None, **kwargs):
        self.calls.append((query, params, kwargs))
        if query == self.migration:
            if self.fail_migration:
                raise RuntimeError("secret migration failure")
            return _Rows()
        if "current_database()" in query:
            return _Rows([self.identity])
        if "FROM pg_extension" in query:
            return _Rows([("0.8.6",)])
        if "FROM pg_catalog.pg_tables" in query:
            return _Rows((name,) for name in (
                "rag_corpora", "rag_documents", "rag_chunks", "rag_active_corpus",
            ))
        if "FROM pg_catalog.pg_indexes" in query and "indexname = ANY" in query:
            return _Rows((name,) for name in (
                "rag_chunks_corpus_idx", "rag_chunks_search_vector_idx",
            ))
        if "indexdef ILIKE" in query:
            return _Rows([(self.approximate,)])
        if "pg_get_constraintdef" in query:
            return _Rows(self.constraints)
        raise AssertionError(f"unexpected query: {query}")

    def rollback(self):
        self.rollbacks += 1


def test_rag_checker_allowlists_only_migration_003_without_connecting(capsys):
    called = False

    def connect(_):
        nonlocal called
        called = True
        raise AssertionError("must not connect")

    result = check_rag_postgres.main(
        ["--target", "preview", "--migrate", str(WRONG_MIGRATION)],
        env={"DATABASE_URL": "postgresql://secret.invalid/db"},
        connect=connect,
    )

    assert result == 1
    assert called is False
    assert capsys.readouterr().err.strip() == "rag_postgres_check_failed error_type=ValueError"


def test_rag_checker_applies_allowlisted_migration_and_reports_sanitized_contract(capsys):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    connection = _Connection(migration)
    database_url = "postgresql://user:secret@database.invalid/twinops"

    result = check_rag_postgres.main(
        PREVIEW_ARGS,
        env=_preview_env(database_url),
        connect=lambda dsn: connection,
    )

    captured = capsys.readouterr()
    assert result == 0
    identity_index = next(
        index for index, (query, _, _) in enumerate(connection.calls)
        if "current_database()" in query
    )
    migration_index = next(
        index for index, (query, _, _) in enumerate(connection.calls)
        if query == migration
    )
    assert identity_index < migration_index
    assert connection.rollbacks == 0
    assert captured.out.strip() == (
        "rag_postgres_check_ok target=preview identity=true tables=4 "
        "indexes=2 constraints=true vector=true approximate_indexes=0 ssl=true"
    )
    assert database_url not in captured.out + captured.err


def test_rag_checker_applies_allowlisted_migration_to_explicit_production_target(capsys):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    connection = _Connection(
        migration,
        identity=("twinops_production", "production_user"),
    )
    database_url = "postgresql://production:secret@database.invalid/twinops"

    result = check_rag_postgres.main(
        PRODUCTION_ARGS,
        env=_production_env(database_url),
        connect=lambda dsn: connection,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip() == (
        "rag_postgres_check_ok target=production identity=true tables=4 "
        "indexes=2 constraints=true vector=true approximate_indexes=0 ssl=true"
    )
    assert database_url not in captured.out + captured.err


def test_rag_checker_fails_closed_on_approximate_index_without_leaking_dsn(capsys):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    database_url = "postgresql://user:secret@database.invalid/twinops"

    result = check_rag_postgres.main(
        PREVIEW_ARGS,
        env=_preview_env(database_url),
        connect=lambda dsn: _Connection(migration, approximate=1),
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.err.strip() == (
        "rag_postgres_check_failed error_type=RagPostgresCheckError stage=approximate_indexes"
    )
    assert database_url not in captured.err


def test_rag_checker_requires_external_preview_identity_allowlist_before_connecting(
    capsys,
):
    called = False

    def connect(_):
        nonlocal called
        called = True
        raise AssertionError("must not connect without an identity allowlist")

    result = check_rag_postgres.main(
        PREVIEW_ARGS,
        env={"DATABASE_URL": "postgresql://secret.invalid/db"},
        connect=connect,
    )

    assert result == 1
    assert called is False
    assert capsys.readouterr().err.strip() == (
        "rag_postgres_check_failed error_type=ValueError"
    )


def test_rag_checker_rolls_back_before_migration_when_database_identity_is_not_allowlisted(
    capsys,
):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    connection = _Connection(migration)
    database_url = "postgresql://production:secret@database.invalid/twinops"

    result = check_rag_postgres.main(
        PREVIEW_ARGS,
        env={
            "DATABASE_URL": database_url,
            "RAG_PREVIEW_DATABASE_NAME": "approved_preview",
            "RAG_PREVIEW_DATABASE_USER": "approved_preview_user",
        },
        connect=lambda dsn: connection,
    )

    captured = capsys.readouterr()
    assert result == 1
    assert connection.rollbacks == 1
    assert not any(query == migration for query, _, _ in connection.calls)
    assert "twinops_preview" not in captured.out + captured.err
    assert "preview_user" not in captured.out + captured.err
    assert database_url not in captured.out + captured.err


def test_rag_checker_rejects_tautological_relevance_constraint_and_rolls_back(capsys):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    constraints = tuple(
        (table, name, (
            "CHECK (min_relevance_score >= 0 OR min_relevance_score <= 1)"
            if "min_relevance_score" in definition
            else definition
        ))
        for table, name, definition in CONSTRAINTS
    )
    connection = _Connection(migration, constraints=constraints)

    result = check_rag_postgres.main(
        PREVIEW_ARGS,
        env=_preview_env(),
        connect=lambda dsn: connection,
    )

    assert result == 1
    assert connection.rollbacks == 1
    assert "stage=constraints" in capsys.readouterr().err


def test_rag_checker_rejects_definitions_swapped_between_named_constraints(capsys):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    definitions = {name: definition for _, name, definition in CONSTRAINTS}
    swapped = tuple(
        (
            table,
            name,
            (
                definitions["rag_corpora_chunk_overlap_check"]
                if name == "rag_corpora_relevance_check"
                else definitions["rag_corpora_relevance_check"]
                if name == "rag_corpora_chunk_overlap_check"
                else definition
            ),
        )
        for table, name, definition in CONSTRAINTS
    )
    connection = _Connection(migration, constraints=swapped)

    result = check_rag_postgres.main(
        PREVIEW_ARGS,
        env=_preview_env(),
        connect=lambda dsn: connection,
    )

    assert result == 1
    assert connection.rollbacks == 1
    assert "stage=constraints" in capsys.readouterr().err


def test_rag_checker_refuses_unknown_target_before_connecting(capsys):
    called = False

    def connect(_):
        nonlocal called
        called = True

    result = check_rag_postgres.main(
        ["--target", "staging", "--migrate", str(MIGRATION_PATH)],
        env={"DATABASE_URL": "postgresql://secret.invalid/db"},
        connect=connect,
    )

    assert result == 1
    assert called is False
    assert "error_type=ValueError" in capsys.readouterr().err


@pytest.mark.parametrize("failure", ["constraints", "migration"])
def test_rag_checker_rolls_back_migration_or_semantic_verification_failure(
    capsys, failure
):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    constraints = CONSTRAINTS[:-1] if failure == "constraints" else CONSTRAINTS
    connection = _Connection(
        migration,
        constraints=constraints,
        fail_migration=failure == "migration",
    )
    database_url = "postgresql://user:secret@database.invalid/twinops"

    result = check_rag_postgres.main(
        PREVIEW_ARGS,
        env=_preview_env(database_url),
        connect=lambda dsn: connection,
    )

    captured = capsys.readouterr()
    assert result == 1
    assert connection.rollbacks == 1
    assert database_url not in captured.out + captured.err
