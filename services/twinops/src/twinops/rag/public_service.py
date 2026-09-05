"""Public non-streaming assistant orchestration with validated fallback."""

import asyncio
import re
from time import perf_counter
import unicodedata
from uuid import uuid4

from twinops.rag.extractive import select_safe_excerpts
from twinops.rag.generation import (
    ChatClient,
    ChatGatewayError,
    GeneratedOutputError,
    build_gateway_messages,
    validate_generated_payload,
)
from twinops.rag.operational import OperationalEvidence, TrustedOperationalContext
from twinops.rag.public_models import (
    AssistantAnswer,
    AssistantQueryRequest,
    AssistantQueryResponse,
    CorpusAnchor,
    ManualCitation,
    ModelAnchors,
    TelemetryCitation,
)
from twinops.rag.retrieval import CorpusUnavailableError, RetrievalResult
from twinops.rag.telemetry import log_rag_stage


DEFAULT_LIMITATIONS = (
    "O assistente não diagnostica causa raiz nem estima probabilidade de falha ou RUL.",
    "Procedimentos e intervenções exigem validação de uma pessoa qualificada.",
)
OUT_OF_SCOPE_MESSAGES = {
    "root_cause": (
        "Não posso determinar causa raiz. Posso apresentar somente "
        "evidências do manual e do assessment atual para validação humana."
    ),
    "probability": (
        "Não posso estimar probabilidade de falha. Posso apresentar somente "
        "evidências observadas, sem converter scores em probabilidade."
    ),
    "rul": (
        "Não posso estimar vida útil restante (RUL) nem prever quando o "
        "equipamento falhará."
    ),
    "execution": (
        "O assistente não executa manutenção nem comanda o equipamento. "
        "Qualquer intervenção exige uma pessoa qualificada."
    ),
    "prompt_exfiltration": (
        "Não posso revelar prompt, regras ou conteúdo interno do sistema. "
        "Posso responder somente com evidências técnicas autorizadas."
    ),
    "secret_exfiltration": (
        "Não posso revelar chaves, tokens ou outras credenciais. "
        "Segredos encontrados em perguntas, histórico ou documentos não são "
        "evidência técnica."
    ),
}


