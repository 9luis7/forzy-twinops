"""RAG/replay boundary tested against actual transactional SQLite persistence."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from twinops.demo.repository import DemoRepository, DemoError, encode, stamp
from .test_demo_service import Repo, service, _Chat, GENERATED_TEXT


@pytest.fixture
def storage(tmp_path):
    now = [datetime(2026, 9, 4, 15, tzinfo=timezone.utc)]
    repository = DemoRepository("sqlite:///" + str(tmp_path / "demo-rag.db"), clock=lambda: now[0])
    sample = Repo()
    sample.current["replay"].update(runId="run", expiresAt=stamp(now[0] + timedelta(hours=24)))
    frozen = deepcopy(sample.current)
    with repository.transaction() as connection:
        repository.sql(connection,
            "INSERT INTO demo_runs(run_id,token_hash,expires_at,state) VALUES(?,?,?,?)",
            ("run", sha256(b"secret").hexdigest(), sample.current["replay"]["expiresAt"],
             encode({"public": sample.current})))
        repository.sql(connection,
            "INSERT INTO demo_events(event_id,run_id,generation,payload,context) VALUES(?,?,?,?,?)",
            ("event-1", "run", 0, encode(sample.event), encode(frozen)))
        second = {**sample.event, "eventId": "event-2"}
        repository.sql(connection,
            "INSERT INTO demo_events(event_id,run_id,generation,payload,context) VALUES(?,?,?,?,?)",
            ("event-2", "run", 0, encode(second), encode(frozen)))
    return repository, now


def test_lease_exclusion_expiry_fencing_and_terminal_immutability(storage):
    repo, now = storage
    first = repo.claim_event("run", "secret", "event-1", owner="owner-1")
    assert first["event"]["status"] == "processing"
    assert repo.claim_event("run", "secret", "event-2", owner="owner-2") is None
    assert repo.claim_event("run", "secret", "event-1", owner="owner-3") is None
    now[0] += timedelta(seconds=61)
    reclaimed = repo.claim_event("run", "secret", "event-1", owner="owner-2")
    assert reclaimed["event"]["attempts"] == 2
    with pytest.raises(DemoError) as conflict:
        repo.finish_event("run", "secret", "event-1", owner="owner-1", status="ready")
    assert conflict.value.detail == "lease_conflict"
    terminal = repo.finish_event("run", "secret", "event-1", owner="owner-2", status="degraded",
                                 error_code="invalid_citation")
    assert repo.finish_event("run", "secret", "event-1", owner="owner-1", status="ready") == terminal
    assert repo.claim_event("run", "secret", "event-1", owner="owner-3") is None


@pytest.mark.asyncio
async def test_real_repository_allows_advance_during_generation_and_preserves_revision(storage):
    repo, _ = storage
    started, release = asyncio.Event(), asyncio.Event()
    class Slow(_Chat):
        async def generate(self, messages):
            started.set()
            await release.wait()
            return await super().generate(messages)
    assistant = service(repo, Slow())
    pending = asyncio.create_task(assistant.recommendation("run", "secret", "event-1"))
    await asyncio.wait_for(started.wait(), 2)

    def advance_state():
        with repo.transaction() as connection:
            state = repo.authorized(connection, "run", "secret")
            state["public"]["revision"] = 9
            state["public"]["replay"]["sourceRow"] = 151
            repo.save(connection, state)
        return repo.trusted_context("run", "secret", 9)

    current = await asyncio.wait_for(asyncio.to_thread(advance_state), 1)
    assert current["replay"]["sourceRow"] == 151
    assert current["events"][0]["status"] == "processing"
    assert repo.claim_event("run", "secret", "event-2", owner="different-worker") is None
    release.set()
    ready = await pending
    assert ready["status"] == "ready"
    assert ready["contextRevision"] == 8
    assert ready["sourceRow"] == 150
    assert ready["recommendation"]["answer"]["currentState"] == GENERATED_TEXT
    assert ready["recommendation"]["generation"]["status"] == "generated"
    assert repo.get_context("run", "secret")["revision"] == 9
    assert await assistant.recommendation("run", "secret", "event-1") == ready


def test_restart_and_wrong_run_or_token_reject_event(storage):
    repo, _ = storage
    repo.claim_event("run", "secret", "event-1", owner="owner-1")
    for run, token in (("other-run", "secret"), ("run", "wrong")):
        with pytest.raises(DemoError) as error:
            repo.event_context(run, token, "event-1")
        assert error.value.status_code == 404
    with repo.transaction() as connection:
        state = repo.authorized(connection, "run", "secret")
        state["public"]["replay"]["generation"] = 1
        repo.save(connection, state)
    with pytest.raises(DemoError) as error:
        repo.finish_event("run", "secret", "event-1", owner="owner-1", status="ready")
    assert error.value.status_code == 404
    assert repo.get_context("run", "secret")["events"] == []


def test_restart_does_not_overlap_old_generation_provider_lease(storage):
    repo, now = storage
    repo.claim_event("run", "secret", "event-1", owner="old-provider")
    with repo.transaction() as connection:
        state = repo.authorized(connection, "run", "secret")
        state["public"]["replay"]["generation"] = 1
        repo.save(connection, state)
        next_event = {**Repo().event, "eventId": "event-new", "generation": 1}
        repo.sql(connection,
            "INSERT INTO demo_events(event_id,run_id,generation,payload,context) VALUES(?,?,?,?,?)",
            ("event-new", "run", 1, encode(next_event), encode(state["public"])))
    assert repo.claim_event("run", "secret", "event-new", owner="new-provider") is None
    now[0] += timedelta(seconds=61)
    assert repo.claim_event("run", "secret", "event-new", owner="new-provider")["event"]["generation"] == 1


@pytest.mark.asyncio
async def test_real_repository_transient_retry_then_validated_result(storage):
    repo, _ = storage
    chat = _Chat(delay=0.1)
    assistant = service(repo, chat, generation_timeout_seconds=0.01)
    transient = await assistant.recommendation("run", "secret", "event-1")
    assert transient["retryable"] is True
    assert transient["status"] == "pending"
    chat.delay = 0
    ready = await assistant.recommendation("run", "secret", "event-1")
    assert ready["status"] == "ready"
    assert ready["attempts"] == 2
    assert ready["recommendation"]["fallbackUsed"] is False
    assert any(c["type"] == "manual" for c in ready["recommendation"]["citations"])


@pytest.mark.asyncio
async def test_real_repository_invalid_citation_then_new_valid_generation_preserves_frozen_context(storage):
    from twinops.rag.generation import GeneratedManualReference
    from .test_public_service import _generated
    repo, _ = storage
    chat = _Chat(_generated(manual_citations=(GeneratedManualReference(
        chunkId="chunk-1", exactQuote="invalid private quote"),)))
    assistant = service(repo, chat)
    first = await assistant.recommendation("run", "secret", "event-1")
    assert first["status"] == "pending" and first["attempts"] == 1
    assert first["retryable"] is True and first["errorCode"] == "invalid_citation"
    assert first["recommendation"] is None
    assert repo.get_event("run", "secret", "event-1") == first
    assert len(chat.calls) == 1
    with repo.transaction() as connection:
        state = repo.authorized(connection, "run", "secret")
        state["public"]["revision"] = 9
        state["public"]["replay"]["sourceRow"] = 151
        repo.save(connection, state)
    chat.output = _Chat().output
    ready = await assistant.recommendation("run", "secret", "event-1")
    assert ready["status"] == "ready" and ready["attempts"] == 2
    assert ready["retryable"] is False and ready["errorCode"] is None
    assert ready["recommendation"]["fallbackUsed"] is False
    manual = [c for c in ready["recommendation"]["citations"] if c["type"] == "manual"]
    assert [c["excerpt"] for c in manual] == [_generated().manual_citations[0].exact_quote]
    assert ready["contextRevision"] == 8 and ready["sourceRow"] == 150
    assert ready["recommendation"]["answer"]["currentState"] == GENERATED_TEXT
    assert ready["recommendation"]["generation"]["status"] == "generated"
    assert chat.calls[0] == chat.calls[1]
    assert repo.get_context("run", "secret")["revision"] == 9
    assert await assistant.recommendation("run", "secret", "event-1") == ready
    assert len(chat.calls) == 2


@pytest.mark.asyncio
async def test_real_repository_three_invalid_citations_are_terminal_without_recommendation(storage):
    from twinops.rag.generation import GeneratedManualReference
    from .test_public_service import _generated
    repo, _ = storage
    chat = _Chat(_generated(manual_citations=(GeneratedManualReference(
        chunkId="invented", exactQuote="invalid private quote"),)))
    assistant = service(repo, chat)
    for attempt in range(1, 4):
        event = await assistant.recommendation("run", "secret", "event-1")
        assert event["attempts"] == attempt
        assert event["status"] == ("pending" if attempt < 3 else "degraded")
        assert event["retryable"] is (attempt < 3)
        assert event["recommendation"] is None
        assert event["errorCode"] == "invalid_citation"
        assert repo.get_event("run", "secret", "event-1") == event
        assert len(chat.calls) == attempt
    chat.output = _generated()
    assert await assistant.recommendation("run", "secret", "event-1") == event
    assert len(chat.calls) == 3


@pytest.mark.asyncio
async def test_unique_literal_resolution_persists_actual_chunk_provenance_without_another_call(storage):
    from twinops.rag.demo_service import DemoAssistantService, DemoRagAssistantService
    from .test_demo_service import misattributed_retrieval
    from .test_public_service import _Retriever, _generated
    repo, _ = storage
    retriever, chat = _Retriever(misattributed_retrieval()), _Chat()
    assistant = DemoAssistantService(repo, DemoRagAssistantService(retriever, chat))
    ready = await assistant.recommendation("run", "secret", "event-1")
    assert ready["status"] == "ready" and ready["attempts"] == 1
    assert ready["recommendation"]["fallbackUsed"] is False
    citations = [c for c in ready["recommendation"]["citations"] if c["type"] == "manual"]
    assert len(citations) == 1
    citation = citations[0]
    assert citation["chunkId"] == "chunk-right" and citation["documentId"] == "document-right"
    assert (citation["pageStart"], citation["pageEnd"]) == (7, 8)
    assert citation["revision"] == "verified-revision"
    assert citation["sourceUrl"] == "https://manufacturer.example/verified-manual.pdf"
    assert citation["contentHash"] == retriever.result.hits[1].candidate.chunk.content_hash
    assert citation["excerpt"] == _generated().manual_citations[0].exact_quote
    assert repo.get_event("run", "secret", "event-1") == ready
    assert await assistant.recommendation("run", "secret", "event-1") == ready
    assert len(chat.calls) == len(retriever.calls) == 1
