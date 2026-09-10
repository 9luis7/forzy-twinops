import React, { useEffect, useMemo, useRef, useState } from "react";
import CopilotDock from "../components/assistant/CopilotDock.jsx";
import TechnicalAssistantPanel from "../components/operations/TechnicalAssistantPanel.jsx";
import { formatDateTime } from "../lib/displayTime.js";
import { evidenceLabel, evidenceUnit } from "../components/assistant/ConciseAnswer.jsx";
import { parseHistoricalAssistantResponse } from "./GatewayHistoryDataSource.js";

const labels = { normal: "Sem desvio relevante", watch: "Atenção", alert: "Alerta relativo", insufficient_data: "Dados insuficientes", unknown: "Sem avaliação" };
const date = (value) => formatDateTime(value, "Não informado");
const number = (value) => value.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
const statusNotices = { operational_unavailable: "A referência documental e a avaliação histórica estão separadas abaixo. A coleta atual não foi consultada." };

function HistoricalEvidence({ response }) {
  return <div className="historical-answer-evidence" aria-label="Evidências do instante histórico">
    {response.historicalEvidence.map((sensor) => <details className="assistant-citation" key={sensor.sensorId}>
      <summary>{sensor.sensorId.toUpperCase()} · {sensor.component === "motor" ? "Motor" : "Bomba"} · {labels[sensor.status]}</summary>
      <div className="assistant-citation__body">
        <p>Registro {sensor.sourceRow} · {date(sensor.observedAt)} · São Paulo</p>
        <p>Vínculo e posição assumidos no modelo 3D.</p>
        <p>Qualidade dos dados: {({ ok: "sem alertas", degraded: "com ressalvas", insufficient_data: "dados insuficientes", unavailable: "indisponível" })[sensor.qualityStatus] ?? "não informada"}.</p>
        {Number.isFinite(sensor.anomalyScore) && <p>Score relativo {number(sensor.anomalyScore)}{Number.isFinite(sensor.deteriorationScore) ? ` · deterioração ${number(sensor.deteriorationScore)}` : ""}{Number.isFinite(sensor.persistenceSeconds) ? ` · persistência ${number(sensor.persistenceSeconds)} s` : ""}.</p>}
        {sensor.evidence.length ? <ul>{sensor.evidence.map((item) => <li key={item.id}>{evidenceLabel(item.feature)}: {number(item.value)} {evidenceUnit(item.unit)}{item.windowSeconds === null ? "" : ` · janela de ${number(item.windowSeconds)} s`}</li>)}</ul> : <p>Sem evidências numéricas suficientes neste instante.</p>}
        <p>Janela avaliada: {date(sensor.windowStart)} — {date(sensor.windowEnd)} · São Paulo</p>
        {sensor.trainedUntil && <p>Modelo treinado com dados até {date(sensor.trainedUntil)} · São Paulo</p>}
        <p>Avaliação retrospectiva; não representa probabilidade de falha.</p>
      </div>
    </details>)}
  </div>;
}
const renderEvidence = (response) => <HistoricalEvidence response={response} />;

export default function HistoricalCopilot({ context, dataSource, open, onOpenChange }) {
  const identity = `${context.dataset.datasetId}:${context.revision}`;
  const previousIdentity = useRef(identity);
  const [contextChanged, setContextChanged] = useState(false);
  const available = context.capabilities.copilot === true && typeof dataSource.query === "function";
  useEffect(() => {
    if (identity !== previousIdentity.current) setContextChanged(true);
    previousIdentity.current = identity;
  }, [identity]);
  const adapter = useMemo(() => ({
    query: async (_assetId, input, options) => {
      setContextChanged(false);
      const { from, to, endRow, limit } = context.selection;
      const wrapper = await dataSource.query(context.dataset.datasetId, {
        ...input, selection: { from, to, endRow, limit }, contextRevision: context.revision,
      }, options);
      const validated = parseHistoricalAssistantResponse(wrapper, {
        datasetId: context.dataset.datasetId, contextRevision: context.revision, selection: context.selection,
      });
      return { ...validated.response, historicalEvidence: validated.historicalEvidence };
    },
  }), [dataSource, context.dataset.datasetId, context.revision, context.selection.from, context.selection.to, context.selection.endRow, context.selection.limit, context.selection.observedAt]);

  return <CopilotDock open={open} onOpenChange={onOpenChange} available={available} contextLabel={`Histórico · ${date(context.selection.observedAt)} · São Paulo`}>
    <p className="historical-copilot-context">A pergunta usa o instante e a janela exibidos. O manual WEG W22 cobre o motor; a cobertura da bomba não é afirmada.</p>
    {contextChanged && <p className="historical-notice" role="status">O instante consultado mudou. A conversa anterior foi encerrada; a próxima pergunta usará a nova seleção.</p>}
    <TechnicalAssistantPanel key={identity} assetId={context.assetId} enabled={available} dataSource={adapter} isActive={open}
      stateLabel="Estado no instante histórico" renderStateEvidence={renderEvidence} statusNotices={statusNotices}
      suggestionContext={{ status: context.sensors?.s1?.assessment?.assessment?.status ?? context.status, sensor: "s1" }} />
  </CopilotDock>;
}