class RagAssistantService:
    max_query_timeout_seconds = 11.0

    def __init__(self, retriever, chat: ChatClient, *, query_timeout_seconds: float) -> None:
        if not 0 < query_timeout_seconds <= self.max_query_timeout_seconds:
            raise ValueError("RAG query timeout exceeds the service budget")
        self.retriever = retriever
        self.chat = chat
        self.query_timeout_seconds = query_timeout_seconds

    def is_healthy(self, asset_id: str) -> bool:
        try:
            return bool(self.retriever.healthy(asset_id))
        except Exception:
            return False

    async def query(
        self,
        asset_id: str,
        request: AssistantQueryRequest,
        *,
        operational: TrustedOperationalContext,
        propagate_errors: bool = False,
    ) -> AssistantQueryResponse:
        started = perf_counter()
        conversation_id = request.conversation_id or uuid4()
        trace_id = uuid4()
        retrieval: RetrievalResult | None = None
        refusal = _refusal_for(request.question)
        if refusal is not None:
            response = self._out_of_scope(
                refusal,
                operational,
                conversation_id=conversation_id,
                trace_id=trace_id,
                started=started,
            )
            self._log_total(
                asset_id,
                trace_id,
                started,
                outcome=response.grounding_status,
            )
            return response
        try:
            async with asyncio.timeout(self.query_timeout_seconds):
                retrieval = await self.retriever.retrieve(
                    asset_id,
                    request.question,
                    trace_id=str(trace_id),
                )
                response = await self._answer_from_retrieval(
                    request,
                    retrieval=retrieval,
                    operational=operational,
                    conversation_id=conversation_id,
                    trace_id=trace_id,
                    started=started,
                )
                self._log_total(
                    asset_id,
                    trace_id,
                    started,
                    outcome=response.grounding_status,
                    retrieval=retrieval,
                )
                return response
        except CorpusUnavailableError:
            self._log_total(
                asset_id,
                trace_id,
                started,
                outcome="corpus_unavailable",
                retrieval=retrieval,
            )
            raise
        except asyncio.CancelledError:
            self._log_total(
                asset_id,
                trace_id,
                started,
                outcome="cancelled",
                retrieval=retrieval,
            )
            raise
        except Exception as error:
            if propagate_errors:
                self._log_total(
                    asset_id, trace_id, started,
                    outcome=_internal_failure_outcome(error), retrieval=retrieval,
                )
                raise
            response = self._fallback(
                request.question,
                retrieval,
                operational,
                conversation_id=conversation_id,
                trace_id=trace_id,
                started=started,
            )
            self._log_total(
                asset_id,
                trace_id,
                started,
                outcome=_internal_failure_outcome(error),
                retrieval=retrieval,
            )
            return response

    async def query_with_operational_loader(
        self,
        asset_id: str,
        request: AssistantQueryRequest,
        *,
        operational_loader,
        started_at: float,
    ) -> AssistantQueryResponse:
        """Run preflight, snapshot, retrieval and generation in one route budget."""

        conversation_id = request.conversation_id or uuid4()
        trace_id = uuid4()
        retrieval: RetrievalResult | None = None
        operational = TrustedOperationalContext.unavailable(
            operational_state="unavailable"
        )
        refusal = _refusal_for(request.question)
        if refusal is not None:
            response = self._out_of_scope(
                refusal,
                operational,
                conversation_id=conversation_id,
                trace_id=trace_id,
                started=started_at,
            )
            self._log_total(
                asset_id,
                trace_id,
                started_at,
                outcome=response.grounding_status,
            )
            return response
        elapsed = max(0.0, perf_counter() - started_at)
        remaining = max(0.0, self.query_timeout_seconds - elapsed)
        try:
            async with asyncio.timeout(remaining):
                operational_task = asyncio.create_task(
                    _timed_operational_loader(
                        operational_loader,
                        asset_id=asset_id,
                        trace_id=trace_id,
                    )
                )
                retrieval_task = None
                try:
                    corpus = await self.retriever.prepare(
                        asset_id, trace_id=str(trace_id)
                    )
                    retrieval_task = asyncio.create_task(
                        self.retriever.retrieve(
                            asset_id,
                            request.question,
                            corpus=corpus,
                            trace_id=str(trace_id),
                        )
                    )
                    operational, retrieval = await asyncio.gather(
                        operational_task,
                        retrieval_task,
                    )
                except BaseException:
                    operational_task.cancel()
                    if retrieval_task is not None:
                        retrieval_task.cancel()
                    await asyncio.gather(
                        *(
                            (operational_task,)
                            if retrieval_task is None
                            else (operational_task, retrieval_task)
                        ),
                        return_exceptions=True,
                    )
                    raise
                response = await self._answer_from_retrieval(
                    request,
                    retrieval=retrieval,
                    operational=operational,
                    conversation_id=conversation_id,
                    trace_id=trace_id,
                    started=started_at,
                )
                self._log_total(
                    asset_id,
                    trace_id,
                    started_at,
                    outcome=response.grounding_status,
                    retrieval=retrieval,
                )
                return response
        except CorpusUnavailableError:
            self._log_total(
                asset_id,
                trace_id,
                started_at,
                outcome="corpus_unavailable",
                retrieval=retrieval,
            )
            raise
        except asyncio.CancelledError:
            self._log_total(
                asset_id,
                trace_id,
                started_at,
                outcome="cancelled",
                retrieval=retrieval,
            )
            raise
        except Exception as error:
            response = self._fallback(
                request.question,
                retrieval,
                operational,
                conversation_id=conversation_id,
                trace_id=trace_id,
                started=started_at,
            )
            self._log_total(
                asset_id,
                trace_id,
                started_at,
                outcome=_internal_failure_outcome(error),
                retrieval=retrieval,
            )
            return response

    async def _answer_from_retrieval(
        self,
        request,
        *,
        retrieval,
        operational,
        conversation_id,
        trace_id,
        started,
    ):
        if not retrieval.sufficient:
            return self._manual_insufficient(
                retrieval,
                operational,
                conversation_id=conversation_id,
                trace_id=trace_id,
                started=started,
            )
        prompt_started = perf_counter()
        try:
            messages = build_gateway_messages(
                question=request.question,
                history=tuple(
                    (turn.question, turn.answer) for turn in request.history
                ),
                retrieval=retrieval,
            )
        except Exception:
            log_rag_stage(
                "prompt_assembly",
                outcome="invalid_response",
                duration_ms=(perf_counter() - prompt_started) * 1000,
                corpus_id=retrieval.corpus.corpus_id,
                model=self.chat.model,
                trace_id=str(trace_id),
            )
            raise
        log_rag_stage(
            "prompt_assembly",
            outcome="ok",
            duration_ms=(perf_counter() - prompt_started) * 1000,
            corpus_id=retrieval.corpus.corpus_id,
            model=self.chat.model,
            count=len(messages),
            trace_id=str(trace_id),
        )
        remaining_budget_ms = max(
            0.0,
            (self.query_timeout_seconds - (perf_counter() - started)) * 1000,
        )
        log_rag_stage(
            "remaining_budget",
            outcome="ok",
            duration_ms=0.0,
            remaining_budget_ms=remaining_budget_ms,
            corpus_id=retrieval.corpus.corpus_id,
            model=self.chat.model,
            trace_id=str(trace_id),
        )
        generation_started = perf_counter()
        try:
            generated = await self.chat.generate(messages)
        except asyncio.CancelledError:
            log_rag_stage(
                "generation",
                outcome="cancelled",
                duration_ms=(perf_counter() - generation_started) * 1000,
                corpus_id=retrieval.corpus.corpus_id,
                model=self.chat.model,
                trace_id=str(trace_id),
            )
            raise
        except ChatGatewayError as error:
            log_rag_stage(
                "generation",
                outcome=error.reason,
                duration_ms=(perf_counter() - generation_started) * 1000,
                corpus_id=retrieval.corpus.corpus_id,
                model=self.chat.model,
                http_status=error.status_code,
                trace_id=str(trace_id),
            )
            raise
        except Exception:
            log_rag_stage(
                "generation",
                outcome="invalid_response",
                duration_ms=(perf_counter() - generation_started) * 1000,
                corpus_id=retrieval.corpus.corpus_id,
                model=self.chat.model,
                trace_id=str(trace_id),
            )
            raise
        log_rag_stage(
            "generation",
            outcome="ok",
            duration_ms=(perf_counter() - generation_started) * 1000,
            corpus_id=retrieval.corpus.corpus_id,
            model=self.chat.model,
            count=len(generated.manual_citations),
            trace_id=str(trace_id),
        )
        validation_started = perf_counter()
        try:
            generated = validate_generated_payload(
                generated,
                retrieval=retrieval,
            )
        except GeneratedOutputError:
            log_rag_stage(
                "validation",
                outcome="invalid_citation",
                duration_ms=(perf_counter() - validation_started) * 1000,
                corpus_id=retrieval.corpus.corpus_id,
                model=self.chat.model,
                trace_id=str(trace_id),
            )
            raise
        except Exception:
            log_rag_stage(
                "validation",
                outcome="invalid_response",
                duration_ms=(perf_counter() - validation_started) * 1000,
                corpus_id=retrieval.corpus.corpus_id,
                model=self.chat.model,
                trace_id=str(trace_id),
            )
            raise
        log_rag_stage(
            "validation",
            outcome="ok",
            duration_ms=(perf_counter() - validation_started) * 1000,
            corpus_id=retrieval.corpus.corpus_id,
            model=self.chat.model,
            count=len(generated.manual_citations),
            trace_id=str(trace_id),
        )
        return self._generated_response(
            generated,
            retrieval,
            operational,
            conversation_id=conversation_id,
            trace_id=trace_id,
            started=started,
        )

    def _log_total(
        self,
        asset_id,
        trace_id,
        started,
        *,
        outcome,
        retrieval=None,
    ):
        log_rag_stage(
            "total",
            outcome=outcome,
            duration_ms=(perf_counter() - started) * 1000,
            asset_id=asset_id,
            corpus_id=(
                None if retrieval is None else retrieval.corpus.corpus_id
            ),
            model=self.chat.model,
            trace_id=str(trace_id),
        )

    def _generated_response(
        self,
        generated,
        retrieval,
        operational,
        *,
        conversation_id,
        trace_id,
        started,
    ):
        hit_by_id = {
            hit.candidate.chunk.chunk_id: hit for hit in retrieval.hits
        }
        citations = [
            _manual_citation(
                hit_by_id[item.chunk_id], excerpt=item.exact_quote
            )
            for item in generated.manual_citations
        ]
        citations.extend(
            _telemetry_citation(operational, item)
            for item in operational.evidence
        )
        current_state = _deterministic_current_state(operational)
        quotes = list(
            dict.fromkeys(item.exact_quote for item in generated.manual_citations)
        )
        return _response(
            manual="Segundo o manual:\n" + "\n".join(
                f"- {quote}" for quote in quotes
            ),
            current_state=current_state,
            grounding_status=(
                "grounded" if operational.available else "operational_unavailable"
            ),
            citations=citations,
            retrieval=retrieval,
            generation_model=self.chat.model,
            fallback_used=False,
            limitations=DEFAULT_LIMITATIONS,
            conversation_id=conversation_id,
            trace_id=trace_id,
            started=started,
        )

    def _out_of_scope(
        self,
        reason,
        operational,
        *,
        conversation_id,
        trace_id,
        started,
    ):
        return _out_of_scope_response(
            reason=reason,
            operational=operational,
            generation_model=self.chat.model,
            conversation_id=conversation_id,
            trace_id=trace_id,
            started=started,
        )

    def _manual_insufficient(
        self, retrieval, operational, *, conversation_id, trace_id, started
    ):
        citations = [
            _telemetry_citation(operational, item)
            for item in operational.evidence
        ]
        return _response(
            manual=(
                "O manual ativo não contém evidência suficiente para responder "
                "a esta pergunta com segurança."
            ),
            current_state=_deterministic_current_state(operational),
            grounding_status="manual_insufficient",
            citations=citations,
            retrieval=retrieval,
            generation_model=self.chat.model,
            fallback_used=False,
            limitations=DEFAULT_LIMITATIONS,
            conversation_id=conversation_id,
            trace_id=trace_id,
            started=started,
        )

    def _fallback(
        self,
        question,
        retrieval,
        operational,
        *,
        conversation_id,
        trace_id,
        started,
    ):
        citations = []
        if retrieval is not None and retrieval.hits:
            selections = select_safe_excerpts(question, retrieval.hits)
            if selections:
                citations.extend(
                    _manual_citation(item.hit, excerpt=item.excerpt)
                    for item in selections
                )
                manual = "Segundo o manual:\n" + "\n".join(
                    f"- {item.excerpt}" for item in selections
                )
                grounding_status = "degraded_fallback"
            else:
                manual = (
                    "O manual ativo não contém evidência suficiente para responder "
                    "a esta pergunta com segurança."
                )
                grounding_status = "manual_insufficient"
        else:
            manual = "Não foi possível consultar o manual técnico neste momento."
            grounding_status = "degraded_fallback"
        citations.extend(
            _telemetry_citation(operational, item)
            for item in operational.evidence
        )
        return _response(
            manual=manual,
            current_state=_deterministic_current_state(operational),
            grounding_status=grounding_status,
            citations=citations,
            retrieval=retrieval,
            generation_model=self.chat.model,
            fallback_used=grounding_status == "degraded_fallback",
            limitations=DEFAULT_LIMITATIONS,
            conversation_id=conversation_id,
            trace_id=trace_id,
            started=started,
        )


