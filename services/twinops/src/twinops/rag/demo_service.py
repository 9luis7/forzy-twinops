"""Replay-only assistant using server snapshots and durable event leases.

There is deliberately no snapshot loader, live service or client measurement input.
The repository is the authorization, revision and immutable event boundary.
"""

import asyncio
from datetime import datetime
import re
from uuid import uuid4

import psycopg

from twinops.contracts.models import AssetConditionAssessment
from twinops.rag.embeddings import EmbeddingGatewayError
from twinops.rag.generation import ChatGatewayError, GeneratedOutputError
from twinops.rag.operational import OperationalEvidence, TrustedOperationalContext
from twinops.rag.public_models import AssistantQueryRequest, AssistantQueryResponse
from twinops.rag.public_service import (
    RagAssistantService,
    _deterministic_current_state,
    _telemetry_citation,
)
from twinops.rag.retrieval import CorpusUnavailableError


DEMO_TOTAL_SECONDS = 40.0
DEMO_GENERATION_SECONDS = 30.0
DEMO_LEASE_SECONDS = 60
MAX_EVENT_ATTEMPTS = 3
# SQLSTATEs are deliberately allowlisted: authentication, schema, data and
# protocol errors are permanent even when psycopg uses OperationalError.
_TRANSIENT_DATABASE_STATES = frozenset({
    "08000", "08001", "08003", "08006", "08007",  # connection availability
    "40001", "40P01", "55P03",                  # serialization/deadlock/lock
    "57014", "57P01", "57P02", "57P03",         # timeout/server availability
    "53300",                                    # too many connections
})
_PERMANENT_CONNECTION_ERROR = re.compile(
    r"authentication|password|pg_hba\.conf|certificate verify failed|"
    r"(?:database|role) .+ does not exist|invalid connection option|invalid dsn",
    re.IGNORECASE,
)
_TRANSIENT_CONNECTION_ERROR = re.compile(
    r"connection (?:reset|refused|timed out|is closed|is bad)|"
    r"timeout expired|connection timeout|server closed .{0,40}connection|"
    r"server disconnected|network is unreachable|temporary failure|"
    r"could not (?:receive|send) data|ssl syscall error|"
    r"ssl connection has been closed unexpectedly",
    re.IGNORECASE,
)
DEMO_LIMITATIONS = (
    "Cobertura documental: motor WEG W22 (S1). O corpus não cobre a bomba (S2); "
    "orientações do motor não são procedimentos de manutenção da bomba.",
    "S1 junto ao acoplamento do motor e S2 junto ao acoplamento da bomba são "
    "posições assumidas para demonstração, sem validação física.",
    "Replay histórico: a resposta pertence à revisão e à linha indicadas, "
    "mesmo que a reprodução tenha avançado. Scores são relativos ao baseline, "
    "não probabilidades de falha nem prova de antecipação fora da amostra.",
)


class _GenerationBudget:
    def __init__(self, chat, seconds):
        self.chat = chat
        self.model = chat.model
        self.seconds = seconds

    async def generate(self, messages):
        async with asyncio.timeout(self.seconds):
            return await self.chat.generate(messages)


class DemoRagAssistantService(RagAssistantService):
    """Isolated orchestration budget; the live service keeps its original cap.

    The injected chat must also be configured with a 30-second HTTP timeout.
    Reuse the live retriever/corpus and provider settings, not the live chat object.
    """

    max_query_timeout_seconds = DEMO_TOTAL_SECONDS

    def __init__(self, retriever, chat, *, query_timeout_seconds=DEMO_TOTAL_SECONDS,
                 generation_timeout_seconds=DEMO_GENERATION_SECONDS):
        if not 0 < generation_timeout_seconds <= DEMO_GENERATION_SECONDS:
            raise ValueError("demo generation budget must be in (0, 30]")
        super().__init__(retriever, _GenerationBudget(chat, generation_timeout_seconds),
                         query_timeout_seconds=query_timeout_seconds)


