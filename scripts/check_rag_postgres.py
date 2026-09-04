"""Apply and verify only RAG migration 003 against an explicit Preview target."""

import argparse
from collections.abc import Callable, Mapping, Sequence
import os
from pathlib import Path
import re
import sys

import psycopg


_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_MIGRATION = (
    _ROOT / "services" / "twinops" / "migrations" / "003_rag_asset_aware_v1.sql"
)
_TABLES = {"rag_corpora", "rag_documents", "rag_chunks", "rag_active_corpus"}
_INDEXES = {"rag_chunks_corpus_idx", "rag_chunks_search_vector_idx"}
_EXPECTED_CONSTRAINTS = {
    ("rag_corpora", "rag_corpora_asset_check"):
        "CHECK (asset_id = 'forzy-motor-01')",
    ("rag_corpora", "rag_corpora_status_check"):
        "CHECK (status IN ('draft','published'))",
    ("rag_corpora", "rag_corpora_dimensions_check"):
        "CHECK (embedding_dimensions > 0)",
    ("rag_corpora", "rag_corpora_chunk_target_check"):
        "CHECK (chunk_target_tokens > 0)",
    ("rag_corpora", "rag_corpora_chunk_overlap_check"):
        "CHECK (chunk_overlap_tokens >= 0 AND chunk_overlap_tokens < chunk_target_tokens)",
    ("rag_corpora", "rag_corpora_relevance_check"):
        "CHECK (min_relevance_score >= 0 AND min_relevance_score <= 1)",
    ("rag_corpora", "rag_corpora_publication_check"):
        "CHECK (status = 'draft' AND published_at IS NULL OR "
        "status = 'published' AND published_at IS NOT NULL)",
    ("rag_corpora", "rag_corpora_manual_identity_key"):
        "UNIQUE (corpus_id, manufacturer, equipment_model)",
    ("rag_corpora", "rag_corpora_asset_identity_key"):
        "UNIQUE (corpus_id, asset_id)",
    ("rag_documents", "rag_documents_manual_identity_fkey"):
        "FOREIGN KEY (corpus_id, manufacturer, equipment_model) "
        "REFERENCES rag_corpora(corpus_id, manufacturer, equipment_model)",
    ("rag_documents", "rag_documents_sha_check"):
        "CHECK (sha256 ~ '^[0-9a-f]{64}$')",
    ("rag_documents", "rag_documents_pages_check"):
        "CHECK (page_count >= 1 AND page_count <= 400)",
    ("rag_documents", "rag_documents_coverage_check"):
        "CHECK (coverage_pages >= 1 AND coverage_pages <= page_count)",
    ("rag_documents", "rag_documents_identity_key"):
        "UNIQUE (document_id, corpus_id)",
    ("rag_documents", "rag_documents_corpus_sha_key"):
        "UNIQUE (corpus_id, sha256)",
    ("rag_chunks", "rag_chunks_corpus_fkey"):
        "FOREIGN KEY (corpus_id) REFERENCES rag_corpora(corpus_id)",
    ("rag_chunks", "rag_chunks_document_fkey"):
        "FOREIGN KEY (document_id, corpus_id) "
        "REFERENCES rag_documents(document_id, corpus_id)",
    ("rag_chunks", "rag_chunks_ordinal_check"): "CHECK (ordinal >= 0)",
    ("rag_chunks", "rag_chunks_text_check"): "CHECK (text <> '')",
    ("rag_chunks", "rag_chunks_page_start_check"): "CHECK (page_start >= 1)",
    ("rag_chunks", "rag_chunks_page_range_check"):
        "CHECK (page_end >= page_start)",
    ("rag_chunks", "rag_chunks_hash_check"):
        "CHECK (content_hash ~ '^[0-9a-f]{64}$')",
    ("rag_chunks", "rag_chunks_token_count_check"): "CHECK (token_count > 0)",
    ("rag_chunks", "rag_chunks_ordinal_key"):
        "UNIQUE (corpus_id, document_id, ordinal)",
    ("rag_active_corpus", "rag_active_corpus_pointer_fkey"):
        "FOREIGN KEY (corpus_id, asset_id) "
        "REFERENCES rag_corpora(corpus_id, asset_id)",
}


class RagPostgresCheckError(RuntimeError):
    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage


def _arguments(argv: Sequence[str] | None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--migrate", required=True, type=Path)
    arguments = parser.parse_args(argv)
    if arguments.target != "preview":
        raise ValueError("only the preview target is allowed")
    if arguments.migrate.resolve() != _EXPECTED_MIGRATION.resolve():
        raise ValueError("unexpected migration path")
    return arguments


def _normalize_constraint(definition: str) -> str:
    value = definition.casefold().replace('"', "")
    value = re.sub(
        r"::(?:text|bpchar|uuid|integer|double precision|character varying)",
        "",
        value,
    )
    value = re.sub(
        r"([a-z_][a-z0-9_]*)\s*=\s*any\s*\(\s*array\s*\[([^]]+)]\s*\)",
        r"\1 in (\2)",
        value,
    )
    value = re.sub(r"\s*,\s*", ",", value)
    return " ".join(value.split())


def _verify_constraints(rows) -> None:
    actual: dict[tuple[str, str], str] = {}
    for table, name, definition in rows:
        key = (table, name)
        if key in actual:
            raise RagPostgresCheckError("constraints")
        actual[key] = _normalize_constraint(definition)
    expected = {
        key: _normalize_constraint(definition)
        for key, definition in _EXPECTED_CONSTRAINTS.items()
    }
    if any(actual.get(key) != definition for key, definition in expected.items()):
        raise RagPostgresCheckError("constraints")


def _rollback_safely(connection) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _verify(
    database_url: str,
    migration_path: Path,
    expected_identity: tuple[str, str],
    connect,
) -> None:
    with connect(database_url) as connection:
        try:
            if connection.pgconn.ssl_in_use is not True:
                raise RagPostgresCheckError("tls")
            identity = connection.execute(
                "SELECT current_database(), current_user"
            ).fetchone()
            if identity != expected_identity:
                raise RagPostgresCheckError("target_identity")
            connection.execute(
                migration_path.read_text(encoding="utf-8"), prepare=False
            )
            extension = connection.execute(
                "SELECT extversion FROM pg_extension WHERE extname='vector'"
            ).fetchone()
            if extension is None:
                raise RagPostgresCheckError("vector_extension")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT tablename FROM pg_catalog.pg_tables "
                    "WHERE schemaname='public' AND tablename = ANY(%s)",
                    (sorted(_TABLES),),
                ).fetchall()
            }
            if tables != _TABLES:
                raise RagPostgresCheckError("tables")
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT indexname FROM pg_catalog.pg_indexes "
                    "WHERE schemaname='public' AND indexname = ANY(%s)",
                    (sorted(_INDEXES),),
                ).fetchall()
            }
            if indexes != _INDEXES:
                raise RagPostgresCheckError("indexes")
            approximate = connection.execute(
                "SELECT COUNT(*) FROM pg_catalog.pg_indexes WHERE schemaname='public' "
                "AND (indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%ivfflat%')"
            ).fetchone()
            if approximate != (0,):
                raise RagPostgresCheckError("approximate_indexes")
            constraints = connection.execute(
                "SELECT rel.relname,con.conname,pg_get_constraintdef(con.oid,true) "
                "FROM pg_catalog.pg_constraint con "
                "JOIN pg_catalog.pg_class rel ON rel.oid=con.conrelid "
                "JOIN pg_catalog.pg_namespace ns ON ns.oid=rel.relnamespace "
                "WHERE ns.nspname='public' AND rel.relname = ANY(%s)",
                (sorted(_TABLES),),
            ).fetchall()
            _verify_constraints(constraints)
        except Exception:
            _rollback_safely(connection)
            raise


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    connect: Callable[..., object] = psycopg.connect,
) -> int:
    try:
        arguments = _arguments(argv)
        source_env = os.environ if env is None else env
        database_url = source_env.get("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        expected_database = source_env.get("RAG_PREVIEW_DATABASE_NAME", "").strip()
        expected_user = source_env.get("RAG_PREVIEW_DATABASE_USER", "").strip()
        if not expected_database or not expected_user:
            raise ValueError("Preview database identity allowlist is required")
        _verify(
            database_url,
            arguments.migrate,
            (expected_database, expected_user),
            connect,
        )
        print(
            "rag_postgres_check_ok target=preview identity=true tables=4 "
            "indexes=2 constraints=true vector=true approximate_indexes=0 ssl=true"
        )
        return 0
    except Exception as exc:
        stage = f" stage={exc.stage}" if isinstance(exc, RagPostgresCheckError) else ""
        print(
            f"rag_postgres_check_failed error_type={type(exc).__name__}{stage}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