async def _timed_operational_loader(loader, *, asset_id, trace_id):
    started = perf_counter()
    try:
        operational = await loader()
    except asyncio.CancelledError:
        log_rag_stage(
            "snapshot",
            outcome="cancelled",
            duration_ms=(perf_counter() - started) * 1000,
            asset_id=asset_id,
            trace_id=str(trace_id),
        )
        raise
    except Exception:
        log_rag_stage(
            "snapshot",
            outcome="unavailable",
            duration_ms=(perf_counter() - started) * 1000,
            asset_id=asset_id,
            trace_id=str(trace_id),
        )
        raise
    log_rag_stage(
        "snapshot",
        outcome="ok",
        duration_ms=(perf_counter() - started) * 1000,
        asset_id=asset_id,
        count=len(operational.evidence),
        trace_id=str(trace_id),
    )
    return operational


def _internal_failure_outcome(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, ChatGatewayError):
        return error.reason
    if isinstance(error, GeneratedOutputError):
        return "invalid_citation"
    return "unavailable"


def prohibited_intent_response(
    request: AssistantQueryRequest,
    *,
    generation_model: str,
    started_at: float,
) -> AssistantQueryResponse | None:
    """Build a local refusal without requiring corpus, Gateway or telemetry."""

    reason = _refusal_for(request.question)
    if reason is None:
        return None
    return _out_of_scope_response(
        reason=reason,
        operational=TrustedOperationalContext.unavailable(
            operational_state="unavailable"
        ),
        generation_model=generation_model,
        conversation_id=request.conversation_id or uuid4(),
        trace_id=uuid4(),
        started=started_at,
    )


