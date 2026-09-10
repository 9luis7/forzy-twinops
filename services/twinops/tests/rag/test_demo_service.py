import asyncio
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from uuid import uuid4

import psycopg
import pytest

from twinops.rag.demo_service import (
    DemoAssistantService, DemoRagAssistantService, project_demo_context,
)
from twinops.rag.generation import ChatGatewayClient, GeminiChatClient, ChatGatewayError
from twinops.rag.public_models import AssistantQueryRequest
from twinops.rag.public_service import RagAssistantService

# Existing real-contract corpus/provider doubles exercise the same citation
# validator and answer assembler as the live regression suite.
from .test_public_service import _Retriever, _Chat as _LegacyChat, _generated

GENERATED_TEXT = "Explicação operacional gerada para S1 (motor) e S2 (bomba)."


class _Chat(_LegacyChat):
    """A generated narrative double, with explicit server invocation metadata."""
    def __init__(self, output=None, **kwargs):
        output = (output or _generated()).model_copy(update={"current_state": GENERATED_TEXT})
        output._generation_metadata = {"status": "generated", "model": self.model,
                                       "invocationId": "test-invocation", "latencyMs": 1}
        super().__init__(output, **kwargs)


TIME = "2026-08-12T13:01:00Z"


def context():
    def assessment(sensor):
        return {
            "schemaVersion": "1.0", "assessmentId": str(uuid4()),
            "assetTag": "MTR-BMB-042", "sensorId": sensor,
            "window": {"start": "2026-08-12T13:00:00Z", "end": TIME,
                       "receivedAt": "2026-09-04T13:00:00Z", "freshnessMs": 0},
            "quality": {"status": "ok", "flags": []},
            "operatingContext": {"state": "unknown", "estimated": True},
            "assessment": {"status": "watch", "anomalyScore": 0.5,
                           "deteriorationScore": 0.4,
                           "scoreSemantics": "relative_to_historical_baseline_not_failure_probability",
                           "episodeId": "episode", "persistenceSeconds": 5},
            "componentTag": None, "recommendation": None, "humanValidationRequired": True,
            "evidence": [{"id": sensor + ":velocity", "feature": "velocity_ewma",
                          "value": 2.4, "unit": "mm/s", "windowSeconds": 60}],
            "model": {"name": "relative-baseline", "version": "1", "configHash": "sha256:" + "a" * 64,
                      "trainedUntil": "2026-08-01T00:00:00Z"},
            "limitations": [],
        }
    return {
        "schemaVersion": "demo-1.0", "mode": "replay", "assetId": "forzy-motor-01",
        "revision": 8,
        "replay": {"generation": 0, "sourceRow": 150, "sourceTime": TIME},
        "sensors": {sensor: {"assessment": assessment(sensor)} for sensor in ("s1", "s2")},
    }


class Repo:
    def __init__(self):
        self.current = context()
        self.frozen = deepcopy(self.current)
        self.event = {"eventId": "event-1", "generation": 0, "kind": "sustained_watch",
                      "contextRevision": 8, "sourceRow": 150, "observedAt": TIME,
                      "receivedAt": "2026-09-04T13:00:00Z", "sensorIds": ["s1", "s2"],
                      "status": "pending", "attempts": 0, "retryable": False,
                      "recommendation": None, "errorCode": None}
        self.owner = None

    def trusted_context(self, run, token, revision):
        from twinops.demo.repository import DemoError
        if token != "secret":
            raise DemoError(404, "run_not_found")
        if revision != self.current["revision"]:
            raise DemoError(409, "revision_conflict")
        return deepcopy(self.current)

    def get_context(self, run, token):
        return self.trusted_context(run, token, self.current["revision"])

    def get_event(self, *args):
        return deepcopy(self.event)

    def claim_event(self, *args, owner, lease_seconds):
        if self.event["status"] in ("ready", "degraded", "processing"):
            return None
        self.owner = owner
        self.event["status"] = "processing"
        self.event["attempts"] += 1
        return {"event": deepcopy(self.event), "context": deepcopy(self.frozen)}

    def finish_event(self, *args, owner, status, recommendation=None,
                     error_code=None, retryable=False):
        from twinops.demo.repository import DemoError
        if owner != self.owner or self.current["replay"]["generation"] != self.event["generation"]:
            raise DemoError(409, "event_generation_conflict")
        self.event.update(status=status, recommendation=recommendation,
                          errorCode=error_code, retryable=retryable)
        return deepcopy(self.event)