def _timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("demo timestamp must be timezone-aware")
    return result


def project_demo_context(context):
    """Validate both assessments and retain their individual provenance."""
    if context.get("schemaVersion") != "demo-1.0" or context.get("mode") != "replay":
        raise ValueError("invalid trusted demo context")
    source_time = context["replay"]["sourceTime"]
    projected = {}
    for sensor_id in ("s1", "s2"):
        raw = context["sensors"][sensor_id]["assessment"]
        if raw is None or source_time is None:
            projected[sensor_id] = TrustedOperationalContext.unavailable(
                operational_state="replay")
            continue
        assessment = AssetConditionAssessment.model_validate(raw)
        if assessment.sensor_id != sensor_id:
            raise ValueError("demo assessment sensor mismatch")
        end = _timestamp(assessment.window.end)
        if end > _timestamp(source_time):
            raise ValueError("future demo assessment")
        projected[sensor_id] = TrustedOperationalContext(
            operational_state="replay",
            assessment_id=str(assessment.assessment_id),
            assessment_status=assessment.assessment.status,
            quality_status=assessment.quality.status,
            window_start=_timestamp(assessment.window.start),
            window_end=end,
            received_at=_timestamp(assessment.window.received_at),
            freshness_ms=assessment.window.freshness_ms,
            evidence=tuple(OperationalEvidence(
                evidence_id=item.id, feature=item.feature, value=item.value,
                unit=item.unit, window_seconds=item.window_seconds,
            ) for item in assessment.evidence),
            quality_flags=tuple(assessment.quality.flags),
        )
    return projected


def _decorate_response(response, context, operational):
    """One generation, two independently attributed assessments, frozen revision."""
    body = response.model_dump(mode="json", by_alias=True)
    if any(citation["type"] == "manual" for citation in body["citations"]):
        body["answer"]["manual"] = (
            "Referência documental do motor WEG W22; sem cobertura da bomba. "
            + body["answer"]["manual"]
        )
    body["answer"]["currentState"] = (
        f"Replay, revisão {context['revision']}, linha {context['replay']['sourceRow']}. "
        + " ".join(
            f"{sensor_id.upper()} ({'motor' if sensor_id == 's1' else 'bomba'}): "
            + _deterministic_current_state(item).replace("atual", "desta revisão")
            for sensor_id, item in operational.items()
        )
    )
    body["citations"] = [citation for citation in body["citations"]
                         if citation["type"] != "telemetry"]
    if response.grounding_status != "out_of_scope":
        body["citations"].extend(
            _telemetry_citation(item, evidence).model_dump(mode="json", by_alias=True)
            for item in operational.values() if item.available
            for evidence in item.evidence
        )
    body["limitations"] = list(dict.fromkeys(body["limitations"] + list(DEMO_LIMITATIONS)))
    return AssistantQueryResponse.model_validate(body)