def _out_of_scope_response(
    *,
    reason: str,
    operational: TrustedOperationalContext,
    generation_model: str,
    conversation_id,
    trace_id,
    started: float,
) -> AssistantQueryResponse:
    return _response(
        manual=OUT_OF_SCOPE_MESSAGES[reason],
        current_state=_deterministic_current_state(operational),
        grounding_status="out_of_scope",
        citations=[],
        retrieval=None,
        generation_model=generation_model,
        fallback_used=False,
        limitations=DEFAULT_LIMITATIONS,
        conversation_id=conversation_id,
        trace_id=trace_id,
        started=started,
    )


def _response(
    *,
    manual,
    current_state,
    grounding_status,
    citations,
    retrieval,
    generation_model,
    fallback_used,
    limitations,
    conversation_id,
    trace_id,
    started,
) -> AssistantQueryResponse:
    corpus = None if retrieval is None else retrieval.corpus
    embedding_model = "unavailable" if corpus is None else corpus.embedding_model
    return AssistantQueryResponse(
        answer=AssistantAnswer(manual=manual, currentState=current_state),
        groundingStatus=grounding_status,
        citations=citations,
        corpus=(
            None
            if corpus is None
            else CorpusAnchor(
                corpusId=corpus.corpus_id,
                manufacturer=corpus.manufacturer,
                equipmentModel=corpus.equipment_model,
                embeddingModel=corpus.embedding_model,
                embeddingDimensions=corpus.embedding_dimensions,
                minRelevanceScore=corpus.min_relevance_score,
            )
        ),
        models=ModelAnchors(
            embedding=embedding_model,
            generation=generation_model,
        ),
        fallbackUsed=fallback_used,
        limitations=list(dict.fromkeys(limitations)),
        humanValidationRequired=True,
        conversationId=conversation_id,
        traceId=trace_id,
        latencyMs=max(0.0, (perf_counter() - started) * 1000.0),
    )


