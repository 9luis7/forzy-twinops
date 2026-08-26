import React, { useEffect, useMemo, useRef, useState } from "react";
import { useOptionalTwinOps } from "../../TwinOpsContext.jsx";
import AssessmentTrend from "./AssessmentTrend.jsx";
import DecisionInspector from "./DecisionInspector.jsx";
import DecisionTimelineChart from "./DecisionTimelineChart.jsx";
import OriginalSamplesTable from "./OriginalSamplesTable.jsx";
import TimelineOverview from "./TimelineOverview.jsx";
import { buildTimelineViewModel } from "./timelineViewModel.js";

const RANGE_PRESETS = Object.freeze([
  ["historical", "Histórico avaliado"],
  ["7d", "Coletas recentes"],
  ["all", "Visão completa"],
]);

export default function TimelineWorkspace({
  overview,
  assessmentOverview = undefined,
  page,
  context,
  loading,
  errors,
  pendingSelection,
  selectTimelinePoint,
  rangePreset = "7d",
  onRangePresetChange = () => undefined,
  commitAnnouncement = null,
  children,
}) {
  const twinOps = useOptionalTwinOps();
  const evidenceDetailsRef = useRef(null);
  const [requestedPointId, setRequestedPointId] = useState(null);
  const [visibleSensors, setVisibleSensors] = useState(() => new Set(["s1", "s2"]));
  const resolvedAssessmentOverview = assessmentOverview === undefined
    ? twinOps?.timelineAssessmentOverview ?? null
    : assessmentOverview;
  const assessmentsLoading = loading?.assessments
    ?? twinOps?.timelineLoading?.assessments
    ?? false;
  const assessmentsError = errors?.assessments
    ?? twinOps?.timelineErrors?.assessments
    ?? null;
  const model = useMemo(
    () => overview === null ? null : buildTimelineViewModel(overview),
    [overview],
  );
  const liveOnly = overview?.capabilities?.historical === false;
  const historicalNavigationAvailable = overview?.capabilities?.historical === true;
  const sourceKinds = new Set(overview?.segments?.map((segment) => segment.sourceKind) ?? []);
  const hasHistoricalArchive = sourceKinds.has("historical_archive");
  const spansHistoricalAndLive = hasHistoricalArchive
    && sourceKinds.has("live_collection");
  const selectedPointId = context?.anchor?.pointId ?? null;
  const aggregation = overview?.aggregationSummary ?? null;
  const selectPoint = (pointId) => {
    setRequestedPointId(pointId);
    void selectTimelinePoint(pointId);
  };
  const openEvidence = () => {
    if (evidenceDetailsRef.current !== null) {
      evidenceDetailsRef.current.open = true;
      evidenceDetailsRef.current.querySelector("summary")?.focus();
    }
  };
  const toggleSensor = (sensorId) => {
    setVisibleSensors((current) => {
      const next = new Set(current);
      if (next.has(sensorId)) next.delete(sensorId);
      else next.add(sensorId);
      return next;
    });
  };

  useEffect(() => {
    if (liveOnly && rangePreset !== "all") {
      void onRangePresetChange("all");
    }
  }, [liveOnly, onRangePresetChange, rangePreset]);

  return (
    <section className="timeline-workspace decision-console" data-testid="timeline-workspace" aria-labelledby="timeline-title">
      <header className="decision-console__toolbar">
        <div className="decision-console__title">
          <p className="eyebrow">{liveOnly ? "Coleta operacional" : "Histórico operacional"}</p>
          <h2 id="timeline-title">Console de decisão</h2>
          <p>
            {liveOnly
              ? "Leituras ao vivo publicadas, sem profundidade histórica simulada."
              : "Telemetria, scores persistidos e evidência do ponto no mesmo eixo temporal."}
          </p>
        </div>

        <div className="decision-console__summary" aria-label="Resumo da consulta">
          <span data-status={errors?.overview ? "warning" : "ready"}>
            {errors?.overview ? "Cobertura parcial" : liveOnly ? "Coleta ao vivo" : "Histórico validado"}
          </span>
          {aggregation === null ? null : (
            <small>
              {liveOnly
                ? `${aggregation.originalPointCount} leituras ao vivo disponíveis`
                : `${aggregation.returnedPointCount} pontos representativos no gráfico · ${aggregation.originalPointCount} leituras persistidas`}
            </small>
          )}
        </div>

        {liveOnly ? (
          <div className="decision-console__availability">
            <strong>Sem lote histórico ativo</strong>
            <span>A consulta carrega tudo o que foi publicado; o gráfico abre no trecho recente. Use Ctrl + roda para zoom e arraste para navegar.</span>
          </div>
        ) : (
          <div aria-label="Período exibido" className="decision-console__range" role="group">
            {RANGE_PRESETS.map(([value, label]) => (
              <button
                aria-pressed={rangePreset === value}
                disabled={value === "historical" && !historicalNavigationAvailable}
                key={value}
                onClick={() => { void onRangePresetChange(value); }}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {!liveOnly && rangePreset === "7d" ? (
          <div className="decision-console__availability">
            <strong>Coletas recentes sem avaliação histórica</strong>
            <span>
              Os scores pertencem ao lote histórico avaliado; nenhum valor recente foi inventado
              ou preenchido com zero. As linhas conectam apenas leituras persistidas do mesmo
              sensor no mesmo dia de coleta, no horário de São Paulo; intervalos entre dias e
              mudanças de origem permanecem separados.
            </span>
          </div>
        ) : null}

        {!liveOnly && rangePreset === "all" && spansHistoricalAndLive ? (
          <div className="decision-console__availability">
            <strong>Visão completa preserva os intervalos sem coleta</strong>
            <span>
              Intervalos longos aparecem como espaço sem dados. Selecione Histórico avaliado para
              analisar a telemetria e os scores no período denso.
            </span>
          </div>
        ) : null}

        <fieldset className="decision-console__sensors">
          <legend>Sensores visíveis</legend>
          {["s1", "s2"].map((sensorId) => (
            <label key={sensorId}>
              <input
                checked={visibleSensors.has(sensorId)}
                onChange={() => toggleSensor(sensorId)}
                type="checkbox"
              />
              <span data-sensor={sensorId}>{sensorId.toUpperCase()}</span>
            </label>
          ))}
        </fieldset>
      </header>

      <div className="decision-console__workspace">
        <div className="decision-console__charts">
          {loading?.overview ? (
            <p className="timeline-inline-status" role="status">
              {overview === null
                ? "Carregando cobertura histórica…"
                : "Atualizando a cobertura; a última linha válida continua visível."}
            </p>
          ) : null}
          {errors?.overview ? (
            <p className="timeline-inline-warning" role="alert">
              {overview === null
                ? "A cobertura histórica está indisponível para esta consulta."
                : "A cobertura não pôde ser atualizada. O último gráfico válido continua visível."}
            </p>
          ) : null}
          {assessmentsLoading ? (
            <p className="timeline-inline-status" role="status">
              {resolvedAssessmentOverview === null
                ? "Carregando scores persistidos…"
                : "Atualizando os scores; a última série válida continua visível."}
            </p>
          ) : null}
          {assessmentsError ? (
            <p className="timeline-inline-warning" role="alert">
              {resolvedAssessmentOverview === null
                ? "Os scores persistidos estão indisponíveis para esta consulta."
                : "As avaliações não puderam ser atualizadas. A última série válida continua visível."}
            </p>
          ) : null}
          {loading?.context && requestedPointId !== null ? (
            <p className="timeline-inline-status" role="status">
              Carregando ponto selecionado…
            </p>
          ) : null}
          {model === null && !loading?.overview && !errors?.overview ? (
            <p className="timeline-empty">Cobertura histórica indisponível para esta consulta.</p>
          ) : null}
          {model === null ? null : (
            <DecisionTimelineChart
              assessmentOverview={resolvedAssessmentOverview}
              frameFullDomain={rangePreset !== "7d"}
              model={model}
              onSelectPoint={selectPoint}
              pendingPointId={pendingSelection?.pointId
                ?? (loading?.context ? requestedPointId : null)}
              selectedAt={context?.selectedAt ?? null}
              selectedPointId={selectedPointId}
              visibleSensors={visibleSensors}
            />
          )}
        </div>

        <DecisionInspector
          context={context}
          error={errors?.context ?? null}
          loading={loading?.context ?? false}
          onOpenEvidence={openEvidence}
          onRetry={selectPoint}
          requestedPointId={requestedPointId}
        />
      </div>

      {commitAnnouncement === null ? null : (
        <p
          aria-atomic="true"
          aria-live="polite"
          className="visually-hidden timeline-context-commit-status"
          role="status"
        >
          {commitAnnouncement}
        </p>
      )}

      <details className="decision-console__evidence" ref={evidenceDetailsRef}>
        <summary>Evidência técnica e leituras originais</summary>
        <div className="decision-console__evidence-body">
          <p>
            Esta área preserva segmentos, lacunas, metadados do modelo e as leituras originais
            para auditoria. Ela não altera o ponto selecionado no console.
          </p>
          {model === null ? null : <TimelineOverview model={model} />}
          {resolvedAssessmentOverview === null ? null : (
            <AssessmentTrend overview={resolvedAssessmentOverview} />
          )}
          {children}
          <OriginalSamplesTable
            error={errors?.page ?? null}
            loading={loading?.page ?? false}
            page={page}
            pendingSelection={pendingSelection}
            selectedPointId={selectedPointId}
            selectTimelinePoint={selectPoint}
          />
        </div>
      </details>
    </section>
  );
}
