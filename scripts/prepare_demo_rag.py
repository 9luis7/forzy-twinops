"""Reindex the approved WEG PDF in the dedicated demo database; offline by default.

No environment file is loaded. Execution requires an operator's verification of
the exact Gemini account's free tier, not merely a free-tier model name. Schema
migrations belong to deployment preparation and are never applied here.
"""

import argparse
import asyncio
from contextlib import contextmanager
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, unquote, urlsplit
from uuid import UUID, uuid4

import httpx
import psycopg
from psycopg.rows import dict_row

from twinops.rag.admin_service import RagAdminService
from twinops.rag.chunking import chunk_pages
from twinops.rag.embeddings import GeminiEmbeddingClient
from twinops.rag.models import CANONICAL_RAG_ASSET_ID, DocumentMetadata, RagCorpus
from twinops.rag.pdf import MAX_PDF_BYTES, extract_searchable_pdf
from twinops.rag.repository import PostgresRagRepository


PDF_SHA256 = "0eb6265cc1bafc7ed90d4cd91f64e87597063b841836373f951e7e753bad10d0"
PAGE_COUNT = 233
CHUNK_COUNT = 117
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768
GENERATION_MODEL = "gemini-3.5-flash-lite"
THRESHOLD = 0.5897445762442176
SOURCE_URL = (
    "https://static.weg.net/medias/downloadcenter/ha6/h39/"
    "WEG-WMO-safe-area-50033244-manual-pt-en-es.pdf"
)
OLD_CORPUS_IDS = {
    "4fc8063f-aa3a-4283-8b14-2f54bf08358c",
    "56f0e62f-4308-4b70-9b82-a73cb2075e83",
}
METADATA = DocumentMetadata(
    manufacturer="WEG", equipment_model="W22",
    revision="50033244 Rev. 43 04/2026", language="pt,en,es",
    source_url=SOURCE_URL,
)


class PreparationError(ValueError):
    """Fixed safe operator error code; never include external error text."""


def preflight(source: Path):
    if source.stat().st_size > MAX_PDF_BYTES:
        raise PreparationError("manual_size_invalid")
    payload = source.read_bytes()
    if sha256(payload).hexdigest() != PDF_SHA256:
        raise PreparationError("manual_hash_mismatch")
    extracted = extract_searchable_pdf(payload, content_type="application/pdf")
    drafts = chunk_pages(extracted.pages, target_tokens=700, overlap_tokens=100)
    if (extracted.page_count, extracted.coverage_pages, len(drafts)) != (
        PAGE_COUNT, PAGE_COUNT, CHUNK_COUNT
    ):
        raise PreparationError("manual_coverage_mismatch")
    return payload, drafts


def validate_execution(env, *, project_ref, free_tier_verified, corpus_id):
    if not free_tier_verified:
        raise PreparationError("exact_gemini_account_free_tier_verification_required")
    if not project_ref or re.fullmatch(r"[a-z0-9]{20}", project_ref) is None:
        raise PreparationError("expected_supabase_project_ref_required")
    try:
        parsed_id = UUID(corpus_id)
        if parsed_id.version != 4 or str(parsed_id) != corpus_id or corpus_id in OLD_CORPUS_IDS:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise PreparationError("new_corpus_uuid4_required") from None
    url = env.get("DEMO_DATABASE_URL", "")
    try:
        parsed = urlsplit(url)
        query = parse_qsl(parsed.query, strict_parsing=True)
        host = parsed.hostname or ""
        direct = host == f"db.{project_ref}.supabase.co" and parsed.port in (None, 5432)
        pooled = (
            host.endswith(".pooler.supabase.com")
            and re.fullmatch(r"[a-z0-9.-]+", host) is not None
            and parsed.port == 5432
        )
        user = unquote(parsed.username or "")
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or not (direct or pooled)
            or user != ("postgres" if direct else f"postgres.{project_ref}")
            or not parsed.password or parsed.path != "/postgres" or parsed.fragment
            or len(query) != 1 or query[0][0] != "sslmode"
            or query[0][1] not in {"require", "verify-full"}
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise PreparationError("dedicated_supabase_session_5432_tls_url_required") from None
    expected = {
        "TWINOPS_RAG_PROVIDER": "gemini",
        "TWINOPS_RAG_EMBEDDING_MODEL": EMBEDDING_MODEL,
        "TWINOPS_RAG_EMBEDDING_DIMENSIONS": str(EMBEDDING_DIMENSIONS),
        "TWINOPS_RAG_GENERATION_MODEL": GENERATION_MODEL,
    }
    if any(env.get(key, value) != value for key, value in expected.items()):
        raise PreparationError("configured_model_incompatible")
    if not env.get("GEMINI_API_KEY", "").strip():
        raise PreparationError("gemini_credential_required")
    return url


