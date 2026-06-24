// TimeChart.jsx — série temporal das leituras (recharts). A métrica é selecionável.
// Dois modos:
//   • histórico (padrão): 24h pré-geradas do mock; a rampa de degradação aparece.
//   • ao vivo (`live`): heartbeat determinístico, 1 ponto/seg, janela deslizante,
//     com Start/Pause/Reset/Trigger Incident e badge "● Ao vivo".
//
// Visual: painel de instrumento SCADA — área com gradiente sob a linha, grade/eixos
// com os tokens, LED pulsante "Ao vivo", botões de métrica estilo instrumento e
// barra de controle do heartbeat enxuta. O comportamento e a matemática NÃO mudam.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { readings, HEARTBEAT, heartbeatPoint } from "../data/mock.js";

// Métricas disponíveis + faixas de alerta/crítico (espelham o mock).
// `grad` é o id do gradiente SVG (definido em <defs>) usado na área sob a linha.
const METRICS = {
  temperature: {
    label: "Temperatura",
    unit: "°C",
    color: "var(--laranja)",
    rgb: "255,122,24",
    warn: 70,
    crit: 90,
  },
  vibration: {
    label: "Vibração",
    unit: "m/s²",
    color: "var(--roxo-claro)",
    rgb: "167,139,250",
    warn: 4.5,
    crit: 7.5,
  },
  current: { label: "Corrente", unit: "A", color: "var(--ok)", rgb: "52,211,153" },
  rotation: { label: "Rotação", unit: "RPM", color: "var(--cyan)", rgb: "34,211,238" },
};

const ORDER = ["temperature", "vibration", "current", "rotation"];

const hhmm = (iso) =>
  new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const hhmmss = (ms) =>
  new Date(ms).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

// Classe de cor do readout em função do valor x limiares da métrica.
function readoutClass(metric, value) {
  const m = METRICS[metric];
  if (value == null || m.warn == null) return "";
  if (m.crit != null && value >= m.crit) return "crit";
  if (value >= m.warn) return "warn";
  return "ok";
}

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

// Barra de controle do heartbeat (botões estilo instrumento via classe .btn).
function LiveControls({ hb }) {
  return (
    <div className="tc-controls">
      {hb.running ? (
        <button className="btn" onClick={hb.pause}>
          <span className="tc-ico" aria-hidden>⏸</span> Pausar
        </button>
      ) : (
        <button className="btn btn-primary" onClick={hb.start}>
          <span className="tc-ico" aria-hidden>▶</span> Iniciar
        </button>
      )}
      <button className="btn" onClick={hb.reset}>
        <span className="tc-ico" aria-hidden>↺</span> Reset
      </button>
      <button
        className={`btn tc-trigger${hb.incident ? " on" : ""}`}
        onClick={hb.trigger}
        title="Injeta um degrau de degradação na telemetria"
      >
        <span className="tc-ico" aria-hidden>⚡</span> Disparar incidente
      </button>
    </div>
  );
}

