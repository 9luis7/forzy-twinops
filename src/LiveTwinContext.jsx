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

import React, { createContext, useContext, useEffect, useState } from "react";
import { useLiveTelemetry } from "./useLiveTelemetry.js";
import { buildReplaySnapshot } from "./dataSources/ReplayTwinDataSource.js";
import { createGatewayTwinDataSource } from "./dataSources/GatewayTwinDataSource.js";
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
const configuredGateway =
  import.meta.env.VITE_TWINOPS_DATA_MODE === "live"
    ? createGatewayTwinDataSource({
        baseUrl: import.meta.env.VITE_TWINOPS_API_BASE_URL || "",
      })
    : null;

// Risco efetivo derivado do estado ao vivo do motor-estrela.
function deriveRisk(status, scenario) {
  if (status === "critico")
    return { level: "Alto", score: 84, confidence: scenario?.confidence ?? 88, windowHours: 24 };
  if (status === "alerta")
    return { level: "Médio", score: 58, confidence: scenario?.confidence ?? 80, windowHours: 72 };
  return { level: "Baixo", score: 12, confidence: 95, windowHours: null };
}

function canonicalProjection(snapshot) {
  if (!snapshot) return null;
  const channels = snapshot.channels.filter((channel) => channel.receivedAt);
  const primary = channels.find((channel) => channel.sensorId === "s1") || channels[0];
  const score = snapshot.assessment
    ? Math.round(
        Math.max(
          snapshot.assessment.assessment.anomalyScore,
          snapshot.assessment.assessment.deteriorationScore
        )
      )
    : 0;
  const status = {
    alert: "critico",
    watch: "alerta",
    normal: "normal",
    insufficient_data: "desconhecido",
    unknown: "desconhecido",
  }[snapshot.status] || "desconhecido";
  const reading = primary
    ? {
        asset_tag: snapshot.assetTag,
        ts: primary.observedAt || primary.receivedAt,
        label: new Date(primary.observedAt || primary.receivedAt).toLocaleTimeString("pt-BR"),
        temperature: primary.measurements.temperature?.value ?? null,
        vibration: primary.measurements.vibrationVelocityRms?.value ?? null,
        current: null,
        rotation: null,
        canonical: true,
      }
    : null;
  const assessmentSufficient = ["normal", "watch", "alert"].includes(snapshot.status);
  const risk = {
    level: !assessmentSufficient
      ? "Indeterminado"
      : snapshot.status === "alert"
      ? "Alto"
      : snapshot.status === "watch"
      ? "Médio"
      : "Baixo",
    score: assessmentSufficient ? score : null,
    confidence: null,
    windowHours: null,
  };
  const assessment = snapshot.assessment;
  const alert = assessment && ["watch", "alert"].includes(assessment.assessment.status)
    ? {
        id: assessment.assessmentId,
        tag: snapshot.assetTag,
        severity: assessment.assessment.status === "alert" ? "critico" : "alerta",
        title: "Desvio relativo ao baseline histórico",
        message: `Score relativo ${score}/100; requer validação humana.`,
        confidence: null,
        origin: assessment.sensorId,
        bases: [`${assessment.model.name} ${assessment.model.version}`],
        ts: assessment.window.end,
        status: "Em análise",
        live: true,
      }
    : null;
  return { status, reading, risk, alert };
}

export function LiveTwinProvider({ children, dataSource = configuredGateway }) {
  const live = useLiveTelemetry(true);
  const [gatewayState, setGatewayState] = useState({ snapshot: null, error: null });

  useEffect(() => {
    if (!dataSource) {
      setGatewayState({ snapshot: null, error: null });
      return undefined;
    }
    return dataSource.subscribe(STAR, (error, snapshot) => {
      setGatewayState({ snapshot: snapshot ?? null, error: error ?? null });
    });
  }, [dataSource]);

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
  const replaySnapshot = buildReplaySnapshot({
    assetTag: STAR,
    live,
    reading: starReading,
    status: starStatus,
    scenario: starScenario,
    risk: starRisk,
  });
  const snapshot = gatewayState.snapshot ?? replaySnapshot;
  const gatewayProjection = canonicalProjection(gatewayState.snapshot);

  const value = {
    snapshot,
    dataMode: gatewayState.snapshot ? "live" : "replay",
    dataError: gatewayState.error,
    live,
    STAR,
    starReading,
    starStatus,
    starScenario,
    starRisk,
    starComponents,
    starAlert,
    isStar,
    statusOf: (tag) =>
      isStar(tag) ? (gatewayProjection ? gatewayProjection.status : starStatus) : assetStatus(tag),
    readingOf: (tag) =>
      isStar(tag) ? (gatewayProjection ? gatewayProjection.reading : starReading) : latestReading(tag),
    riskOf: (tag) =>
      isStar(tag) ? (gatewayProjection ? gatewayProjection.risk : starRisk) : assetRisk(tag),
    scenarioOf: (tag) =>
      isStar(tag) && !gatewayProjection ? starScenario : null,
    componentsOf: (tag) =>
      isStar(tag)
        ? gatewayProjection
          ? []
          : starComponents
        : componentsForAsset(tag),
    alertOf: (tag) =>
      isStar(tag)
        ? gatewayProjection?.alert ?? (gatewayProjection ? null : starAlert)
        : alertsForTag(tag)[0] || null,
    // Lista de alertas com o estrela refletindo o estado ao vivo (some quando normal).
    alertsList: () => {
      const others = alerts.filter((a) => a.tag !== STAR);
      const effectiveAlert = gatewayProjection?.alert ?? (gatewayProjection ? null : starAlert);
      return effectiveAlert ? [effectiveAlert, ...others] : others;
    },
  };

  return <LiveTwinCtx.Provider value={value}>{children}</LiveTwinCtx.Provider>;
}

export function useLiveTwin() {
  return useContext(LiveTwinCtx);
}
