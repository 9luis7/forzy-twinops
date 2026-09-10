"""Generative analysis bound to a server-selected historical cutoff.

Both sensors and bounded prior readings feed the shared generation service.
Historical evidence remains distinct from live telemetry and receipt times.
"""

import asyncio
from copy import deepcopy
from dataclasses import replace

from twinops.rag.demo_service import DEMO_TOTAL_SECONDS, DemoRagAssistantService
from twinops.rag.operational import TrustedOperationalContext, build_analysis_context
from twinops.rag.public_models import AssistantQueryRequest
from twinops.rag.public_service import _concise_condition, _sao_paulo_time

from .assistant_models import HistoricalQueryResponse, HistoricalSensorEvidence
from .service import HistoryError, HistoryService, selection_time


HISTORICAL_LIMITATIONS = (
    "Cobertura documental: motor WEG W22 (S1). O corpus não cobre a bomba (S2); "
    "orientações do motor não são procedimentos de manutenção da bomba.",
    "S1 no motor e S2 na bomba são associações e posições assumidas junto ao "
    "acoplamento, sem validação física.",
    "A análise pertence ao instante e ao período históricos indicados, não ao "
    "estado atual do equipamento. O horário de recebimento original é desconhecido.",
    "Análise retrospectiva: scores são relativos ao baseline histórico, não "
    "probabilidades de falha nem prova de antecipação fora da amostra. "
    "A data de treinamento do baseline permanece indicada nas evidências.",
)
def _historical_evidence(context):
    if context.get("schemaVersion") != "historical-1.0" or context.get("mode") != "historical":
        raise ValueError("invalid historical context")
    selection = context["selection"]
    selected_at = selection_time(selection["observedAt"])
    projected = []
    for sensor_id, component in (("s1", "motor"), ("s2", "bomba")):
        sensor = context["sensors"][sensor_id]
        latest, assessment = sensor["latest"], sensor["assessment"] or {}
        if (latest["sensorId"] != sensor_id or latest["sourceRow"] != selection["endRow"]
                or selection_time(latest["observedAt"]) != selected_at):
            raise ValueError("historical sensor selection mismatch")
        if assessment.get("sensorId", sensor_id) != sensor_id:
            raise ValueError("historical assessment sensor mismatch")
        window = assessment.get("window", {})
        start, end = window.get("start"), window.get("end")
        if bool(start) != bool(end):
            raise ValueError("incomplete historical assessment window")
        if end and not selection_time(start) <= selection_time(end) <= selected_at:
            raise ValueError("future historical assessment")
        projected.append(HistoricalSensorEvidence(
            sensorId=sensor_id, component=component, observedAt=latest["observedAt"],
            sourceRow=latest["sourceRow"], assessmentId=assessment.get("assessmentId"),
            status=assessment.get("assessment", {}).get("status", "unknown"),
            qualityStatus=assessment.get("quality", {}).get("status", "unavailable"),
            qualityFlags=list(dict.fromkeys(latest.get("qualityFlags", [])
                                           + assessment.get("quality", {}).get("flags", []))),
            windowStart=start, windowEnd=end,
            trainedUntil=assessment.get("model", {}).get("trainedUntil"),
            scoreSemantics=assessment.get("assessment", {}).get("scoreSemantics"),
            anomalyScore=assessment.get("assessment", {}).get("anomalyScore"),
            deteriorationScore=assessment.get("assessment", {}).get("deteriorationScore"),
            persistenceSeconds=assessment.get("assessment", {}).get("persistenceSeconds"),
            evidence=[{key: item[key] for key in ("id", "feature", "value", "unit", "windowSeconds",
                      "baseline", "deviation", "direction", "robustScale", "normalizedDistance",
                      "anomalyScoreComponent", "positiveScoreComponent") if key in item}
                      for item in assessment.get("evidence", [])],
        ))
    return projected


def _current_state(context, evidence, *, include_evidence=True):
    instant = selection_time(context["selection"]["observedAt"])
    return (
        f"Histórico de {_sao_paulo_time(instant)}. "
        + " ".join(f"{item.sensor_id.upper()} ({item.component}): "
                   + _concise_condition(item.status, item.evidence if include_evidence else (), item.quality_status) + "."
                   for item in evidence)
    )


class HistoricalAssistantService:
    def __init__(self, history: HistoryService, assistant: DemoRagAssistantService):
        self.history, self.assistant = history, assistant

    async def query(self, dataset_id, request):
        async with asyncio.timeout(DEMO_TOTAL_SECONDS):
            # Resolve and detach everything before the first provider await.
            # The browser supplies only selection coordinates, never measurements.
            selection = request.selection
            context = deepcopy(await asyncio.to_thread(
                self.history.context, dataset_id, from_time=selection.from_time,
                to_time=selection.to_time, end_row=selection.end_row, limit=selection.limit,
            ))
            if (context["revision"] != request.context_revision
                    or context["dataset"]["datasetId"] != dataset_id
                    or context["selection"]["endRow"] != selection.end_row):
                raise HistoryError(409, "historical_context_changed")
            evidence = _historical_evidence(context)
            # Expand only backwards within the same selected dataset/range. The
            # immutable selected end and response revision remain unchanged.
            if selection.limit < 300:
                expanded = await asyncio.to_thread(
                    self.history.context, dataset_id, from_time=selection.from_time,
                    to_time=selection.to_time, end_row=selection.end_row, limit=300,
                )
                context["history"] = deepcopy(expanded["history"])
            operational = replace(
                TrustedOperationalContext.unavailable(operational_state="historical"),
                analysis_context=build_analysis_context(context),
            )
            response = await self.assistant.query(
                context["assetId"], AssistantQueryRequest(
                    question=request.question, conversationId=request.conversation_id,
                    history=request.history,
                ), operational=operational,
            )
            body = response.model_dump(mode="json", by_alias=True)
            if getattr(getattr(response, "generation", None), "status", None) != "generated":
                body["answer"]["currentState"] = _current_state(
                    context, evidence, include_evidence=response.grounding_status != "out_of_scope",
                )
            body["citations"] = [citation for citation in body["citations"] if citation["type"] == "manual"]
            body["limitations"] = list(dict.fromkeys(body["limitations"] + list(HISTORICAL_LIMITATIONS)))
            # Preserve grounded/degraded/refusal outcomes from the shared service.
            # A retrospective score never promotes documentary grounding.
            return HistoricalQueryResponse(
                contextRevision=context["revision"], datasetId=context["dataset"]["datasetId"],
                selection=context["selection"], response=body, historicalEvidence=evidence,
            ).model_dump(mode="json", by_alias=True)