def _manual_citation(hit, *, excerpt: str) -> ManualCitation:
    chunk = hit.candidate.chunk
    document = hit.candidate.document
    return ManualCitation(
        chunkId=chunk.chunk_id,
        documentId=document.document_id,
        manufacturer=document.manufacturer,
        equipmentModel=document.equipment_model,
        revision=document.revision,
        sourceUrl=document.source_url,
        pageStart=chunk.page_start,
        pageEnd=chunk.page_end,
        section=chunk.section,
        excerpt=excerpt,
        contentHash=chunk.content_hash,
    )


def _telemetry_citation(
    operational: TrustedOperationalContext,
    evidence: OperationalEvidence,
) -> TelemetryCitation:
    assert operational.assessment_id is not None
    assert operational.window_start is not None
    assert operational.window_end is not None
    assert operational.received_at is not None
    assert operational.freshness_ms is not None
    assert operational.quality_status is not None
    return TelemetryCitation(
        assessmentId=operational.assessment_id,
        evidenceId=evidence.evidence_id,
        feature=evidence.feature,
        value=evidence.value,
        unit=evidence.unit,
        windowStart=operational.window_start.isoformat(),
        windowEnd=operational.window_end.isoformat(),
        receivedAt=operational.received_at.isoformat(),
        freshnessMs=operational.freshness_ms,
        windowSeconds=evidence.window_seconds,
        qualityStatus=operational.quality_status,
    )


