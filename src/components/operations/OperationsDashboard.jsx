import React from "react";
import { useTwinOps } from "../../TwinOpsContext.jsx";
import LoadingState from "../LoadingState.jsx";
import TimelineWorkspace from "../timeline/TimelineWorkspace.jsx";
import HistoricalContextEvidence from "../timeline/HistoricalContextEvidence.jsx";
import { resolveOperationsDisplay } from "../timeline/timelineViewModel.js";
import AssessmentPanel from "./AssessmentPanel.jsx";
import AssetHeader from "./AssetHeader.jsx";
import IntegrationHealth from "./IntegrationHealth.jsx";
import SensorCard from "./SensorCard.jsx";
import TelemetryTrend from "./TelemetryTrend.jsx";

const SNAPSHOT_LOADING_MESSAGES = [
  "Conectando ao snapshot operacional…",
  "Validando telemetria S1 e S2…",
  "Preparando o painel operacional…",
  "Sincronizando o gêmeo digital…",
];

export function TwinFallback() {
  return (
    <div className="twin-fallback">
      <img
        src="/models/conjunto-motor-bomba-preview.png"
        alt="Prévia estática do conjunto motor-bomba derivada do STEP fornecido"
        loading="lazy"
      />
      <span>Visualização 3D indisponível</span>
      <small>Os dados operacionais não são simulados neste fallback.</small>
    </div>
  );
}

export default function OperationsDashboard({ Twin3DComponent = null }) {
  const {
    snapshot,
    error,
    refreshing,
    refreshNow,
    viewMode,
    timelineOverview,
    timelinePage,
    pendingSelection,
    historicalContext,
    displayContext,
    timelineLoading,
    timelineErrors,
    showNow,
    showHistory,
    selectTimelinePoint,
  } = useTwinOps();

  if (!snapshot && !error) {
    return (
      <main className="operations-shell operations-shell--centered">
        <LoadingState
          label="Carregando o último snapshot real…"
          messages={SNAPSHOT_LOADING_MESSAGES}
          variant="panel"
        />
      </main>
    );
  }

  if (!snapshot) {
    return (
      <main className="operations-shell operations-shell--centered">
        <section className="fatal-state" role="alert">
          <p className="eyebrow">TwinOps</p>
          <h1>Dados reais indisponíveis</h1>
          <p>O backend não forneceu um snapshot válido. Nenhum dado sintético foi usado.</p>
          <button type="button" onClick={() => void refreshNow()} disabled={refreshing}>
            {refreshing ? "Atualizando…" : "Atualizar agora"}
          </button>
        </section>
      </main>
    );
  }

  const {
    committedHistoricalContext,
    displayViewMode,
    channels: displayedChannels,
    assessment: displayedAssessment,
    operationalState: displayedOperationalState,
  } = resolveOperationsDisplay({ snapshot, viewMode, historicalContext, displayContext });
  const fallback = <TwinFallback />;
  const contextualPanels = (
    <section
      aria-label={displayViewMode === "historical"
        ? "Contexto histórico sincronizado"
        : "Contexto Agora preservado"}
      className="contextual-panels"
    >
      {committedHistoricalContext === null ? null : (
        <HistoricalContextEvidence context={committedHistoricalContext} />
      )}

      <section className="sensor-grid" aria-label="Sensores no contexto exibido">
        {displayedChannels.map((channel, index) => {
          const sensorId = index === 0 ? "s1" : "s2";
          return (
            <SensorCard
              channel={channel}
              historical={displayViewMode === "historical"}
              key={sensorId}
              sensorId={sensorId}
            />
          );
        })}
      </section>

      <section className={`details-grid${displayViewMode === "historical" ? " details-grid--historical" : ""}`}>
        <AssessmentPanel
          assessment={displayedAssessment}
          historical={displayViewMode === "historical"}
        />
        {displayViewMode === "now" ? <IntegrationHealth integration={snapshot.integration} /> : null}
      </section>

      {displayViewMode === "now" ? (
        <TelemetryTrend history={snapshot.history} />
      ) : null}
    </section>
  );

  return (
    <main className="operations-shell">
      <AssetHeader
        asset={snapshot.asset}
        onShowHistory={showHistory}
        onShowNow={showNow}
        operationalState={displayedOperationalState}
        displayViewMode={displayViewMode}
        selectedAt={committedHistoricalContext?.selectedAt ?? null}
        timelineLoading={timelineLoading.overview || timelineLoading.page || timelineLoading.context}
        viewMode={viewMode}
      />

      <div className="dashboard-actions">
        <p>Atualização automática apenas seg/ter/qua, das 12h às 14h (America/Sao_Paulo).</p>
        <button type="button" onClick={() => void refreshNow()} disabled={refreshing}>
          {refreshing ? "Atualizando…" : "Atualizar agora"}
        </button>
      </div>

      {error && (
        <p className="warning-banner" role="alert">
          A atualização falhou. O último dado real conhecido continua visível.
        </p>
      )}
      {snapshot.operationalState === "unavailable" && (
        <p className="warning-banner">Nenhuma leitura real foi persistida ainda.</p>
      )}

      {viewMode === "historical" ? (
        <TimelineWorkspace
          context={committedHistoricalContext}
          errors={timelineErrors}
          loading={timelineLoading}
          overview={timelineOverview}
          page={timelinePage}
          pendingSelection={pendingSelection}
          selectTimelinePoint={selectTimelinePoint}
        >
          {contextualPanels}
        </TimelineWorkspace>
      ) : (
        contextualPanels
      )}

      <section className="panel twin-panel" aria-labelledby="twin-title">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Geometria do conjunto fornecido</p>
            <h2 id="twin-title">Gêmeo 3D</h2>
          </div>
        </div>
        {Twin3DComponent ? (
          <Twin3DComponent
            snapshot={snapshot}
            fallback={fallback}
            viewMode={displayViewMode}
            displayContext={committedHistoricalContext ?? snapshot}
          />
        ) : fallback}
      </section>

      <footer className="operations-footer">
        <p>
          A API atual não comprova o frescor físico na origem, antecedência de falha ou SLA
          industrial.
        </p>
      </footer>
    </main>
  );
}
