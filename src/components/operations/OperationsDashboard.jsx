import React, { lazy, Suspense, useState } from "react";
import { useTwinOps } from "../../TwinOpsContext.jsx";
import LoadingState from "../LoadingState.jsx";
import AssessmentPanel from "./AssessmentPanel.jsx";
import AssetHeader from "./AssetHeader.jsx";
import IntegrationHealth from "./IntegrationHealth.jsx";
import SensorCard from "./SensorCard.jsx";
import TechnicalAssistantPanel from "./TechnicalAssistantPanel.jsx";
import TelemetryTrend from "./TelemetryTrend.jsx";
import OperationalSummary from "./OperationalSummary.jsx";
import CopilotDock from "../assistant/CopilotDock.jsx";

const HistoricalWorkspace = lazy(() => import("../../history/HistoricalWorkspace.jsx"));

const SNAPSHOT_LOADING_MESSAGES = [
  "Conectando à fonte de dados…",
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

export default function OperationsDashboard({ Twin3DComponent = null, ragDataSource, historyDataSource }) {
  const { assetId, snapshot, error, refreshing, refreshNow } = useTwinOps();
  const [copilotOpen, setCopilotOpen] = useState(false);

  if (!snapshot && !error) {
    return (
      <main className="operations-shell operations-shell--centered">
        <LoadingState
          label="Consultando os dados do equipamento…"
          messages={SNAPSHOT_LOADING_MESSAGES}
          variant="panel"
        />
      </main>
    );
  }

  if (!snapshot) {
    if (historyDataSource) {
      return (
        <main className="operations-shell">
          <header className="overview-heading">
            <div><p className="eyebrow">Visão geral</p><h1>Motor e bomba</h1></div>
            <button className="button-secondary" type="button" onClick={() => void refreshNow()} disabled={refreshing}>
              {refreshing ? "Atualizando…" : "Atualizar agora"}
            </button>
          </header>
          <Suspense fallback={<p role="status">Consultando o histórico disponível…</p>}>
            <HistoricalWorkspace dataSource={historyDataSource} compact liveUnavailable Twin3DComponent={Twin3DComponent ?? undefined} />
          </Suspense>
        </main>
      );
    }
    return (
      <main className="operations-shell operations-shell--centered">
        <section className="fatal-state" role="alert">
          <p className="eyebrow">TwinOps</p>
          <h1>Dados reais indisponíveis</h1>
          <p>Não foi possível consultar os dados do equipamento. Tente novamente em instantes.</p>
          <button type="button" onClick={() => void refreshNow()} disabled={refreshing}>
            {refreshing ? "Atualizando…" : "Atualizar agora"}
          </button>
        </section>
      </main>
    );
  }

  const fallback = <TwinFallback />;

  return (
    <main className={`operations-shell${copilotOpen ? " has-copilot-open" : ""}`}>
      <AssetHeader asset={snapshot.asset} operationalState={snapshot.operationalState} />

      <OperationalSummary snapshot={snapshot} />

      <div className="dashboard-actions">
        <p>Consulta automática: segunda a quarta, das 12h às 14h, horário de São Paulo.</p>
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

      <section className="sensor-grid" aria-label="Valores disponíveis dos sensores">
        {snapshot.channels.map((channel) => (
          <SensorCard channel={channel} key={channel.sensorId} />
        ))}
      </section>

      <TelemetryTrend history={snapshot.history} />

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
          />
        ) : fallback}
      </section>

      <section className="details-grid">
        <AssessmentPanel assessment={snapshot.assessment} />
        <IntegrationHealth integration={snapshot.integration} />
      </section>

      <CopilotDock open={copilotOpen} onOpenChange={setCopilotOpen}
        available={snapshot.capabilities.copilot === true}
        contextLabel="Últimos dados operacionais disponíveis · Manual do motor WEG">
        <TechnicalAssistantPanel
          assetId={assetId}
          enabled={snapshot.capabilities.copilot === true}
          dataSource={ragDataSource}
          isActive={copilotOpen}
        />
      </CopilotDock>

      <footer className="operations-footer">
        <p>
          A API atual não comprova o frescor físico na origem, antecedência de falha ou SLA
          industrial.
        </p>
      </footer>
    </main>
  );
}
