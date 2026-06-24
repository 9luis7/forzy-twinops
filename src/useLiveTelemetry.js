// useLiveTelemetry.js — motor da telemetria ao vivo da estrela (MTR-BMB-042).
//
// Diferente do histórico (24h pré-gerado), aqui o tempo anda: 1 ponto/seg, janela
// deslizante, e o LOOP DE CENÁRIOS roda sozinho — estável → falha → detecção →
// normalização → próximo cenário. O estado vive AQUI (não dentro do gráfico) para
// que o painel inteiro (gauges, gêmeo digital, banner, diagnóstico) consuma a mesma
// leitura e reaja em sincronia. Os valores são determinísticos por tick
// (liveScenarioPoint); só o timestamp exibido vem do relógio.

import { useEffect, useRef, useState } from "react";
import {
  HEARTBEAT,
  LIVE_CYCLE_LEN,
  liveScenarioPoint,
  liveCycleState,
  readingStatus,
} from "./data/mock.js";

const hhmmss = (ms) =>
  new Date(ms).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

// `enabled` liga o motor só na estrela; nos demais ativos o hook fica inerte.
export function useLiveTelemetry(enabled = true) {
  const { windowPoints: WIN, seedPoints: SEED } = HEARTBEAT;

  // Âncora de relógio só para os rótulos (os valores não dependem dela).
  const baseRef = useRef(null);
  if (baseRef.current == null) baseRef.current = Date.now() - SEED * 1000;

  // Tick global do loop — começa após os pontos de seed.
  const tickRef = useRef(SEED);

  const mk = (i) => {
    const p = liveScenarioPoint(i);
    const ts = baseRef.current + i * 1000;
    return { ...p, ts, label: hhmmss(ts) };
  };

  const seedWindow = (startTick = 0) =>
    Array.from({ length: SEED }, (_, k) => mk(startTick + k));

  const [points, setPoints] = useState(() => seedWindow(0));
  const [running, setRunning] = useState(enabled);

  useEffect(() => {
    if (!enabled || !running) return;
    const id = setInterval(() => {
      const i = tickRef.current;
      tickRef.current = i + 1;
      setPoints((prev) => {
        const next = [...prev, mk(i)];
        return next.length > WIN ? next.slice(next.length - WIN) : next;
      });
    }, 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, running]);

  const reset = () => {
    setRunning(false);
    tickRef.current = SEED;
    baseRef.current = Date.now() - SEED * 1000;
    setPoints(seedWindow(0));
  };

  // Pula para o início (fase estável) do próximo cenário do loop.
  const nextScenario = () => {
    const i = tickRef.current;
    const nextStart = (Math.floor(i / LIVE_CYCLE_LEN) + 1) * LIVE_CYCLE_LEN;
    baseRef.current = Date.now() - SEED * 1000;
    setPoints(seedWindow(nextStart));
    tickRef.current = nextStart + SEED;
    setRunning(true);
  };

  const last = points[points.length - 1] || null;
  const state = liveCycleState(last ? last.t : SEED);
  // Status pelos VALORES (espelha os gauges), não pelo envelope — coerência total.
  const status = readingStatus(last);

  return {
    points,
    running,
    last,
    scenario: state.scenario,
    phase: state.phase,
    intensity: state.intensity,
    status,
    start: () => setRunning(true),
    pause: () => setRunning(false),
    reset,
    nextScenario,
  };
}