def service(repo=None, chat=None, **budgets):
    return DemoAssistantService(repo or Repo(), DemoRagAssistantService(_Retriever(), chat or _Chat(), **budgets))


def misattributed_retrieval(*, ambiguous=False, candidate_only=False):
    """Known wrong ID and a literal quote belonging to another authorized hit."""
    base = _Retriever().result
    original = base.hits[0]
    source = original.candidate
    unrelated = "Electrical installation instructions only."
    wrong = replace(original, candidate=replace(source, chunk=replace(
        source.chunk, text=unrelated, content_hash=sha256(unrelated.encode()).hexdigest(),
    )))
    document = replace(source.document, document_id="document-right", revision="verified-revision",
                       source_url="https://manufacturer.example/verified-manual.pdf")
    right = replace(original, candidate=replace(source, document=document, chunk=replace(
        source.chunk, chunk_id="chunk-right", document_id=document.document_id, ordinal=1,
        page_start=7, page_end=8, content_hash=sha256(source.chunk.text.encode()).hexdigest(),
    )))
    hits = [wrong] if candidate_only else [wrong, right]
    if ambiguous:
        hits.append(replace(right, candidate=replace(right.candidate, chunk=replace(
            right.candidate.chunk, chunk_id="chunk-ambiguous", ordinal=2,
        ))))
    return replace(base, hits=tuple(hits), vector_candidates=(wrong.candidate, right.candidate),
                   lexical_candidates=(wrong.candidate, right.candidate))


def test_demo_resolves_unique_literal_to_authorized_hit_without_changing_quote_or_live():
    from twinops.rag.generation import GeneratedOutputError
    retrieval, payload = misattributed_retrieval(), _generated()
    before = payload.model_dump()
    demo = DemoRagAssistantService(_Retriever(retrieval), _Chat())
    resolved = demo._validate_generated_payload(payload, retrieval=retrieval)
    assert resolved.manual_citations[0].chunk_id == "chunk-right"
    assert resolved.manual_citations[0].exact_quote == payload.manual_citations[0].exact_quote
    assert payload.model_dump() == before
    live = RagAssistantService(_Retriever(retrieval), _Chat(), query_timeout_seconds=10)
    with pytest.raises(GeneratedOutputError, match="invalid_manual_citation"):
        live._validate_generated_payload(payload, retrieval=retrieval)


@pytest.mark.parametrize("case", ["unknown", "missing", "ambiguous", "candidate_only", "converged_duplicates"])
def test_demo_literal_resolution_preserves_refusals(case):
    from twinops.rag.generation import GeneratedManualReference, GeneratedOutputError
    retrieval = misattributed_retrieval(ambiguous=case == "ambiguous", candidate_only=case == "candidate_only")
    good = _generated().manual_citations[0]
    references = (good,)
    if case == "unknown":
        references = (good.model_copy(update={"chunk_id": "unknown"}),)
    elif case == "missing":
        references = (good.model_copy(update={"exact_quote": "absent quote"}),)
    elif case == "converged_duplicates":
        references = (good, GeneratedManualReference(chunkId="chunk-right", exactQuote=good.exact_quote))
    payload = _generated(manual_citations=references)
    with pytest.raises(GeneratedOutputError):
        DemoRagAssistantService(_Retriever(retrieval), _Chat())._validate_generated_payload(payload, retrieval=retrieval)


def test_original_duplicate_ids_cannot_resolve_into_separate_chunks():
    from twinops.rag.generation import GeneratedManualReference, GeneratedOutputError
    retrieval = misattributed_retrieval()
    wrong = retrieval.hits[0].candidate.chunk
    payload = _generated(manual_citations=(
        _generated().manual_citations[0],
        GeneratedManualReference(chunkId=wrong.chunk_id, exactQuote=wrong.text),
    ))
    with pytest.raises(GeneratedOutputError, match="duplicate_manual_citation"):
        DemoRagAssistantService(_Retriever(retrieval), _Chat())._validate_generated_payload(payload, retrieval=retrieval)


def test_already_correct_quote_keeps_its_id_even_if_another_hit_contains_it():
    retrieval = misattributed_retrieval(ambiguous=True)
    payload = _generated(manual_citations=(_generated().manual_citations[0].model_copy(
        update={"chunk_id": "chunk-right"}),))
    validated = DemoRagAssistantService(_Retriever(retrieval), _Chat())._validate_generated_payload(payload, retrieval=retrieval)
    assert validated.model_dump() == payload.model_dump()


