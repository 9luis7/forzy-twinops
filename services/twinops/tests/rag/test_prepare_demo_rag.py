"""Offline contract tests: real admin/extraction, in-memory DB and fake embeddings."""

from dataclasses import replace
from hashlib import sha256
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts import prepare_demo_rag as tool
from twinops.rag.embeddings import EmbeddingGatewayError, GeminiEmbeddingClient
from twinops.rag.repository import InMemoryRagRepository

from .pdf_factory import searchable_pdf


PROJECT = "abcdefghijklmnopqrst"
URL = f"postgresql://postgres.{PROJECT}:private@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require"


def environment():
    return {"DEMO_DATABASE_URL": URL, "GEMINI_API_KEY": "secret-test-key"}


def validate(env=None, **changes):
    options = dict(project_ref=PROJECT, free_tier_verified=True, corpus_id=str(uuid4()))
    options.update(changes)
    return tool.validate_execution(environment() if env is None else env, **options)


@pytest.fixture
def manual(tmp_path, monkeypatch):
    payload = searchable_pdf("WEG W22 motor maintenance lubrication inspection")
    monkeypatch.setattr(tool, "PDF_SHA256", sha256(payload).hexdigest())
    monkeypatch.setattr(tool, "PAGE_COUNT", 1)
    monkeypatch.setattr(tool, "CHUNK_COUNT", 1)
    path = tmp_path / "manual.pdf"
    path.write_bytes(payload)
    return path


class Embeddings:
    model = tool.EMBEDDING_MODEL
    dimensions = tool.EMBEDDING_DIMENSIONS

    def __init__(self):
        self.calls = 0
        self.fail = False

    async def embed(self, texts):
        self.calls += 1
        if self.fail:
            raise EmbeddingGatewayError("quota")
        return tuple((0.1,) * self.dimensions for _ in texts)


def chunk_reader(repository):
    def read(corpus_id):
        return [dict(
            chunk_id=c.chunk_id, document_id=c.document_id, ordinal=c.ordinal,
            text=c.text, page_start=c.page_start, page_end=c.page_end, section=c.section,
            content_hash=c.content_hash, token_count=c.token_count, dimensions=len(c.embedding),
        ) for c in sorted(repository._chunks.values(), key=lambda c: c.ordinal) if c.corpus_id == corpus_id]
    return read


def prepare_args(manual, repository, corpus_id):
    payload, drafts = tool.preflight(manual)
    return dict(corpus_id=corpus_id, payload=payload, drafts=drafts, read_chunks=chunk_reader(repository))


