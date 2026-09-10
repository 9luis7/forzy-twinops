import React, { useMemo } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatClock } from "../lib/displayTime.js";
import "./trends.css";

export const METRICS = [
  { key: "vibrationVelocityRms", label: "Velocidade RMS", unit: "mm/s" },
  { key: "vibrationAcceleration", label: "Aceleração", unit: "g" },
  { key: "temperature", label: "Temperatura", unit: "°C" },
];
export const clockLabel = formatClock;

// Source order is intentional: repeated timestamps and readings remain visible.
export function buildTrendPoints(history, metric) {
  const rows = new Map();
  history.forEach((frame) => {
    if (!rows.has(frame.sourceRow)) rows.set(frame.sourceRow, { row: frame.sourceRow, time: frame.observedAt, s1: null, s2: null, gap: false, preloaded: frame.preloaded });
    const row = rows.get(frame.sourceRow);
    row[frame.sensorId] = frame.measurements[metric]?.value ?? null;
    row.gap ||= frame.gapBefore;
  });
  return [...rows.values()].flatMap((row) => row.gap ? [{ ...row, row: `gap-${row.row}`, s1: null, s2: null, break: true }, row] : [row]);
}

const CHANNELS = [
  { key: "s1", label: "S1 · Motor", color: "#60a5fa" },
  { key: "s2", label: "S2 · Bomba", color: "#2dd4bf" },
];
const numberLabel = (value) => value.toLocaleString("pt-BR", { maximumFractionDigits: 4 });

function VelocityTrend({ points, selected }) {
  // Both channels always define the scale, even when one is hidden. Keep zero
  // visible so a 0.01 mm/s change does not occupy the whole vertical axis.
  const values = points.flatMap((point) => [point.s1, point.s2]).filter(Number.isFinite);
  const maximum = Math.max(0, ...values);
  const magnitude = maximum > 0 ? 10 ** Math.floor(Math.log10(maximum)) : 1;
  const upperBound = maximum > 0 ? Number((Math.ceil(maximum * 1.15 / magnitude) * magnitude).toPrecision(12)) : 1;
  const domain = [Math.min(0, ...values), upperBound];

  return <article className="velocity-trend">
    <h3>Velocidade RMS <span className="muted small">mm/s</span></h3>
    <p className="small muted">Cada ponto é uma leitura · canais separados, mesma escala a partir de zero.</p>
    <div className="velocity-channel-grid">
      {CHANNELS.filter((channel) => selected === "all" || selected === channel.key).map((channel) => {
        const readings = points.map((point) => point[channel.key]).filter(Number.isFinite);
        return <section className="velocity-channel" key={channel.key} aria-label={`Velocidade RMS — ${channel.label}`}>
          <div className="velocity-channel-heading">
            <h4><span className="velocity-channel-dot" style={{ background: channel.color }} aria-hidden="true" />{channel.label}</h4>
            {readings.length > 0 && <span className="small muted">{numberLabel(Math.min(...readings))}–{numberLabel(Math.max(...readings))} mm/s</span>}
          </div>
          {!readings.length ? <p className="empty-state">Sem leituras de velocidade para este canal.</p> : <>
            <ResponsiveContainer width="100%" height={190}>
              <LineChart data={points} margin={{ top: 10, right: 10, left: 0, bottom: 0 }} accessibilityLayer>
                <CartesianGrid vertical={false} stroke="#26374b" strokeDasharray="3 3" />
                <XAxis dataKey="row" minTickGap={55} tick={{ fill: "#9baec4", fontSize: 10 }} tickFormatter={(row) => clockLabel(points.find((point) => point.row === row)?.time)} />
                <YAxis width={48} tickCount={6} tick={{ fill: "#9baec4", fontSize: 10 }} tickFormatter={numberLabel} domain={domain} />
                <Tooltip contentStyle={{ background: "#122238", borderColor: "#2a3c55", borderRadius: 10 }} labelFormatter={(row, payload) => `${clockLabel(payload?.[0]?.payload.time)} · São Paulo · linha ${row}`} formatter={(value) => [`${numberLabel(value)} mm/s`, channel.label]} />
                <Line dataKey={channel.key} stroke="none" dot={{ r: 2, fill: channel.color, strokeWidth: 0, fillOpacity: 0.85 }} activeDot={{ r: 5, fill: channel.color, stroke: "#e8eef7", strokeWidth: 1 }} connectNulls={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
            <p className="small muted">{readings.length} leituras na janela · sem suavização</p>
          </>}
        </section>;
      })}
    </div>
  </article>;
}

export default function DemoTrends({ context, selected, onSelect }) {
  const series = useMemo(() => METRICS.map((metric) => buildTrendPoints(context.history, metric.key)), [context.history]);
  return <section className="panel demo-trends" aria-labelledby="demo-trends-title" data-revision={context.revision}>
    <div className="panel-heading"><div><p className="eyebrow">Leituras históricas</p><h2 id="demo-trends-title">O sinal ao longo do tempo</h2></div>
      <label>Canal<select value={selected} onChange={(e) => onSelect(e.target.value)}><option value="all">S1 + S2</option><option value="s1">S1 · Motor</option><option value="s2">S2 · Bomba</option></select></label>
    </div>
    <p className="muted small">Ordem original das leituras · horário de São Paulo · interrupções indicam lacunas &gt;15 s · aceleração exibida, fora do score.</p>
    <div className="demo-chart-grid demo-chart-grid--velocity-focus">
      <VelocityTrend points={series[0]} selected={selected} />
      {METRICS.slice(1).map((metric, offset) => {
        const index = offset + 1;
        return <article key={metric.key}>
      <h3>{metric.label} <span className="muted small">{metric.unit}</span></h3>
      {!series[index].length ? <p className="empty-state">Aguardando leituras históricas.</p> : <>
        <ResponsiveContainer width="100%" height={190}><LineChart data={series[index]} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#26374b" strokeDasharray="3 3" />
          <XAxis dataKey="row" minTickGap={55} tick={{ fill: "#9baec4", fontSize: 10 }} tickFormatter={(row) => clockLabel(series[index].find((p) => p.row === row)?.time)} />
          <YAxis tick={{ fill: "#9baec4", fontSize: 10 }} domain={["auto", "auto"]} />
          <Tooltip contentStyle={{ background: "#122238", borderColor: "#2a3c55", borderRadius: 10 }} labelFormatter={(row, payload) => `${clockLabel(payload?.[0]?.payload.time)} · São Paulo · linha ${row}`} formatter={(value, name) => [value == null ? "Indisponível" : `${value} ${metric.unit}`, name.toUpperCase()]} />
          {selected !== "s2" && <Line dataKey="s1" stroke="#60a5fa" dot={false} connectNulls={false} isAnimationActive={false} strokeWidth={2} />}
          {selected !== "s1" && <Line dataKey="s2" stroke="#2dd4bf" dot={false} connectNulls={false} isAnimationActive={false} strokeWidth={2} />}
        </LineChart></ResponsiveContainer>
        <p className="small muted">{series[index].filter((p) => !p.break).length} pares na janela · S1 Motor azul / S2 Bomba verde</p>
      </>}
    </article>;
      })}</div>
    <details><summary>Detalhes dos gráficos</summary><p className="small muted">Revisão {context.revision} · Os gráficos usam o mesmo instante do equipamento 3D e dos cartões de sensores. A velocidade exibe pontos sem unir as leituras; os dois canais mantêm a mesma escala, inclusive ao filtrar. As leituras repetidas e as lacunas são preservadas.</p></details>
  </section>;
}