// Tooltip customizado — painel de vidro com leitura tabular.
function ChartTooltip({ active, payload, label, metric }) {
  if (!active || !payload || !payload.length) return null;
  const m = METRICS[metric];
  const v = payload[0].value;
  return (
    <div className="tc-tip">
      <div className="tc-tip-time">{label}</div>
      <div className="tc-tip-row">
        <span className="led" style={{ background: m.color, boxShadow: `0 0 8px 1px rgba(${m.rgb},.65)` }} />
        <span className="tc-tip-label">{m.label}</span>
        <span className={`readout ${readoutClass(metric, v)}`} style={{ fontSize: 14 }}>
          {v} <span className="tc-tip-unit">{m.unit}</span>
        </span>
      </div>
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
  const m = METRICS[metric];

  if (!live && (!series || series.length === 0)) {
    return (
      <section className="card tc-card" data-tour="telemetry">
        <Styles />
        <h3 className="tc-title">Gráfico temporal</h3>
        <p className="muted small">Sem série para exibir.</p>
      </section>
    );
  }

  const gradId = `tc-grad-${metric}`;

  return (
    <section className="card tc-card" data-tour="telemetry">
      <Styles />

      {/* Cabeçalho: título + subtítulo + LED ao vivo + seletor de métrica */}
      <div className="tc-head">
        <h3 className="tc-title">
          Gráfico temporal
          <span className="tc-sub">· {live ? "telemetria ao vivo" : "últimas 24h"}</span>
          {live && (
            <span className={`live-badge ${hb.running ? "on" : "off"}`}>
              <span className="live-dot" /> {hb.running ? "Ao vivo" : "Pausado"}
            </span>
          )}
        </h3>

        {/* Seletor de métrica — botões estilo instrumento */}
        <div className="tc-metrics" role="tablist" aria-label="Métrica">
          {ORDER.map((key) => {
            const active = key === metric;
            const mk = METRICS[key];
            return (
              <button
                key={key}
                role="tab"
                aria-selected={active}
                onClick={() => setMetric(key)}
                className={`tc-metric${active ? " active" : ""}`}
                style={active ? { "--mc": mk.color, "--mrgb": mk.rgb } : undefined}
              >
                <span className="tc-metric-dot" style={{ background: mk.color }} />
                {mk.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Barra de controle do heartbeat (só ao vivo) */}
      {live && (
        <div className="tc-livebar">
          <LiveControls hb={hb} />
          <div className="tc-heartbeat">
            <span className="muted small">último heartbeat</span>
            <span className="tc-hb-time">{hb.last ? hb.last.label : "—"}</span>
            {hb.last && (
              <span className={`readout ${readoutClass(metric, hb.last[metric])} tc-hb-val`}>
                {hb.last[metric]} <span className="tc-hb-unit">{m.unit}</span>
              </span>
            )}
          </div>
        </div>
      )}

      {/* Gráfico */}
      <div className="tc-plot scada-grid">
        <ResponsiveContainer width="100%" height={live ? 300 : 290}>
          <AreaChart data={data} margin={{ top: 10, right: 18, bottom: 4, left: -6 }}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={`rgba(${m.rgb},.32)`} />
                <stop offset="55%" stopColor={`rgba(${m.rgb},.10)`} />
                <stop offset="100%" stopColor={`rgba(${m.rgb},0)`} />
              </linearGradient>
            </defs>

            <CartesianGrid stroke="var(--stroke)" strokeDasharray="2 5" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: "var(--texto-fraco)", fontSize: 11 }}
              minTickGap={live ? 28 : 48}
              stroke="var(--stroke)"
              tickLine={false}
              axisLine={{ stroke: "var(--stroke)" }}
            />
            <YAxis
              tick={{ fill: "var(--texto-fraco)", fontSize: 11 }}
              stroke="var(--stroke)"
              tickLine={false}
              axisLine={false}
              domain={["auto", "auto"]}
              width={48}
            />
            <Tooltip
              cursor={{ stroke: m.color, strokeWidth: 1, strokeDasharray: "3 3", strokeOpacity: 0.5 }}
              content={<ChartTooltip metric={metric} />}
            />

            {/* Linhas de referência (alerta/crítico) quando a métrica tem limiar */}
            {m.warn != null && (
              <ReferenceLine
                y={m.warn}
                stroke="var(--alerta)"
                strokeOpacity={0.85}
                strokeDasharray="5 4"
                label={{
                  value: "alerta",
                  fill: "var(--alerta)",
                  fontSize: 10,
                  position: "insideTopLeft",
                }}
              />
            )}
            {m.crit != null && (
              <ReferenceLine
                y={m.crit}
                stroke="var(--critico)"
                strokeOpacity={0.9}
                strokeDasharray="5 4"
                label={{
                  value: "crítico",
                  fill: "var(--critico)",
                  fontSize: 10,
                  position: "insideTopLeft",
                }}
              />
            )}

            <Area
              type="monotone"
              dataKey={metric}
              stroke={m.color}
              strokeWidth={2.2}
              fill={`url(#${gradId})`}
              fillOpacity={1}
              dot={false}
              activeDot={{
                r: 3.5,
                fill: m.color,
                stroke: "var(--bg)",
                strokeWidth: 1.5,
              }}
              isAnimationActive={false}
              name={m.label}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

// ----------------------------------------------------------------- estilos locais
// Mantidos dentro do componente (não toco em styles.css). Usam os tokens globais.
function Styles() {
  return (
    <style>{`
      .tc-card { margin-top: 16px; padding: 16px; }
      .tc-head {
        display: flex; justify-content: space-between; align-items: center;
        flex-wrap: wrap; gap: 10px;
      }
      .tc-title {
        margin: 0; display: flex; align-items: center; gap: 10px;
        font-size: 15px; font-weight: 700; color: var(--texto);
      }
      .tc-sub { color: var(--texto-fraco); font-weight: 400; font-size: 13px; }

      /* Seletor de métrica — “teclas” de instrumento */
      .tc-metrics {
        display: inline-flex; gap: 4px; padding: 4px;
        background: var(--panel); border: 1px solid var(--stroke);
        border-radius: 11px;
      }
      .tc-metric {
        display: inline-flex; align-items: center; gap: 7px;
        background: transparent; border: 1px solid transparent;
        border-radius: 8px; cursor: pointer;
        color: var(--texto-fraco); font-size: 12px; font-weight: 600;
        padding: 5px 11px; transition: color .12s, background .12s, border-color .12s;
      }
      .tc-metric:hover { color: var(--texto); }
      .tc-metric.active {
        color: var(--texto);
        background: linear-gradient(180deg, rgba(var(--mrgb), .16), rgba(var(--mrgb), .04));
        border-color: rgba(var(--mrgb), .55);
        box-shadow: 0 0 0 1px rgba(var(--mrgb), .14), 0 1px 8px rgba(var(--mrgb), .18);
      }
      .tc-metric-dot {
        width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
        opacity: .55;
      }
      .tc-metric.active .tc-metric-dot {
        opacity: 1; box-shadow: 0 0 7px 1px rgba(var(--mrgb), .7);
      }

      /* Barra ao vivo */
      .tc-livebar {
        display: flex; justify-content: space-between; align-items: center;
        flex-wrap: wrap; gap: 10px; margin-top: 12px;
        padding: 10px 12px;
        background: var(--panel); border: 1px solid var(--stroke);
        border-radius: 11px;
      }
      .tc-controls { display: flex; gap: 6px; flex-wrap: wrap; }
      .tc-ico { font-size: 11px; line-height: 1; }
      .tc-trigger.on {
        border-color: var(--critico); color: var(--critico);
        box-shadow: 0 0 0 1px rgba(251,106,106,.25), 0 0 12px rgba(251,106,106,.25);
      }
      .tc-heartbeat {
        display: inline-flex; align-items: baseline; gap: 8px;
        font-family: ui-monospace, "SFMono-Regular", Menlo, monospace;
      }
      .tc-hb-time { color: var(--texto-fraco); font-size: 12.5px; }
      .tc-hb-val { font-size: 15px; }
      .tc-hb-unit { font-size: 11px; opacity: .8; }

      /* Área do gráfico */
      .tc-plot {
        width: 100%; margin-top: 12px;
        border: 1px solid var(--stroke); border-radius: 12px;
        padding: 6px 4px 2px; overflow: hidden;
      }

      /* Tooltip */
      .tc-tip {
        background: var(--panel-2);
        border: 1px solid var(--stroke); border-radius: 10px;
        padding: 8px 11px; backdrop-filter: blur(8px);
        box-shadow: 0 8px 24px rgba(0,0,0,.45);
      }
      .tc-tip-time {
        color: var(--texto-fraco); font-size: 11px;
        font-family: ui-monospace, monospace; margin-bottom: 5px;
      }
      .tc-tip-row { display: flex; align-items: center; gap: 8px; }
      .tc-tip-label { color: var(--texto); font-size: 12px; font-weight: 600; }
      .tc-tip-unit { font-size: 11px; opacity: .8; }
    `}</style>
  );
}