@pytest.mark.asyncio
async def test_ambiguous_literal_resolution_still_stops_after_three_event_attempts():
    repo, chat, retriever = Repo(), _Chat(), _Retriever(misattributed_retrieval(ambiguous=True))
    assistant = DemoAssistantService(repo, DemoRagAssistantService(retriever, chat))
    for attempt in range(1, 4):
        event = await assistant.recommendation("run", "secret", "event-1")
        assert event["status"] == ("pending" if attempt < 3 else "degraded")
        assert event["recommendation"] is None and event["attempts"] == attempt
    assert await assistant.recommendation("run", "secret", "event-1") == event
    assert len(chat.calls) == len(retriever.calls) == 3


@pytest.mark.asyncio
async def test_manual_uses_frozen_both_sensor_provenance_and_coverage():
    repo = Repo()
    answer = await service(repo).query("run", "secret", AssistantQueryRequest(question="rolamentos"), 8)
    assert answer["contextRevision"] == 8
    assert answer["sourceRow"] == 150
    assert answer["observedAt"] == TIME
    response = answer["response"]
    assert response["fallbackUsed"] is False
    assert response["groundingStatus"] == "grounded"
    telemetry = [c for c in response["citations"] if c["type"] == "telemetry"]
    assert {c["assessmentId"] for c in telemetry} == {
        repo.current["sensors"][s]["assessment"]["assessmentId"] for s in ("s1", "s2")}
    assert {c["evidenceId"] for c in telemetry} == {"s1:velocity", "s2:velocity"}
    assert "S1 (motor)" in response["answer"]["currentState"]
    assert "S2 (bomba)" in response["answer"]["currentState"]
    assert any("não cobre a bomba" in limit for limit in response["limitations"])
    assert response["corpus"]["equipmentModel"] == "W22"


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [None, 0, 9])
async def test_manual_captures_latest_server_context_regardless_of_browser_revision(revision):
    chat = _Chat()
    response = await service(chat=chat).query("run", "secret", AssistantQueryRequest(question="estado"), revision)
    assert response["contextRevision"] == 8
    assert response["observedAt"] == TIME
    assert len(chat.calls) == 1


def test_future_or_misattributed_assessment_is_rejected():
    frozen = context()
    frozen["sensors"]["s1"]["assessment"]["window"]["end"] = "2026-08-12T13:02:00Z"
    with pytest.raises(ValueError, match="future"):
        project_demo_context(frozen)
    frozen = context()
    frozen["sensors"]["s1"]["assessment"]["sensorId"] = "s2"
    with pytest.raises(ValueError, match="sensor mismatch"):
        project_demo_context(frozen)


@pytest.mark.asyncio
async def test_demo_refusal_preserves_guard_without_uncited_numeric_summary():
    chat = _Chat()
    result = await service(chat=chat).query(
        "run", "secret", AssistantQueryRequest(question="Desligue o motor agora"), 8,
    )
    response = result["response"]
    assert response["groundingStatus"] == "out_of_scope"
    assert response["citations"] == []
    assert "S1 (motor): atenção" in response["answer"]["currentState"]
    assert "vibração média recente" not in response["answer"]["currentState"]
    assert "2,4" not in response["answer"]["currentState"]
    assert chat.calls == []


@pytest.mark.asyncio
async def test_guided_warmup_before_first_visible_row_is_operational_unavailable():
    repo = Repo()
    repo.current["replay"].update(sourceRow=None, sourceTime=None)
    response = await service(repo).query("run", "secret", AssistantQueryRequest(question="rolamentos"), 8)
    assert response["observedAt"] is None
    assert response["response"]["groundingStatus"] == "operational_unavailable"
    assert all(citation["type"] != "telemetry" for citation in response["response"]["citations"])


@pytest.mark.asyncio
async def test_event_is_bound_to_immutable_revision_and_deduplicates():
    repo, chat = Repo(), _Chat()
    repo.current["revision"] = 90
    repo.current["replay"]["sourceRow"] = 240
    assistant = service(repo, chat)
    event = await assistant.recommendation("run", "secret", "event-1")
    assert event["status"] == "ready"
    assert event["contextRevision"] == 8
    assert event["recommendation"]["answer"]["currentState"] == GENERATED_TEXT
    assert TIME in json.dumps(chat.calls)
    assert event["sourceRow"] == 150
    assert "revisão" not in event["recommendation"]["answer"]["currentState"]
    assert await assistant.recommendation("run", "secret", "event-1") == event
    assert len(chat.calls) == 1


