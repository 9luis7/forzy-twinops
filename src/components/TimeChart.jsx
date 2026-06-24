// TimeChart.jsx — série temporal das leituras (recharts). A métrica é selecionável.
// Dois modos:
//   • histórico (padrão): 24h pré-geradas do mock; a rampa de degradação aparece.
//   • ao vivo (`live`): heartbeat determinístico, 1 ponto/seg, janela deslizante,
//     com Start/Pause/Reset/Trigger Incident e badge "● Ao vivo".

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { readings, HEARTBEAT, heartbeatPoint } from "../data/mock.js";

// Métricas disponíveis + faixas de alerta/crítico (espelham o mock).
const METRICS = {
  temperature: { label: "Temperatura", unit: "°C", color: "var(--laranja)", warn: 70, crit: 90 },
  vibration: { label: "Vibração", unit: "m/s²", color: "var(--roxo-claro)", warn: 4.5, crit: 7.5 },
  current: { label: "Corrente", unit: "A", color: "var(--ok)" },
  rotation: { label: "Rotação", unit: "RPM", color: "var(--alerta)" },
};

const ORDER = ["temperature", "vibration", "current", "rotation"];

const hhmm = (iso) =>
  new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const hhmmss = (ms) =>
  new Date(ms).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

// ---------------------------------------------------------------- heartbeat hook
// Mantém a janela deslizante de pontos ao vivo. Os valores vêm de heartbeatPoint
// (determinístico por índice de tick); só o timestamp exibido é de relógio.
function useHeartbeat() {
  const { windowPoints: WIN, seedPoints: SEED } = HEARTBEAT;
  const baseRef = useRef(null);
  if (baseRef.current == null) baseRef.current = Date.now() - SEED * 1000;

  const tickRef = useRef(SEED);
  const incidentRef = useRef(null);

  const mk = (i) => {
    const p = heartbeatPoint(i, { incidentTick: incidentRef.current });
    const ts = baseRef.current + i * 1000;
    return { ...p, ts, label: hhmmss(ts) };
  };

  const seed = () => Array.from({ length: SEED }, (_, i) => mk(i));

  const [points, setPoints] = useState(seed);
  const [running, setRunning] = useState(false);
  const [incident, setIncident] = useState(false);

  useEffect(() => {
    if (!running) return;
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
  }, [running]);

  const reset = () => {
    setRunning(false);
    tickRef.current = SEED;
    incidentRef.current = null;
    baseRef.current = Date.now() - SEED * 1000;
    setIncident(false);
    setPoints(seed());
  };

  const trigger = () => {
    incidentRef.current = tickRef.current; // degrada a partir de agora
    setIncident(true);
    setRunning(true);
  };

  return {
    points,
    running,
    incident,
    last: points[points.length - 1] || null,
    start: () => setRunning(true),
    pause: () => setRunning(false),
    reset,
    trigger,
  };
}

function LiveControls({ hb }) {
  const btn = {
    background: "var(--surface-2)",
    border: "1px solid var(--borda)",
    borderRadius: 8,
    color: "var(--texto)",
    cursor: "pointer",
    padding: "5px 11px",
    fontSize: 12.5,
  };
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {hb.running ? (
        <button style={btn} onClick={hb.pause}>⏸ Pausar</button>
      ) : (
        <button style={{ ...btn, borderColor: "var(--roxo)" }} onClick={hb.start}>▶ Iniciar</button>
      )}
      <button style={btn} onClick={hb.reset}>↺ Reset</button>
      <button
        style={{ ...btn, borderColor: hb.incident ? "var(--critico)" : "var(--borda)", color: hb.incident ? "var(--critico)" : "var(--texto)" }}
        onClick={hb.trigger}
        title="Injeta um degrau de degradação na telemetria"
      >
        ⚡ Trigger Incident
      </button>
    </div>
  );
}