def desired_corpus(corpus_id):
    return RagCorpus.draft(
        corpus_id=corpus_id, asset_id=CANONICAL_RAG_ASSET_ID,
        manufacturer=METADATA.manufacturer, equipment_model=METADATA.equipment_model,
        embedding_model=EMBEDDING_MODEL, embedding_dimensions=EMBEDDING_DIMENSIONS,
        chunk_target_tokens=700, chunk_overlap_tokens=100,
        min_relevance_score=THRESHOLD,
    )


def verify_chunks(rows, drafts, document_id):
    """Validate exact text/provenance and vector dimensions without exporting them."""
    if len(rows) != len(drafts):
        raise PreparationError("persisted_chunk_count_mismatch")
    manifest = []
    seen = set()
    for row, draft in zip(rows, drafts, strict=True):
        chunk_id = str(row["chunk_id"])
        if (
            chunk_id in seen or str(row["document_id"]) != document_id
            or row["ordinal"] != draft.ordinal or row["text"] != draft.text
            or row["content_hash"] != draft.content_hash
            or sha256(row["text"].encode("utf-8")).hexdigest() != draft.content_hash
            or (row["page_start"], row["page_end"]) != (draft.page_start, draft.page_end)
            or row["section"] != draft.section or row["token_count"] != draft.token_count
            or row["dimensions"] != EMBEDDING_DIMENSIONS
        ):
            raise PreparationError("persisted_chunk_provenance_mismatch")
        seen.add(chunk_id)
        manifest.append({
            "chunkId": chunk_id, "documentId": document_id, "ordinal": draft.ordinal,
            "contentHash": draft.content_hash, "pageStart": draft.page_start,
            "pageEnd": draft.page_end,
        })
    return manifest


async def prepare(repository, embeddings, *, corpus_id, payload, drafts, read_chunks, publish=False):
    """Caller holds the dedicated DB lock. Persisted uploads are reused on retry."""
    desired = desired_corpus(corpus_id)
    corpus = repository.get_corpus(corpus_id)
    if corpus is None:
        if repository.get_active_corpus(CANONICAL_RAG_ASSET_ID) is not None:
            raise PreparationError("active_corpus_exists_use_its_id_or_review_replacement")
        corpus = repository.create_corpus(desired)
    if any(getattr(corpus, field) != getattr(desired, field) for field in (
        "asset_id", "manufacturer", "equipment_model", "embedding_model",
        "embedding_dimensions", "chunk_target_tokens", "chunk_overlap_tokens", "min_relevance_score",
    )):
        raise PreparationError("existing_corpus_incompatible")
    service = RagAdminService(
        repository, embeddings, manufacturer="WEG", equipment_model="W22",
    )
    document = repository.find_document_by_sha256(corpus_id, PDF_SHA256)
    reused = document is not None
    if document is None:
        if corpus.status != "draft" or repository.coverage(corpus_id).document_count:
            raise PreparationError("existing_corpus_not_empty_draft")
        uploaded = await service.upload_document(
            corpus_id, filename="WEG-50033244-rev43-pt-en-es.pdf",
            content_type="application/pdf", payload=payload, metadata=METADATA,
        )
        document = uploaded.document
    if any(getattr(document, field) != getattr(METADATA, field) for field in (
        "manufacturer", "equipment_model", "revision", "language", "source_url",
    )):
        raise PreparationError("persisted_document_provenance_mismatch")
    coverage = repository.coverage(corpus_id)
    if (coverage.document_count, coverage.page_count, coverage.coverage_pages, coverage.chunk_count) != (
        1, PAGE_COUNT, PAGE_COUNT, CHUNK_COUNT
    ):
        raise PreparationError("persisted_coverage_mismatch")
    manifest = verify_chunks(read_chunks(corpus_id), drafts, document.document_id)
    active = repository.get_active_corpus(CANONICAL_RAG_ASSET_ID)
    if publish:
        if active is not None and active.corpus_id != corpus_id:
            raise PreparationError("active_corpus_replacement_requires_separate_review")
        if corpus.status == "draft":
            service.publish(corpus_id)
        elif active is None or active.corpus_id != corpus_id:
            raise PreparationError("published_corpus_inactive_use_explicit_rollback_tool")
    active = repository.get_active_corpus(CANONICAL_RAG_ASSET_ID)
    return {
        "mode": "execute", "corpusId": corpus_id, "documentId": document.document_id,
        "documentSha256": PDF_SHA256, "pages": PAGE_COUNT, "chunkCount": CHUNK_COUNT,
        "embeddingModel": EMBEDDING_MODEL, "embeddingDimensions": EMBEDDING_DIMENSIONS,
        "generationModel": GENERATION_MODEL, "generationCalled": False,
        "sourceUrl": SOURCE_URL, "revision": METADATA.revision,
        "minRelevanceScore": THRESHOLD, "reusedDocument": reused,
        "status": repository.get_corpus(corpus_id).status,
        "active": active is not None and active.corpus_id == corpus_id,
        "citationProvenanceVerified": True, "retrievalAcceptancePending": True,
        "chunks": manifest,
    }