class DemoAssistantService:
    def __init__(self, repository, assistant: DemoRagAssistantService):
        self.repository = repository
        self.assistant = assistant

    async def _query(self, context, request, *, propagate_errors=False):
        operational = project_demo_context(context)
        # S1 owns the documented motor corpus. S2 telemetry is separately added
        # below, never relabelled as motor evidence or sent to the model as fact.
        primary = operational["s1"] if operational["s1"].available else operational["s2"]
        response = await self.assistant.query(
            context["assetId"], request, operational=primary,
            propagate_errors=propagate_errors,
        )
        return _decorate_response(response, context, operational)

    async def query(self, run_id, token, request, context_revision):
        async with asyncio.timeout(DEMO_TOTAL_SECONDS):
            context = await asyncio.to_thread(
                self.repository.trusted_context, run_id, token, context_revision)
            response = await self._query(context, request)
        return {
            "contextRevision": context["revision"],
            "sourceRow": context["replay"]["sourceRow"],
            "observedAt": context["replay"]["sourceTime"],
            "response": response.model_dump(mode="json", by_alias=True),
        }

    async def recommendation(self, run_id, token, event_id):
        # Includes authorization, lease claim and final persistence. If the
        # complete deadline interrupts persistence, the durable lease recovers.
        async with asyncio.timeout(DEMO_TOTAL_SECONDS):
            return await self._recommendation(run_id, token, event_id)

    async def _recommendation(self, run_id, token, event_id):
        owner = str(uuid4())
        claim = await asyncio.to_thread(
            self.repository.claim_event, run_id, token, event_id,
            owner=owner, lease_seconds=DEMO_LEASE_SECONDS,
        )
        if claim is None:
            return await asyncio.to_thread(self.repository.get_event, run_id, token, event_id)
        event, context = claim["event"], claim["context"]
        try:
            async with asyncio.timeout(DEMO_TOTAL_SECONDS):
                if context["revision"] != event["contextRevision"]:
                    raise ValueError("event context revision mismatch")
                if context["replay"]["generation"] != event["generation"]:
                    raise ValueError("event generation mismatch")
                response = await self._query(
                    context, AssistantQueryRequest(question=_event_question(event)),
                    propagate_errors=True,
                )
            generated = (not response.fallback_used and any(
                citation.type == "manual" for citation in response.citations))
            return await asyncio.to_thread(
                self.repository.finish_event, run_id, token, event_id, owner=owner,
                status="ready" if generated else "degraded",
                recommendation=response.model_dump(mode="json", by_alias=True),
                error_code=None if generated else "manual_insufficient",
            )
        except asyncio.CancelledError:
            # Durable lease recovery also handles process death. Cancellation
            # must never publish a partial response or assume the new revision.
            raise
        except Exception as error:
            # Ownership/restart errors from finishing must propagate to the
            # repository boundary, never become a second terminal write.
            if hasattr(error, "status_code") and hasattr(error, "detail"):
                raise
            retryable, code = _failure(error)
            retryable = retryable and event["attempts"] < MAX_EVENT_ATTEMPTS
            return await asyncio.to_thread(
                self.repository.finish_event, run_id, token, event_id, owner=owner,
                status="pending" if retryable else "degraded",
                error_code=code, retryable=retryable,
            )


def _event_question(event):
    # Retrieval asks about the covered motor only; frozen sensor state is rendered
    # deterministically alongside the quoted manual, rather than invented by LLM.
    descriptions = {"sustained_watch": "atenção sustentada", "escalation": "alerta",
                    "recovery": "retorno ao estado normal"}
    kind = descriptions.get(event["kind"], "mudança de condição")
    return (f"No evento de {kind}, quais verificações de vibração, temperatura e "
            "rolamentos o manual do motor WEG W22 recomenda para avaliação humana?")


def _failure(error):
    if isinstance(error, TimeoutError):
        return True, "generation_timeout"
    if isinstance(error, CorpusUnavailableError):
        return True, "corpus_unavailable"
    if isinstance(error, EmbeddingGatewayError):
        return True, "embedding_unavailable"
    if isinstance(error, ChatGatewayError):
        transient = error.reason in ("timeout", "transport") or (
            error.reason == "http_status" and
            (error.status_code in (408, 429) or (error.status_code or 0) >= 500))
        return transient, "generation_" + error.reason
    if isinstance(error, GeneratedOutputError):
        return False, "invalid_citation"
    if isinstance(error, psycopg.Error):
        return _transient_database_failure(error), "retrieval_database_unavailable"
    return False, "recommendation_unavailable"


def _transient_database_failure(error):
    if error.sqlstate:
        return error.sqlstate in _TRANSIENT_DATABASE_STATES
    if not isinstance(error, psycopg.OperationalError):
        return False
    # libpq connection failures may omit SQLSTATE, including bad credentials.
    # Inspect narrowly for availability signatures; never log or publish the
    # message, which may contain connection details or credential material.
    message = str(error)
    return (not _PERMANENT_CONNECTION_ERROR.search(message)
            and bool(_TRANSIENT_CONNECTION_ERROR.search(message)))