export default function TimeChart({ tag, live = false }) {
  const [metric, setMetric] = useState("temperature");
  const hb = useHeartbeat();

  const series = tag ? readings[tag] : null;

  // Histórico: pré-formata o eixo X uma vez por TAG.
  const histData = useMemo(
    () => (series ? series.map((r) => ({ ...r, label: hhmm(r.ts) })) : []),
    [series]
  );

  const data = live ? hb.points : histData;

  const wrap = {
    background: "var(--surface)",
    border: "1px solid var(--borda)",
    borderRadius: 12,
    padding: 16,
    marginTop: 16,
  };

  if (!live && (!series || series.length === 0)) {
    return (
      <section style={wrap}>
        <h3 style={{ marginTop: 0 }}>Gráfico temporal</h3>
        <p style={{ color: "var(--texto-fraco)", fontSize: 13 }}>Sem série para exibir.</p>
      </section>
    );
  }

  const m = METRICS[metric];

  return (
    <section style={wrap}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: 10 }}>
          Gráfico temporal{" "}
          <span style={{ color: "var(--texto-fraco)", fontWeight: 400, fontSize: 13 }}>
            · {live ? "telemetria ao vivo" : "últimas 24h"}
          </span>
          {live && (
            <span className={`live-badge ${hb.running ? "on" : "off"}`}>
              <span className="live-dot" /> {hb.running ? "Ao vivo" : "Pausado"}
            </span>
          )}
        </h3>

        {/* Seletor de métrica */}
        <div style={{ display: "flex", gap: 6 }}>
          {ORDER.map((key) => {
            const active = key === metric;
            return (
              <button
                key={key}
                onClick={() => setMetric(key)}
                style={{
                  background: active ? "var(--surface-2)" : "transparent",
                  border: active ? "1px solid var(--roxo)" : "1px solid var(--borda)",
                  borderRadius: 8,
                  color: active ? "var(--texto)" : "var(--texto-fraco)",
                  cursor: "pointer",
                  padding: "4px 10px",
                  fontSize: 12,
                }}
              >
                {METRICS[key].label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Barra de controle do heartbeat (só ao vivo) */}
      {live && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 10,
            marginTop: 12,
          }}
        >
          <LiveControls hb={hb} />
          <span className="muted small" style={{ fontFamily: "ui-monospace, monospace" }}>
            último heartbeat: {hb.last ? hb.last.label : "—"}
            {hb.last ? ` · ${hb.last[metric]} ${m.unit}` : ""}
          </span>
        </div>
      )}

      <div style={{ width: "100%", height: 280, marginTop: 12 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
            <CartesianGrid stroke="var(--borda)" strokeDasharray="3 3" />
            <XAxis
              dataKey="label"
              tick={{ fill: "var(--texto-fraco)", fontSize: 11 }}
              minTickGap={live ? 28 : 48}
              stroke="var(--borda)"
            />
            <YAxis
              tick={{ fill: "var(--texto-fraco)", fontSize: 11 }}
              stroke="var(--borda)"
              domain={["auto", "auto"]}
              width={48}
            />
            <Tooltip
              contentStyle={{
                background: "var(--surface-2)",
                border: "1px solid var(--borda)",
                borderRadius: 8,
                color: "var(--texto)",
              }}
              labelStyle={{ color: "var(--texto-fraco)" }}
              formatter={(value) => [`${value} ${m.unit}`, m.label]}
            />

            {/* Linhas de referência (alerta/crítico) quando a métrica tem limiar */}
            {m.warn != null && (
              <ReferenceLine
                y={m.warn}
                stroke="var(--alerta)"
                strokeDasharray="4 4"
                label={{ value: "alerta", fill: "var(--alerta)", fontSize: 10, position: "insideTopLeft" }}
              />
            )}
            {m.crit != null && (
              <ReferenceLine
                y={m.crit}
                stroke="var(--critico)"
                strokeDasharray="4 4"
                label={{ value: "crítico", fill: "var(--critico)", fontSize: 10, position: "insideTopLeft" }}
              />
            )}

            <Line
              type="monotone"
              dataKey={metric}
              stroke={m.color}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              name={m.label}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
