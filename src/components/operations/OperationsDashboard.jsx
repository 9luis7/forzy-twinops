import React, { useEffect, useRef, useState } from "react";
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

const historicalDateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  dateStyle: "short",
  timeStyle: "medium",
});

const historicalContextIdentity = (context) => context === null
  ? null
  : [
      context.decisionFacts.collectionState,
      context.anchor?.pointId ?? "gap",
      context.segmentId ?? "without-segment",
      context.selectedAt,
    ].join("|");

function useHistoricalCommitAnnouncement({ context, error, loading }) {
  const identity = historicalContextIdentity(context);
  const lastSeenIdentityRef = useRef(identity);
  const [announcement, setAnnouncement] = useState(null);

  useEffect(() => {
    if (context === null || loading || error !== null) {
      setAnnouncement(null);
      return;
    }
    if (identity === lastSeenIdentityRef.current) {
      setAnnouncement(null);
      return;
    }

    lastSeenIdentityRef.current = identity;
    setAnnouncement(
      `Contexto hist\u00f3rico confirmado para ${historicalDateTimeFormatter.format(new Date(context.selectedAt))}. Todos os pain\u00e9is exibem a mesma evid\u00eancia.`,
    );
  }, [context, error, identity, loading]);

  return announcement;
}

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

function RefreshAction({ busy, onRefresh }) {
  const handleClick = () => {
    if (!busy) void onRefresh();
  };

  return (
    <button
      aria-busy={busy}
      aria-disabled={busy}
      className="refresh-action"
      type="button"
      onClick={handleClick}
    >
      {busy ? <span aria-hidden="true" className="refresh-action__spinner" /> : null}
      <span>{busy ? "Consultando dados reais…" : "Atualizar agora"}</span>
    </button>
  );
}

export default function OperationsDashboard({ Twin3DComponent = null }) {
  const {
    snapshot,
    error,
    refreshing,
    lastRefreshAttemptAt,
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
  const announcementContext = viewMode === "historical"
    && historicalContext !== null
    && displayContext === historicalContext
    ? historicalContext
    : null;
  const historicalCommitAnnouncement = useHistoricalCommitAnnouncement({
    context: announcementContext,
    error: timelineErrors.context,
    loading: timelineLoading.context,
  });

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
          <RefreshAction busy={refreshing} onRefresh={refreshNow} />
          {refreshing ? (
            <p aria-live="polite" className="fatal-state__retry-status" role="status">
              Consultando o backend por um snapshot real…
            </p>
          ) : lastRefreshAttemptAt !== null ? (
            <p aria-live="polite" className="fatal-state__retry-status" role="status">
              A nova tentativa falhou. O backend continua indisponível.
            </p>
          ) : null}
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
        <RefreshAction busy={refreshing} onRefresh={refreshNow} />
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
          commitAnnouncement={historicalCommitAnnouncement}
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