def _deterministic_current_state(operational: TrustedOperationalContext) -> str:
    if not operational.available:
        text = (
            "O assessment operacional atual está indisponível; não é seguro "
            "inferir o estado do equipamento."
        )
        if operational.outside_window:
            text += " O equipamento está fora da janela operacional."
        return text
    assert operational.window_start is not None
    assert operational.window_end is not None
    assert operational.freshness_ms is not None
    base = (
        f"O assessment atual está em {operational.assessment_status}, com qualidade "
        f"{operational.quality_status}. A janela vai de "
        f"{operational.window_start.isoformat()} a {operational.window_end.isoformat()} "
        f"e o frescor é {operational.freshness_ms:.0f} ms."
    )
    return _append_operational_warning(base, operational)


def _append_operational_warning(
    text: str, operational: TrustedOperationalContext
) -> str:
    warnings = []
    if operational.stale:
        warnings.append("O dado operacional está antigo e deve ser atualizado.")
    if operational.operational_state == "last_known":
        warnings.append(
            "Este é o último estado conhecido e não uma medição recebida agora."
        )
    if operational.outside_window:
        warnings.append(
            "O equipamento está fora da janela operacional; o estado é apenas o último conhecido."
        )
    return " ".join((text, *warnings))


def _refusal_for(question: str) -> str | None:
    normalized = _normalized_text(question)
    tokens = tuple(re.findall(r"[a-z0-9]+|%", normalized))
    token_set = set(tokens)

    if _is_secret_exfiltration_request(normalized, token_set):
        return "secret_exfiltration"
    if _is_prompt_exfiltration_request(normalized, token_set):
        return "prompt_exfiltration"
    if _is_policy_limited_state_request(normalized, token_set):
        return None
    if _is_root_cause_request(normalized, token_set):
        return "root_cause"
    if _is_probability_request(token_set):
        return "probability"
    if _is_remaining_life_request(normalized, token_set):
        return "rul"
    if _is_execution_request(normalized, tokens):
        return "execution"
    return None


def _is_policy_limited_state_request(normalized: str, tokens: set[str]) -> bool:
    state_request = bool(tokens & {"assessment", "estado", "state"}) and bool(
        tokens & {"explain", "explique", "show", "mostre"}
    )
    probability_boundary = (
        ("sem transformar" in normalized or "without converting" in normalized)
        and bool(tokens & {"probabilidade", "probability"})
    )
    root_cause_boundary = (
        ("sem diagnosticar" in normalized or "without diagnosing" in normalized)
        and ("causa raiz" in normalized or "root cause" in normalized)
    )
    return state_request and (probability_boundary or root_cause_boundary)


def _is_prompt_exfiltration_request(normalized: str, tokens: set[str]) -> bool:
    disclosure = bool(
        tokens
        & {
            "exiba",
            "expose",
            "mostre",
            "print",
            "repita",
            "repeat",
            "reveal",
            "revele",
            "show",
        }
    )
    protected_target = any(
        phrase in normalized
        for phrase in (
            "conteudo interno",
            "internal instructions",
            "internal prompt",
            "prompt do sistema",
            "regras do sistema",
            "system instructions",
            "system prompt",
        )
    )
    return disclosure and protected_target


def _is_secret_exfiltration_request(normalized: str, tokens: set[str]) -> bool:
    disclosure = bool(
        tokens
        & {
            "exiba",
            "expose",
            "mostre",
            "print",
            "repita",
            "repeat",
            "reveal",
            "revele",
            "show",
        }
    )
    explicit_secret = bool(
        tokens
        & {
            "credential",
            "credentials",
            "credencial",
            "credenciais",
            "password",
            "secret",
            "segredo",
            "senha",
            "token",
        }
    )
    provider_key = (
        bool(tokens & {"api", "gateway"})
        and bool(tokens & {"chave", "key"})
    ) or "api key" in normalized
    return disclosure and (explicit_secret or provider_key)


def _normalized_text(value: str) -> str:
    return " ".join(
        "".join(
            character
            for character in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(character)
        ).casefold().split()
    )


def _has_prefix(tokens: set[str], *prefixes: str) -> bool:
    return any(
        token.startswith(prefix)
        for token in tokens
        for prefix in prefixes
    )


def _is_manual_catalog_question(tokens: set[str]) -> bool:
    manual_anchor = bool(
        tokens & {"manual", "manufacturer", "fabricante", "troubleshooting"}
    )
    catalog_language = bool(
        tokens
        & {
            "lista",
            "listadas",
            "listed",
            "possiveis",
            "possible",
            "tabela",
            "table",
            "checks",
            "checagens",
        }
    )
    return manual_anchor and catalog_language