def test_offline_preflight_never_reads_configuration_or_opens_network(manual, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("offline preflight attempted an external operation")
    monkeypatch.setattr(tool.psycopg, "connect", forbidden)
    monkeypatch.setattr(tool.httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(tool, "validate_execution", forbidden)
    assert tool.main([str(manual)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["externalCalls"] == 0
    assert result["accountFreeTierVerified"] is False
    assert result["chunkCount"] == 1
    assert result["suggestedNewCorpusId"] not in tool.OLD_CORPUS_IDS


def test_pdf_hash_rejected_before_extraction(manual, monkeypatch):
    manual.write_bytes(b"different source")
    monkeypatch.setattr(tool, "extract_searchable_pdf", lambda *a, **k: pytest.fail("wrong PDF extracted"))
    with pytest.raises(tool.PreparationError, match="manual_hash_mismatch"):
        tool.preflight(manual)


def test_coverage_drift_rejected(manual, monkeypatch):
    monkeypatch.setattr(tool, "CHUNK_COUNT", 117)
    with pytest.raises(tool.PreparationError, match="manual_coverage_mismatch"):
        tool.preflight(manual)


@pytest.mark.parametrize("change", [
    {"free_tier_verified": False}, {"project_ref": "wrong"},
    {"corpus_id": "4fc8063f-aa3a-4283-8b14-2f54bf08358c"}, {"corpus_id": None},
])
def test_execution_gates(change):
    with pytest.raises(tool.PreparationError):
        validate(**change)


@pytest.mark.parametrize("url", [
    "", "postgresql://user:secret@ep-live.neon.tech/main?sslmode=require",
    URL.replace(PROJECT, "zyxwvutsrqponmlkjihg"),
    URL.replace("sslmode=require", "sslmode=disable"),
    URL + "&host=ep-live.neon.tech", URL + "&sslmode=disable",
    URL.replace("/postgres?", "/other?"),
    URL.replace(":5432/", ":6543/"),
    URL.replace("pooler.supabase.com", "pooler.supabase.com.evil.example"),
])
def test_only_exact_dedicated_demo_supabase_target_allowed(url):
    env = environment()
    env.update(DEMO_DATABASE_URL=url, DATABASE_URL=URL, TWINOPS_DATABASE_URL=URL)
    with pytest.raises(tool.PreparationError, match="dedicated_supabase_session_5432_tls_url_required"):
        validate(env)


def test_no_live_url_fallback():
    with pytest.raises(tool.PreparationError):
        validate({"DATABASE_URL": URL, "TWINOPS_DATABASE_URL": URL, "GEMINI_API_KEY": "key"})


@pytest.mark.parametrize("key,value", [
    ("TWINOPS_RAG_PROVIDER", "gateway"),
    ("TWINOPS_RAG_EMBEDDING_MODEL", "another-model"),
    ("TWINOPS_RAG_EMBEDDING_DIMENSIONS", "3072"),
    ("TWINOPS_RAG_GENERATION_MODEL", "another-generation-model"),
])
def test_wrong_models_rejected(key, value):
    env = environment()
    env[key] = value
    with pytest.raises(tool.PreparationError, match="configured_model_incompatible"):
        validate(env)


@pytest.mark.parametrize("url", [URL,
    f"postgresql://postgres:private@db.{PROJECT}.supabase.co:5432/postgres?sslmode=verify-full"])
def test_explicit_supabase_destinations_accepted(url):
    env = environment()
    env["DEMO_DATABASE_URL"] = url
    assert validate(env) == url


@pytest.mark.asyncio
async def test_real_admin_upload_then_publish_and_repeat_do_not_reembed(manual):
    repo, embed, corpus_id = InMemoryRagRepository(), Embeddings(), str(uuid4())
    args = prepare_args(manual, repo, corpus_id)
    draft = await tool.prepare(repo, embed, **args)
    assert draft["status"] == "draft" and not draft["active"]
    assert embed.calls == 1
    published = await tool.prepare(repo, embed, **args, publish=True)
    repeated = await tool.prepare(repo, embed, **args, publish=True)
    assert repeated == published
    assert published["active"] and published["reusedDocument"]
    assert published["citationProvenanceVerified"] and published["retrievalAcceptancePending"]
    assert not published["generationCalled"]
    assert embed.calls == 1
    assert len(repo._corpora) == len(repo._documents) == len(repo._chunks) == 1
    assert published["documentId"] != "9513b1a8-d158-4f2a-bf0e-509a4e4bf87a"
    assert "maintenance" not in json.dumps(published)
    assert "embedding\":" not in json.dumps(published)


@pytest.mark.asyncio
async def test_provider_failure_keeps_empty_draft_and_explicit_retry_reuses_corpus(manual):
    repo, embed, corpus_id = InMemoryRagRepository(), Embeddings(), str(uuid4())
    args = prepare_args(manual, repo, corpus_id)
    embed.fail = True
    with pytest.raises(EmbeddingGatewayError):
        await tool.prepare(repo, embed, **args, publish=True)
    assert embed.calls == 1 and len(repo._corpora) == 1
    assert not repo._documents and not repo._chunks and not repo._active
    embed.fail = False
    result = await tool.prepare(repo, embed, **args, publish=True)
    assert result["active"] and len(repo._corpora) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("text", "forged"), ("content_hash", "0" * 64),
    ("page_start", 2), ("dimensions", 3), ("ordinal", 7)])
async def test_bad_persisted_chunk_cannot_be_published(manual, field, value):
    repo, embed, corpus_id = InMemoryRagRepository(), Embeddings(), str(uuid4())
    args = prepare_args(manual, repo, corpus_id)
    await tool.prepare(repo, embed, **args)
    rows = args["read_chunks"](corpus_id)
    rows[0][field] = value
    args["read_chunks"] = lambda _: rows
    with pytest.raises(tool.PreparationError, match="persisted_chunk_provenance_mismatch"):
        await tool.prepare(repo, embed, **args, publish=True)
    assert not repo._active and embed.calls == 1


@pytest.mark.asyncio
async def test_existing_incompatible_corpus_rejected_without_embedding(manual):
    repo, embed, corpus_id = InMemoryRagRepository(), Embeddings(), str(uuid4())
    repo.create_corpus(replace(tool.desired_corpus(corpus_id), embedding_dimensions=3))
    with pytest.raises(tool.PreparationError, match="existing_corpus_incompatible"):
        await tool.prepare(repo, embed, **prepare_args(manual, repo, corpus_id))
    assert embed.calls == 0


@pytest.mark.asyncio
async def test_different_active_corpus_preserved_without_embedding(manual):
    repo, embed, corpus_id = InMemoryRagRepository(), Embeddings(), str(uuid4())
    await tool.prepare(repo, embed, **prepare_args(manual, repo, corpus_id), publish=True)
    with pytest.raises(tool.PreparationError, match="active_corpus_exists"):
        await tool.prepare(repo, embed, **prepare_args(manual, repo, str(uuid4())), publish=True)
    assert repo.get_active_corpus(tool.CANONICAL_RAG_ASSET_ID).corpus_id == corpus_id
    assert embed.calls == 1


def test_failure_output_does_not_leak_external_diagnostics(manual, monkeypatch, capsys):
    monkeypatch.setattr(tool, "preflight", lambda _: (_ for _ in ()).throw(RuntimeError("secret DSN raw manual")))
    assert tool.main([str(manual)]) == 1
    output = capsys.readouterr()
    assert "secret" not in output.err and "manual" not in output.err
    assert json.loads(output.err)["error"] == "demo_rag_preparation_failed"


def test_existing_output_blocks_execution_before_calls(manual, tmp_path, monkeypatch, capsys):
    output = tmp_path / "already.json"
    output.write_text("keep")
    monkeypatch.setattr(tool, "validate_execution", lambda *a, **k: pytest.fail("validation should not be reached"))
    assert tool.main([str(manual), "--execute", "--output", str(output)]) == 1
    assert output.read_text() == "keep"


@pytest.mark.asyncio
async def test_execute_wires_direct_gemini_without_quota_retry(manual, monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def locked(url):
        assert url == URL
        yield object()
    monkeypatch.setattr(tool, "locked_target", locked)
    monkeypatch.setattr(tool, "PostgresRagRepository", lambda *a, **k: object())
    async def inspect(repo, embeddings, **kwargs):
        assert isinstance(embeddings, GeminiEmbeddingClient)
        assert embeddings._max_rate_limit_retries == 0
        assert embeddings._task_type == "RETRIEVAL_DOCUMENT"
        assert embeddings._base_url == "https://generativelanguage.googleapis.com/v1beta"
        assert embeddings.model == tool.EMBEDDING_MODEL
        assert embeddings.dimensions == 768
        return {"ok": True}
    monkeypatch.setattr(tool, "prepare", inspect)
    args = SimpleNamespace(expected_project_ref=PROJECT, gemini_free_tier_verified=True,
        corpus_id=str(uuid4()), publish=False)
    payload, drafts = tool.preflight(manual)
    assert await tool.execute(args, environment(), payload, drafts) == {"ok": True}


@pytest.mark.parametrize("tls,locked,error", [(False, True, "database_tls_not_active"),
    (True, False, "another_demo_reindex_is_running")])
def test_lock_and_actual_tls_precede_provider(tls, locked, error, monkeypatch):
    class Connection:
        pgconn = SimpleNamespace(ssl_in_use=tls)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, *args):
            return SimpleNamespace(fetchone=lambda: {"db": "postgres", "acquired": locked})
    monkeypatch.setattr(tool.psycopg, "connect", lambda *a, **k: Connection())
    with pytest.raises(tool.PreparationError, match=error):
        with tool.locked_target(URL):
            pytest.fail("target should have been rejected")


def test_driver_configuration_and_lock_released_on_failure(monkeypatch):
    observed = {}
    class Connection:
        pgconn = SimpleNamespace(ssl_in_use=True)
        def __enter__(self): return self
        def __exit__(self, exc_type, *args): observed["exit_type"] = exc_type
        def execute(self, sql, *args):
            observed.setdefault("sql", []).append(sql)
            return SimpleNamespace(fetchone=lambda: {"db": "postgres", "acquired": True})
    def connect(url, **kwargs):
        assert url == URL
        observed.update(kwargs)
        return Connection()
    monkeypatch.setattr(tool.psycopg, "connect", connect)
    with pytest.raises(RuntimeError):
        with tool.locked_target(URL):
            raise RuntimeError("stopped")
    assert observed["prepare_threshold"] is None
    assert observed["connect_timeout"] == 10
    assert any("statement_timeout" in sql for sql in observed["sql"])
    assert any("pg_try_advisory_xact_lock" in sql for sql in observed["sql"])
    assert observed["exit_type"] is RuntimeError