@pytest.mark.asyncio
async def test_slow_generation_does_not_hold_replay_and_restart_rejects_late_write():
    from twinops.demo.repository import DemoError
    started, release = asyncio.Event(), asyncio.Event()
    class SlowChat(_Chat):
        async def generate(self, messages):
            started.set()
            await release.wait()
            return await super().generate(messages)
    repo = Repo()
    assistant = service(repo, SlowChat())
    pending = asyncio.create_task(assistant.recommendation("run", "secret", "event-1"))
    await asyncio.wait_for(started.wait(), 2)
    # Replay continues independently while the generation awaits the provider.
    repo.current["revision"] += 1
    assert repo.trusted_context("run", "secret", 9)["revision"] == 9
    assert (await assistant.recommendation("run", "secret", "event-1"))["status"] == "processing"
    repo.current["replay"]["generation"] += 1
    release.set()
    with pytest.raises(DemoError):
        await pending
    assert repo.event["recommendation"] is None


@pytest.mark.asyncio
async def test_timeout_retries_then_success_is_terminal():
    repo = Repo()
    chat = _Chat(delay=0.08)
    assistant = service(repo, chat, generation_timeout_seconds=0.01)
    event = await assistant.recommendation("run", "secret", "event-1")
    assert event["status"] == "pending"
    assert event["retryable"] is True
    assert event["errorCode"] == "generation_timeout"
    chat.delay = 0
    event = await assistant.recommendation("run", "secret", "event-1")
    assert event["status"] == "ready"
    assert event["attempts"] == 2
    assert event["retryable"] is False


@pytest.mark.asyncio
async def test_retry_limit_terminates_without_duplicate_response():
    repo = Repo()
    assistant = service(repo, _Chat(failure=ChatGatewayError("transport")))
    for _ in range(3):
        event = await assistant.recommendation("run", "secret", "event-1")
    assert event["status"] == "degraded"
    assert event["retryable"] is False
    assert event["attempts"] == 3
    assert event["recommendation"] is None
    assert await assistant.recommendation("run", "secret", "event-1") == event


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,status,retryable", [
    ("timeout", None, True), ("http_status", 429, True),
    ("http_status", 503, True), ("http_status", 401, False),
    ("invalid_response", None, False),
])
async def test_provider_failure_taxonomy_stays_sanitized(reason, status, retryable):
    chat = _Chat(failure=ChatGatewayError(reason, status_code=status))
    event = await service(chat=chat).recommendation("run", "secret", "event-1")
    assert event["retryable"] is retryable
    assert event["status"] == ("pending" if retryable else "degraded")
    assert event["errorCode"] == "generation_" + reason
    assert event["recommendation"] is None


@pytest.mark.asyncio
async def test_missing_document_store_still_generates_operational_event_and_deduplicates():
    retriever = _Retriever(failure=psycopg.OperationalError("connection reset private-marker"))
    chat = _Chat(_generated(manual_citations=()))
    assistant = DemoAssistantService(Repo(), DemoRagAssistantService(retriever, chat))
    event = await assistant.recommendation("run", "secret", "event-1")
    assert event["status"] == "ready"
    assert event["attempts"] == 1 and not event["retryable"]
    assert event["recommendation"]["generation"]["status"] == "generated"
    assert not any(c["type"] == "manual" for c in event["recommendation"]["citations"])
    assert "private-marker" not in json.dumps(event)
    assert await assistant.recommendation("run", "secret", "event-1") == event
    assert len(chat.calls) == len(retriever.calls) == 1