@contextmanager
def target_connection(url):
    # Explicit driver settings; execution uses the approved session pooler only.
    with psycopg.connect(
        url, connect_timeout=10, row_factory=dict_row, prepare_threshold=None,
    ) as connection:
        if not connection.pgconn.ssl_in_use:
            raise PreparationError("database_tls_not_active")
        connection.execute("SELECT set_config('statement_timeout', '30000', true)")
        yield connection


@contextmanager
def locked_target(url):
    # The lock spans calls from this script, including external embedding work.
    # Repository writes use their own short transactions; no schema is created.
    with target_connection(url) as connection:
        row = connection.execute("SELECT current_database() AS db").fetchone()
        if row["db"] != "postgres":
            raise PreparationError("database_identity_mismatch")
        row = connection.execute(
            "SELECT pg_try_advisory_xact_lock(%s) AS acquired", (73190508117,)
        ).fetchone()
        if not row["acquired"]:
            raise PreparationError("another_demo_reindex_is_running")
        yield connection


async def execute(args, env, payload, drafts):
    url = validate_execution(
        env, project_ref=args.expected_project_ref,
        free_tier_verified=args.gemini_free_tier_verified, corpus_id=args.corpus_id,
    )
    with locked_target(url) as connection:
        repository = PostgresRagRepository(
            url, connection_factory=lambda: target_connection(url),
            connect_timeout_seconds=10, statement_timeout_ms=30000,
        )

        def read_chunks(corpus_id):
            return connection.execute(
                "SELECT chunk_id,document_id,ordinal,text,page_start,page_end,section,"
                "content_hash,token_count,vector_dims(embedding) AS dimensions "
                "FROM rag_chunks WHERE corpus_id=%s ORDER BY ordinal", (corpus_id,),
            ).fetchall()

        async with httpx.AsyncClient(trust_env=False) as http:
            embeddings = GeminiEmbeddingClient(
                http, api_key=env["GEMINI_API_KEY"], model=EMBEDDING_MODEL,
                dimensions=EMBEDDING_DIMENSIONS, task_type="RETRIEVAL_DOCUMENT",
                timeout_seconds=30, max_rate_limit_retries=0,
            )
            return await prepare(
                repository, embeddings, corpus_id=args.corpus_id, payload=payload,
                drafts=drafts, read_chunks=read_chunks, publish=args.publish,
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--corpus-id")
    parser.add_argument("--expected-project-ref")
    parser.add_argument(
        "--gemini-free-tier-verified", action="store_true",
        help="Operator attestation after checking the exact account's Free tier; this flag is not proof",
    )
    parser.add_argument("--output", type=Path, help="New sanitized evidence file; never overwritten")
    args = parser.parse_args(argv)
    # Parser/provider/driver logs could contain source text or URL credentials.
    logging.disable(logging.CRITICAL)
    try:
        if args.publish and not args.execute:
            raise PreparationError("publish_requires_execute")
        if args.output and args.output.exists():
            raise PreparationError("evidence_output_already_exists")
        if args.execute:
            validate_execution(
                os.environ, project_ref=args.expected_project_ref,
                free_tier_verified=args.gemini_free_tier_verified, corpus_id=args.corpus_id,
            )
        payload, drafts = preflight(args.source)
        if args.execute:
            report = asyncio.run(execute(args, os.environ, payload, drafts))
        else:
            report = {
                "mode": "offline_preflight", "documentSha256": PDF_SHA256,
                "pages": PAGE_COUNT, "chunkCount": len(drafts),
                "embeddingModel": EMBEDDING_MODEL, "embeddingDimensions": EMBEDDING_DIMENSIONS,
                "generationModel": GENERATION_MODEL, "suggestedNewCorpusId": str(uuid4()),
                "externalCalls": 0, "accountFreeTierVerified": False,
            }
        if args.output:
            with args.output.open("x", encoding="utf-8") as output:
                json.dump(report, output, indent=2)
                output.write("\n")
        print(json.dumps({key: value for key, value in report.items() if key != "chunks"}))
        return 0
    except PreparationError as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
    except Exception:
        print(json.dumps({"ok": False, "error": "demo_rag_preparation_failed"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
