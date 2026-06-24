// TimeChart.jsx — série temporal das leituras (recharts). A métrica é selecionável;
// no MOT-003 a rampa de degradação (temperatura/vibração subindo) fica visível.

import { useMemo, useState } from "react";
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
import { readings } from "../data/mock.js";

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

export default function TimeChart({ tag }) {
  const [metric, setMetric] = useState("temperature");

  const series = tag ? readings[tag] : null;

  // Pré-formata o eixo X uma vez por TAG.
  const data = useMemo(
    () => (series ? series.map((r) => ({ ...r, label: hhmm(r.ts) })) : []),
    [series]
  );

  const wrap = {
    background: "var(--surface)",
    border: "1px solid var(--borda)",
    borderRadius: 12,
    padding: 16,
    marginTop: 16,
  };

  if (!series || series.length === 0) {
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
        <h3 style={{ margin: 0 }}>
          Gráfico temporal{" "}
          <span style={{ color: "var(--texto-fraco)", fontWeight: 400, fontSize: 13 }}>
            · últimas 24h
          </span>
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

      <div style={{ width: "100%", height: 280, marginTop: 12 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
            <CartesianGrid stroke="var(--borda)" strokeDasharray="3 3" />
            <XAxis
              dataKey="label"
              tick={{ fill: "var(--texto-fraco)", fontSize: 11 }}
              minTickGap={48}
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