@pytest.mark.asyncio
async def test_citation_only_output_is_not_reported_as_generated_event():
    assistant = DemoAssistantService(Repo(), DemoRagAssistantService(_Retriever(), _LegacyChat()))
    event = await assistant.recommendation("run", "secret", "event-1")
    assert event["status"] == "degraded"
    assert event["errorCode"] == "generation_unavailable"
    assert event["recommendation"]["generation"]["status"] == "not_called"
    assert await assistant.recommendation("run", "secret", "event-1") == event


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [
    psycopg.errors.ConnectionFailure, psycopg.errors.ConnectionDoesNotExist,
    psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable,
    psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected,
    psycopg.errors.AdminShutdown, psycopg.errors.CrashShutdown,
    psycopg.errors.CannotConnectNow, psycopg.errors.TooManyConnections,
])
async def test_temporary_postgres_sqlstate_is_retryable(error_type):
    from twinops.rag.demo_service import _failure
    assert _failure(error_type("private-marker")) == (True, "retrieval_database_unavailable")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    psycopg.errors.InvalidPassword("private-marker"),
    psycopg.errors.InvalidAuthorizationSpecification("private-marker"),
    psycopg.errors.UndefinedTable("private-marker"),
    psycopg.errors.InvalidSchemaName("private-marker"),
    psycopg.errors.InsufficientPrivilege("private-marker"),
    psycopg.errors.InvalidTextRepresentation("private-marker"),
    psycopg.errors.ProtocolViolation("private-marker"),
    psycopg.OperationalError('connection reset: password authentication failed for user "private-marker"'),
    psycopg.OperationalError('connection reset: no pg_hba.conf entry for host "private-marker"'),
    psycopg.OperationalError('connection reset: database "private-marker" does not exist'),
    psycopg.OperationalError("private-marker unspecified operational error"),
])
async def test_permanent_or_unclassified_postgres_error_is_immediately_terminal(failure):
    from twinops.rag.demo_service import _failure
    assert _failure(failure) == (False, "retrieval_database_unavailable")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["unknown_id", "nonliteral_quote", "duplicate_id"])
async def test_invalid_citation_never_delivered_and_stops_at_existing_attempt_limit(kind):
    from twinops.rag.generation import GeneratedManualReference
    good = _generated().manual_citations[0]
    references = {
        "unknown_id": (GeneratedManualReference(chunkId="invented", exactQuote=good.exact_quote),),
        "nonliteral_quote": (GeneratedManualReference(chunkId=good.chunk_id, exactQuote="invented"),),
        "duplicate_id": (good, good),
    }
    chat = _Chat(_generated(manual_citations=references[kind]))
    assistant = service(chat=chat)
    for attempt in range(1, 4):
        event = await assistant.recommendation("run", "secret", "event-1")
        assert event["status"] == ("pending" if attempt < 3 else "degraded")
        assert event["retryable"] is (attempt < 3)
        assert event["attempts"] == attempt
        assert event["errorCode"] == "invalid_citation"
        assert event["recommendation"] is None
        assert len(chat.calls) == attempt  # No nested retry/generation loop.
    assert await assistant.recommendation("run", "secret", "event-1") == event
    assert len(chat.calls) == 3


def test_demo_and_live_budgets_are_separate():
    demo = DemoRagAssistantService(_Retriever(), _Chat())
    assert demo.query_timeout_seconds == 40
    assert demo.chat.seconds == 30
    with pytest.raises(ValueError):
        RagAssistantService(_Retriever(), _Chat(), query_timeout_seconds=40)
    for client_type in (ChatGatewayClient, GeminiChatClient):
        live = client_type(None, api_key="test", model="model")
        demo_chat = client_type(None, api_key="test", model="model", timeout_seconds=30)
        assert live._timeout_seconds == 10
        assert demo_chat._timeout_seconds == 30


@pytest.mark.asyncio
async def test_interrupted_worker_leaves_claim_for_durable_lease_recovery():
    started = asyncio.Event()
    class InterruptedChat(_Chat):
        async def generate(self, messages):
            started.set()
            await asyncio.Event().wait()
    repo = Repo()
    pending = asyncio.create_task(service(repo, InterruptedChat()).recommendation("run", "secret", "event-1"))
    await asyncio.wait_for(started.wait(), 2)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert repo.event["status"] == "processing"
    assert repo.event["recommendation"] is None


@pytest.mark.asyncio
async def test_total_budget_includes_claim_generation_and_persistence(monkeypatch):
    import twinops.rag.demo_service as module
    monkeypatch.setattr(module, "DEMO_TOTAL_SECONDS", 0.02)
    repo = Repo()
    with pytest.raises(TimeoutError):
        await service(repo, _Chat(delay=0.15)).recommendation("run", "secret", "event-1")
    # The durable processing lease is recoverable after a whole-request cutoff.
    assert repo.event["status"] == "processing"
    assert repo.event["recommendation"] is None
