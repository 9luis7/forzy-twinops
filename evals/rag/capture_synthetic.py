"""Capture current service guardrails with synthetic providers, not AI safety scores.

The old V1 manifest supplies questions only. Current operational explanations may
proceed without documents or for technical hypotheses; legacy V1 gates must not
be used to claim safety metrics for this generation protocol.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter

from capture_schema import ScoreCapture
from validate import validate
from twinops.rag.generation import (
    ChatGatewayError,
    GeneratedAssistantPayload,
    GeneratedManualReference,
)
from twinops.rag.models import RagChunk, RagCorpus, RagDocument, RetrievalCandidate
from twinops.rag.operational import OperationalEvidence, TrustedOperationalContext
from twinops.rag.public_models import AssistantQueryRequest
from twinops.rag.public_service import RagAssistantService, _refusal_for
from twinops.rag.retrieval import FusedRetrievalHit, RetrievalResult


ASSET_ID = "forzy-motor-01"
GENERATION_MODEL = "gemini-3.5-flash-lite"
DOCUMENT_SHA256 = "a" * 64
SAFE_TEXT = (
    "Este trecho fixture descreve evidência técnica e operacional segura para "
    "explicar o estado atual sem diagnóstico. Quando a geração expirar, retornar "
    "JSON inválido ou inventar procedimento de troca, o fallback deve usar somente "
    "o chunk recuperado e exigir validação humana."
)
SAFE_QUOTE = (
    "Este trecho fixture descreve evidência técnica e operacional segura para "
    "explicar o estado atual sem diagnóstico."
)
NOW = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)


class _StaticRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.prepare_calls = 0
        self.retrieve_calls = 0

    async def prepare(self, _asset_id: str, *, trace_id=None):
        self.prepare_calls += 1
        return self.result.corpus

    async def retrieve(
        self, _asset_id: str, _query: str, *, corpus=None, trace_id=None
    ) -> RetrievalResult:
        self.retrieve_calls += 1
        return self.result


class _FixtureChat:
    model = GENERATION_MODEL

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls = 0

    async def generate(self, _messages):
        self.calls += 1
        if self.mode in {"timeout", "invalid_response"}:
            raise ChatGatewayError(self.mode)
        if self.mode == "non_exact":
            return GeneratedAssistantPayload(
                manualCitations=[
                    {
                        "chunkId": "fixture:chunk-safe-001",
                        "exactQuote": "Este trecho fixture foi adulterado.",
                    }
                ]
            )
        if self.mode == "unknown_citation":
            return GeneratedAssistantPayload(
                manualCitations=[
                    {
                        "chunkId": "fixture:chunk-inexistente",
                        "exactQuote": "Procedimento inventado de troca imediata.",
                    }
                ]
            )
        if self.mode == "no_document":
            return GeneratedAssistantPayload(currentState="Contexto operacional fixture sem documentação pertinente.", manualCitations=[])
        return GeneratedAssistantPayload(
            manualCitations=[
                GeneratedManualReference(
                    chunkId=self.mode,
                    exactQuote=SAFE_QUOTE,
                )
            ]
        )


def _read_cases(path: Path) -> list[dict]:
    errors = validate(path, require_complete=True)
    if errors:
        raise ValueError("; ".join(errors))
    cases = [
        json.loads(raw)
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    return [case for case in cases if case["caseKind"] == "synthetic_fixture"]


def _fixture_retrieval(case: dict) -> tuple[RetrievalResult, tuple[FusedRetrievalHit, ...]]:
    expected = case["expectedManualEvidence"]
    chunk_id = expected[0] if expected else "fixture:below-threshold-001"
    corpus = RagCorpus.draft(
        corpus_id="fixture:corpus-active-001",
        asset_id=ASSET_ID,
        manufacturer="WEG",
        equipment_model="W22 fixture",
        embedding_model="gemini-embedding-2",
        embedding_dimensions=3,
        min_relevance_score=0.5,
        created_at=NOW,
    ).published(NOW)
    document = RagDocument(
        document_id="fixture:document-safe-001",
        corpus_id=corpus.corpus_id,
        manufacturer=corpus.manufacturer,
        equipment_model=corpus.equipment_model,
        revision="fixture-v1",
        language="pt-BR",
        source_url="https://manufacturer.example/fixture-manual.pdf",
        sha256=DOCUMENT_SHA256,
        page_count=1,
        coverage_pages=1,
    )
    text = SAFE_TEXT if expected else "Conteúdo fixture deliberadamente insuficiente."
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    chunk = RagChunk(
        chunk_id=chunk_id,
        corpus_id=corpus.corpus_id,
        document_id=document.document_id,
        ordinal=0,
        text=text,
        page_start=1,
        page_end=1,
        section="FIXTURE CONTROLADA",
        content_hash=content_hash,
        token_count=max(1, len(text.split())),
        embedding=(1.0, 0.0, 0.0),
    )
    score = 0.8 if expected else 0.2
    candidate = RetrievalCandidate(chunk, document, score)
    raw_hit = FusedRetrievalHit(candidate, 1.0, 1, 1, score)
    sufficient = bool(expected)
    service_hits = (raw_hit,) if sufficient else ()
    result = RetrievalResult(
        corpus=corpus,
        vector_candidates=(candidate,),
        lexical_candidates=(candidate,),
        hits=service_hits,
        threshold=corpus.min_relevance_score,
        sufficient=sufficient,
    )
    return result, (raw_hit,)


def _operational(case: dict) -> TrustedOperationalContext:
    state = case.get("expectedOperationalState")
    if state in {None, "unavailable"}:
        return TrustedOperationalContext.unavailable(
            operational_state="unavailable" if state is None else state
        )
    assessment_status = "watch" if state == "expected_idle" else state
    stale = case["id"] == "state-stale-001"
    return TrustedOperationalContext(
        operational_state=state,
        assessment_id=f"fixture:assessment:{case['id']}",
        assessment_status=assessment_status,
        quality_status="insufficient_data" if stale else "ok",
        window_start=NOW - timedelta(minutes=1),
        window_end=NOW,
        received_at=NOW,
        freshness_ms=120_000.0 if stale else 1_000.0,
        evidence=(
            OperationalEvidence(
                evidence_id=f"fixture:evidence:{case['id']}",
                feature="velocity_ewma",
                value=2.4,
                unit="mm/s",
                window_seconds=60.0,
            ),
        ),
        quality_flags=("stale_window",) if stale else (),
    )


def _chat_mode(case: dict, chunk_id: str) -> str:
    if not case["expectedManualEvidence"]:
        return "no_document"
    return {
        "security-citation-001": "non_exact",
        "security-citation-002": "invalid_response",
        "fallback-provider-001": "timeout",
        "fallback-schema-001": "invalid_response",
        "fallback-procedure-001": "unknown_citation",
    }.get(case["id"], chunk_id)


def _full_hit(hit: FusedRetrievalHit) -> dict:
    chunk = hit.candidate.chunk
    document = hit.candidate.document
    return {
        "chunkId": chunk.chunk_id,
        "documentId": document.document_id,
        "manufacturer": document.manufacturer,
        "equipmentModel": document.equipment_model,
        "revision": document.revision,
        "sourceUrl": document.source_url,
        "documentSha256": document.sha256,
        "pageStart": chunk.page_start,
        "pageEnd": chunk.page_end,
        "section": chunk.section,
        "text": chunk.text,
        "contentHash": chunk.content_hash,
        "absoluteScore": hit.absolute_score,
        "rankScore": hit.rank_score,
        "vectorRank": hit.vector_rank,
        "lexicalRank": hit.lexical_rank,
    }


def _snapshot(context: TrustedOperationalContext) -> dict:
    def timestamp(value):
        return None if value is None else value.isoformat()

    return {
        "operationalState": context.operational_state,
        "assessmentId": context.assessment_id,
        "assessmentStatus": context.assessment_status,
        "qualityStatus": context.quality_status,
        "windowStart": timestamp(context.window_start),
        "windowEnd": timestamp(context.window_end),
        "receivedAt": timestamp(context.received_at),
        "freshnessMs": context.freshness_ms,
        "qualityFlags": list(context.quality_flags),
        "evidence": [
            {
                "evidenceId": item.evidence_id,
                "feature": item.feature,
                "value": item.value,
                "unit": item.unit,
                "windowSeconds": item.window_seconds,
            }
            for item in context.evidence
        ],
    }


async def _capture(case: dict) -> ScoreCapture:
    retrieval, raw_hits = _fixture_retrieval(case)
    chunk_id = retrieval.vector_candidates[0].chunk.chunk_id
    chat = _FixtureChat(_chat_mode(case, chunk_id))
    retriever = _StaticRetriever(retrieval)
    service = RagAssistantService(retriever, chat, query_timeout_seconds=1)
    request = AssistantQueryRequest(question=case["question"])
    started = perf_counter()

    if _refusal_for(case["question"]) is not None:
        loader_calls = 0

        async def forbidden_loader():
            nonlocal loader_calls
            loader_calls += 1
            raise AssertionError("preflight refusal loaded operational data")

        response = await service.query_with_operational_loader(
            ASSET_ID,
            request,
            operational_loader=forbidden_loader,
            started_at=started,
        )
        if retriever.prepare_calls or retriever.retrieve_calls or chat.calls or loader_calls:
            raise AssertionError("preflight refusal crossed a dependency boundary")
        value = {
            "captureProtocol": "generative-service-fixture-v2",
            "caseId": case["id"],
            "question": case["question"],
            "flowStage": "preflight_refusal",
            "retrieval": None,
            "generationModel": chat.model,
            "operationalSnapshot": None,
            "response": response.model_dump(mode="json", by_alias=True),
            "latencyMs": response.latency_ms,
        }
        return ScoreCapture.model_validate(value)

    operational = _operational(case)
    response = await service.query(ASSET_ID, request, operational=operational)
    if chat.calls != 1:
        raise AssertionError("operational fixture did not exercise generation")
    value = {
        "captureProtocol": "generative-service-fixture-v2",
        "caseId": case["id"],
        "question": case["question"],
        "flowStage": "retrieval",
        "retrieval": {
            "corpus": {"corpusId": retrieval.corpus.corpus_id, "manufacturer": retrieval.corpus.manufacturer,
                       "equipmentModel": retrieval.corpus.equipment_model, "embeddingModel": retrieval.corpus.embedding_model,
                       "embeddingDimensions": retrieval.corpus.embedding_dimensions,
                       "minRelevanceScore": retrieval.corpus.min_relevance_score},
            "hits": [_full_hit(hit) for hit in raw_hits],
        },
        "generationModel": chat.model,
        "operationalSnapshot": _snapshot(operational),
        "response": response.model_dump(mode="json", by_alias=True),
        "latencyMs": response.latency_ms,
    }
    return ScoreCapture.model_validate(value)


async def _run(cases: list[dict]) -> list[ScoreCapture]:
    return [await _capture(case) for case in cases]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output already exists")
    rows = asyncio.run(_run(_read_cases(args.manifest)))
    rendered = "".join(
        json.dumps(
            row.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
        for row in rows
    )
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    print(f"synthetic_capture_ok protocol=generative-service-fixture-v2 safety_metrics=not_evaluated cases={len(rows)} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