def _is_root_cause_request(normalized: str, tokens: set[str]) -> bool:
    if "causa raiz" in normalized or "root cause" in normalized:
        return True
    if _is_manual_catalog_question(tokens):
        return False
    causal_concept = bool(
        tokens
        & {
            "causa",
            "cause",
            "motivo",
            "reason",
            "origem",
            "origin",
            "determinante",
            "determinant",
            "responsavel",
            "underlying",
        }
    ) or _has_prefix(tokens, "motiv", "caus", "diagnost")
    investigative_intent = bool(
        tokens
        & {
            "identifique",
            "identify",
            "determine",
            "explique",
            "explain",
            "qual",
            "what",
            "why",
            "porque",
        }
    ) or "por que" in normalized or "o que" in normalized
    causal_target = bool(
        tokens
        & {
            "falha",
            "failure",
            "defeito",
            "fault",
            "anomalia",
            "anomaly",
            "vibracao",
            "vibration",
        }
    )
    direct_why_question = (
        ("por que" in normalized or bool(tokens & {"why", "porque"}))
        and causal_target
    )
    return direct_why_question or causal_concept and (
        investigative_intent or causal_target
    )


def _is_probability_request(tokens: set[str]) -> bool:
    probability_terms = {
        "probabilidade",
        "probability",
        "likelihood",
        "chance",
        "chances",
        "possibilidade",
        "possibility",
        "odds",
    }
    if tokens & probability_terms:
        return True
    risk_terms = bool(tokens & {"risco", "risk", "percentual", "percentage"})
    failure_terms = bool(
        tokens
        & {
            "falha",
            "failure",
            "parada",
            "stop",
            "quebrar",
            "breakdown",
        }
    )
    return risk_terms and (failure_terms or "%" in tokens)


def _is_remaining_life_request(normalized: str, tokens: set[str]) -> bool:
    if "rul" in tokens or "remaining useful life" in normalized:
        return True
    remaining = bool(
        tokens & {"restante", "remanescente", "remaining", "left"}
    )
    life = bool(
        tokens & {"vida", "life", "durabilidade", "durability"}
    )
    time_question = bool(
        tokens & {"quanto", "quantas", "when", "quando", "hours", "horas"}
    )
    future_failure = _has_prefix(
        tokens, "durar", "falh", "quebr", "parar", "fail", "break"
    )
    return (remaining and life) or (time_question and future_failure)


def _is_execution_request(
    normalized: str, ordered_tokens: tuple[str, ...]
) -> bool:
    tokens = set(ordered_tokens)
    passive_command = any(
        phrase in normalized
        for phrase in (
            "seja executada",
            "seja executado",
            "deve ser realizada",
            "deve ser realizado",
            "precisa ser feita",
            "must be performed",
        )
    )
    command_index = 0
    if ordered_tokens[:2] == ("por", "favor"):
        command_index = 2
    elif ordered_tokens[:2] in {("can", "you"), ("could", "you")}:
        command_index = 2
    elif ordered_tokens and ordered_tokens[0] in {
        "please",
        "pode",
        "poderia",
    }:
        command_index = 1
    command = (
        ordered_tokens[command_index]
        if command_index < len(ordered_tokens)
        else ""
    )
    intervention_commands = {
        "abra",
        "aplique",
        "troque",
        "substitua",
        "desligue",
        "remova",
        "lubrifique",
        "aperte",
        "providencie",
        "conserte",
        "repare",
        "repair",
        "restart",
        "replace",
        "disconnect",
        "remove",
        "apply",
        "tighten",
    }
    generic_commands = {"faca", "execute", "realize", "perform"}
    intervention_targets = {
        "manutencao",
        "maintenance",
        "troca",
        "substituicao",
        "replacement",
        "reparo",
        "repair",
        "motor",
        "equipamento",
        "equipment",
        "rolamento",
        "bearing",
        "terminal",
        "diagnostico",
        "diagnosis",
    }
    imperative = command in intervention_commands or (
        command in generic_commands and bool(tokens & intervention_targets)
    )
    return passive_command or imperative
