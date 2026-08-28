import React, {
  Suspense,
  lazy,
  startTransition,
  useCallback,
  useEffect,
  useState,
} from "react";
import { useTwinOps } from "../../TwinOpsContext.jsx";
import LoadingState from "../LoadingState.jsx";
import AssessmentPanel from "./AssessmentPanel.jsx";
import AssetHeader from "./AssetHeader.jsx";
import IntegrationHealth from "./IntegrationHealth.jsx";
import SensorCard from "./SensorCard.jsx";

const loadTelemetryTrend = () => import("./TelemetryTrend.jsx");
const LazyTelemetryTrend = lazy(loadTelemetryTrend);

// Start downloading the core visualization while the snapshot request is in flight.
void loadTelemetryTrend();

const SNAPSHOT_LOADING_MESSAGES = [
  "Conectando ao snapshot operacional…",
  "Validando telemetria S1 e S2…",
  "Preparando o painel operacional…",
  "Reservando o 3D para a etapa final…",
];

const TREND_LOADING_MESSAGES = [
  "Organizando os pontos reais por canal…",
  "Preparando as séries completas de S1 e S2…",
  "Montando a tendência operacional…",
];

const TWIN_DEFERRED_MESSAGES = [
  "Priorizando os dados operacionais…",
  "Aguardando a tendência real ficar disponível…",
  "O modelo interativo será carregado por último…",
];

function scheduleAfterPaint(callback) {
  if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
    const frame = window.requestAnimationFrame(callback);
    return () => window.cancelAnimationFrame?.(frame);
  }
  const timer = setTimeout(callback, 0);
  return () => clearTimeout(timer);
}

function scheduleWhenIdle(callback) {
  if (typeof window !== "undefined" && typeof window.requestIdleCallback === "function") {
    const idleCallback = window.requestIdleCallback(callback, { timeout: 1_200 });
    return () => window.cancelIdleCallback?.(idleCallback);
  }
  const timer = setTimeout(callback, 0);
  return () => clearTimeout(timer);
}

function useProgressiveSections(hasSnapshot) {
  const [trendReady, setTrendReady] = useState(false);
  const [showSecondary, setShowSecondary] = useState(false);
  const [showTwin, setShowTwin] = useState(false);

  useEffect(() => {
    if (!hasSnapshot || !trendReady) return undefined;
    return scheduleAfterPaint(() => {
      startTransition(() => setShowSecondary(true));
    });
  }, [hasSnapshot, trendReady]);

  useEffect(() => {
    if (!hasSnapshot || !showSecondary) return undefined;
    return scheduleWhenIdle(() => {
      startTransition(() => setShowTwin(true));
    });
  }, [hasSnapshot, showSecondary]);

  const markTrendReady = useCallback(() => setTrendReady(true), []);
  return { markTrendReady, showSecondary, showTwin };
}

function DeferredTelemetryTrend({ history, onReady }) {
  useEffect(() => {
    onReady();
  }, [onReady]);

  return <LazyTelemetryTrend history={history} />;
}

function ProgressivePanelLoading({ eyebrow, title, label, messages, variant = "panel" }) {
  return (
    <section className="panel progressive-panel-loading" aria-label={title}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </div>
      <LoadingState label={label} messages={messages} variant={variant} />
    </section>
  );
}

function DashboardSkeletonPanel({ eyebrow, title, wide = false }) {
  return (
    <section
      aria-hidden="true"
      className={`panel dashboard-skeleton-panel${wide ? " dashboard-skeleton-panel--wide" : ""}`}
    >
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <div className="dashboard-skeleton-lines">
        <span />
        <span />
        <span />
      </div>
    </section>
  );
}

function DashboardLoadingShell() {
  return (
    <main
      aria-busy="true"
      className="operations-shell dashboard-loading-shell"
      data-testid="dashboard-loading-shell"
    >
      <header className="asset-header dashboard-loading-header">
        <div>
          <p className="eyebrow">TwinOps</p>
          <h1>Visão operacional real</h1>
          <p className="asset-tag">
            Os dados reais aparecerão por etapas assim que o snapshot responder.
          </p>
        </div>
        <p className="operational-state">Conectando à origem</p>
      </header>

      <section className="panel snapshot-loading-panel">
        <LoadingState
          label="Carregando o último snapshot real…"
          messages={SNAPSHOT_LOADING_MESSAGES}
          variant="panel"
        />
      </section>

      <div className="dashboard-skeleton-grid">
        <DashboardSkeletonPanel eyebrow="Prioridade de carregamento" title="Tendência operacional real" wide />
        <DashboardSkeletonPanel eyebrow="Telemetria real" title="Canais S1 e S2" />
        <DashboardSkeletonPanel eyebrow="Contexto operacional" title="Avaliação e integração" />
        <DashboardSkeletonPanel eyebrow="Geometria interativa" title="O 3D entra por último" wide />
      </div>
    </main>
  );
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

export default function OperationsDashboard({ Twin3DComponent = null }) {
  const { snapshot, error, refreshing, refreshNow } = useTwinOps();
  const { markTrendReady, showSecondary, showTwin } = useProgressiveSections(Boolean(snapshot));

  if (!snapshot && !error) {
    return <DashboardLoadingShell />;
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

  const fallback = <TwinFallback />;

  return (
    <main className="operations-shell">
      <AssetHeader asset={snapshot.asset} operationalState={snapshot.operationalState} />

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

      <Suspense
        fallback={(
          <ProgressivePanelLoading
            eyebrow="Histórico coletado pelo TwinOps"
            title="Tendência operacional real"
            label="Carregando todo o histórico real…"
            messages={TREND_LOADING_MESSAGES}
          />
        )}
      >
        <DeferredTelemetryTrend history={snapshot.history} onReady={markTrendReady} />
      </Suspense>

      {showSecondary ? (
        <>
          <section className="sensor-grid" aria-label="Valores atuais dos sensores">
            {snapshot.channels.map((channel) => (
              <SensorCard channel={channel} key={channel.sensorId} />
            ))}
          </section>

          <section className="details-grid">
            <AssessmentPanel assessment={snapshot.assessment} />
            <IntegrationHealth integration={snapshot.integration} />
          </section>
        </>
      ) : (
        <div
          className="dashboard-skeleton-grid"
          aria-label="Dados complementares serão carregados depois do gráfico"
        >
          <DashboardSkeletonPanel eyebrow="Próxima etapa" title="Canais e medições" />
          <DashboardSkeletonPanel eyebrow="Próxima etapa" title="Modelo e integração" />
        </div>
      )}

      {showTwin ? (
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
      ) : (
        <ProgressivePanelLoading
          eyebrow="Geometria do conjunto fornecido"
          title="Gêmeo 3D"
          label="O gêmeo 3D será carregado depois dos dados…"
          messages={TWIN_DEFERRED_MESSAGES}
          variant="twin"
        />
      )}

      <footer className="operations-footer">
        <p>
          A API atual não comprova o frescor físico na origem, antecedência de falha ou SLA
          industrial.
        </p>
      </footer>
    </main>
  );
}
