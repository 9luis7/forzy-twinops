// LiveTwinContext.jsx — FONTE ÚNICA DA VERDADE do motor-estrela (MTR-BMB-042).
//
// O loop de cenários ao vivo roda UMA ÚNICA VEZ aqui (provider no topo do app) e
// todo o restante — perfil, árvore de TAGs, cards, sinótico da planta, KPIs,
// central de alertas, copiloto e auditoria — lê o estado do estrela a partir
// deste contexto. Assim não há duas verdades: o que o gráfico mostra é o que os
// gauges, o gêmeo digital, o LED da árvore e o alerta mostram, no mesmo instante.
//
// Os demais ativos seguem com os dados estáticos do mock (caem nos fallbacks).
// O histórico curado (OS, documentos, OS-2025-118) permanece — muda apenas o
// ESTADO ATUAL do estrela (leitura, status, risco, alerta), que passa a ser vivo.

import { createContext, useContext } from "react";
import { useLiveTelemetry } from "./useLiveTelemetry.js";
import {
  HEARTBEAT,
  assetStatus,
  latestReading,
  assetRisk,
  componentsForAsset,
  alerts,
  alertsForTag,
} from "./data/mock.js";

const STAR = HEARTBEAT.tag;
const LiveTwinCtx = createContext(null);

// Risco efetivo derivado do estado ao vivo do motor-estrela.
function deriveRisk(status, scenario) {
  if (status === "critico")
    return { level: "Alto", score: 84, confidence: scenario?.confidence ?? 88, windowHours: 24 };
  if (status === "alerta")
    return { level: "Médio", score: 58, confidence: scenario?.confidence ?? 80, windowHours: 72 };
  return { level: "Baixo", score: 12, confidence: 95, windowHours: null };
}

export function LiveTwinProvider({ children }) {
  const live = useLiveTelemetry(true);

  const starStatus = live.status;
  const starScenario = starStatus !== "normal" ? live.scenario : null;
  const starRisk = deriveRisk(starStatus, starScenario);

  // Leitura ao vivo no MESMO formato das leituras estáticas (com ts/label).
  const starReading = live.last
    ? {
        asset_tag: STAR,
        ts: new Date(live.last.ts).toISOString(),
        label: live.last.label,
        temperature: live.last.temperature,
        vibration: live.last.vibration,
        current: live.last.current,
        rotation: live.last.rotation,
      }
    : latestReading(STAR);

  // Componentes do estrela: só o componente culpado do cenário fica fora do
  // normal (com as evidências do cenário); os demais ficam normais.
  const starComponents = componentsForAsset(STAR).map((c) =>
    starScenario && c.tag === starScenario.component
      ? {
          ...c,
          status: starStatus,
          evidence: starScenario.evidence,
          risk: { level: starRisk.level, score: starRisk.score },
        }
      : { ...c, status: "normal", risk: { level: "Baixo", score: 12 } }
  );

  // Alerta ao vivo do estrela — null quando o motor está normal (estável).
  const starAlert = starScenario
    ? {
        id: "ALR-LIVE-042",
        tag: STAR,
        severity: starStatus, // "alerta" | "critico"
        title: starScenario.name,
        message: starScenario.diagnosis,
        confidence: starScenario.confidence,
        origin: starScenario.sensor,
        bases: starScenario.bases,
        ts: starReading.ts,
        status: starStatus === "critico" ? "Aberto" : "Em análise",
        live: true,
      }
    : null;

  const isStar = (tag) => tag === STAR;

  const value = {
    live,
    STAR,
    starReading,
    starStatus,
    starScenario,
    starRisk,
    starComponents,
    starAlert,
    isStar,
    statusOf: (tag) => (isStar(tag) ? starStatus : assetStatus(tag)),
    readingOf: (tag) => (isStar(tag) ? starReading : latestReading(tag)),
    riskOf: (tag) => (isStar(tag) ? starRisk : assetRisk(tag)),
    scenarioOf: (tag) => (isStar(tag) ? starScenario : null),
    componentsOf: (tag) => (isStar(tag) ? starComponents : componentsForAsset(tag)),
    alertOf: (tag) => (isStar(tag) ? starAlert : alertsForTag(tag)[0] || null),
    // Lista de alertas com o estrela refletindo o estado ao vivo (some quando normal).
    alertsList: () => {
      const others = alerts.filter((a) => a.tag !== STAR);
      return starAlert ? [starAlert, ...others] : others;
    },
  };

  return <LiveTwinCtx.Provider value={value}>{children}</LiveTwinCtx.Provider>;
}

export function useLiveTwin() {
  return useContext(LiveTwinCtx);
}
