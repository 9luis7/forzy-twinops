import React, { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const timeFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

function trendSeries(history) {
  const series = { s1: [], s2: [] };
  history.forEach((frame, index) => {
    if (!Object.hasOwn(series, frame.sensorId)) return;
    const timestamp = frame.observedAt ?? frame.receivedAt;
    if (!timestamp) return;
    series[frame.sensorId].push({
      id: `${frame.frameId}-${index}`,
      timestamp,
      value: frame.measurements.vibrationVelocityRms?.value ?? null,
    });
  });
  series.s1.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  series.s2.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  return series;
}

function SensorTrendSeries({ sensorId, points, stroke }) {
  return (
    <article className="trend-series" data-testid={`trend-series-${sensorId}`}>
      <h3>{sensorId.toUpperCase()}</h3>
      {points.length === 0 ? (
        <p className="empty-state">Sem histórico para este canal.</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={210}>
            <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(value) => timeFormatter.format(new Date(value))}
                minTickGap={28}
              />
              <YAxis width={48} />
              <Tooltip
                labelFormatter={(value) => timeFormatter.format(new Date(value))}
                formatter={(value) => [value ?? "Indisponível", sensorId.toUpperCase()]}
              />
              <Line
                type="linear"
                dataKey="value"
                stroke={stroke}
                connectNulls={false}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
          <ol className="visually-hidden" aria-label={`Pontos da série ${sensorId.toUpperCase()}`}>
            {points.map((point) => (
              <li
                data-value={point.value === null ? "unavailable" : String(point.value)}
                key={point.id}
              >
                {point.timestamp}: {point.value === null ? "Indisponível" : point.value}
              </li>
            ))}
          </ol>
        </>
      )}
    </article>
  );
}

export default function TelemetryTrend({ history }) {
  const series = useMemo(() => trendSeries(history), [history]);
  const hasHistory = series.s1.length > 0 || series.s2.length > 0;

  return (
    <section className="panel trend-panel" data-testid="telemetry-trend">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Histórico coletado pelo TwinOps</p>
          <h2>Tendência operacional real</h2>
        </div>
        <p className="trend-unit">Velocidade RMS (mm/s)</p>
      </div>

      {!hasHistory ? (
        <p className="empty-state">Ainda não há histórico operacional coletado.</p>
      ) : (
        <div className="trend-series-grid" aria-label="Gráficos independentes da tendência de S1 e S2">
          <SensorTrendSeries sensorId="s1" points={series.s1} stroke="#2dd4bf" />
          <SensorTrendSeries sensorId="s2" points={series.s2} stroke="#60a5fa" />
        </div>
      )}
    </section>
  );
}
