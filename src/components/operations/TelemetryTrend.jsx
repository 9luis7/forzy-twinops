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

function trendPoints(history) {
  const byTimestamp = new Map();
  for (const frame of history) {
    const timestamp = frame.observedAt ?? frame.receivedAt;
    if (!timestamp) continue;
    const point = byTimestamp.get(timestamp) ?? { timestamp };
    point[frame.sensorId] = frame.measurements.vibrationVelocityRms?.value ?? null;
    byTimestamp.set(timestamp, point);
  }
  return [...byTimestamp.values()].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
}

export default function TelemetryTrend({ history }) {
  const points = useMemo(() => trendPoints(history), [history]);

  return (
    <section className="panel trend-panel" data-testid="telemetry-trend">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Histórico coletado pelo TwinOps</p>
          <h2>Tendência operacional real</h2>
        </div>
        <p className="trend-unit">Velocidade RMS (mm/s)</p>
      </div>

      {points.length === 0 ? (
        <p className="empty-state">Ainda não há histórico operacional coletado.</p>
      ) : (
        <>
          <div className="trend-legend" aria-label="Canais da tendência">
            <span className="trend-legend__s1">S1</span>
            <span className="trend-legend__s2">S2</span>
          </div>
          <div className="trend-chart" aria-label="Gráfico da tendência de S1 e S2">
            <ResponsiveContainer width="100%" height={260}>
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
                  formatter={(value, name) => [value ?? "Indisponível", name.toUpperCase()]}
                />
                <Line type="linear" dataKey="s1" stroke="#2dd4bf" connectNulls={false} dot={false} />
                <Line type="linear" dataKey="s2" stroke="#60a5fa" connectNulls={false} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <span hidden data-connect-nulls="false" data-sensor="s1" />
          <span hidden data-connect-nulls="false" data-sensor="s2" />
        </>
      )}
    </section>
  );
}
