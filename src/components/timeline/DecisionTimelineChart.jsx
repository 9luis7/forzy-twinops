import React, { useMemo, useState } from "react";

const CHART_WIDTH = 1040;
const SENSOR_CHART_HEIGHT = 310;
const SCORE_CHART_HEIGHT = 250;
const MARGIN = Object.freeze({ top: 18, right: 22, bottom: 34, left: 58 });
const SENSOR_COLORS = Object.freeze({ s1: "#5eead4", s2: "#fbbf24" });
const MINUTE = 60 * 1000;
const ZOOM_FACTORS = Object.freeze([1, 2, 4, 8, 16, 32, 64, 128, 256, 512]);
const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const splitScoreRuns = (points, scoreKey) => {
  const runs = [];
  let current = [];
  for (const point of points) {
    if (point[scoreKey] === null) {
      if (current.length > 0) runs.push(current);
      current = [];
      continue;
    }
    current.push({ ...point, timeMs: Date.parse(point.eventAt), value: point[scoreKey] });
  }
  if (current.length > 0) runs.push(current);
  return runs;
};

const fitDomain = (candidate, fullDomain) => {
  const fullSpan = Math.max(1, fullDomain[1] - fullDomain[0]);
  const requestedSpan = Math.min(fullSpan, Math.max(1, candidate[1] - candidate[0]));
  let start = candidate[0];
  let end = start + requestedSpan;
  if (start < fullDomain[0]) {
    start = fullDomain[0];
    end = start + requestedSpan;
  }
  if (end > fullDomain[1]) {
    end = fullDomain[1];
    start = end - requestedSpan;
  }
  return [start, end];
};

const denseDataDomain = (times, fullDomain) => {
  const sorted = [...new Set(times)]
    .filter((value) => Number.isFinite(value) && value >= fullDomain[0] && value <= fullDomain[1])
    .sort((left, right) => left - right);
  if (sorted.length < 3) return [...fullDomain];

  const targetCount = Math.max(2, Math.ceil(sorted.length * 0.8));
  let bestStart = sorted[0];
  let bestEnd = sorted[targetCount - 1];
  for (let startIndex = 1; startIndex + targetCount <= sorted.length; startIndex += 1) {
    const endIndex = startIndex + targetCount - 1;
    if (sorted[endIndex] - sorted[startIndex] < bestEnd - bestStart) {
      bestStart = sorted[startIndex];
      bestEnd = sorted[endIndex];
    }
  }

  const denseSpan = Math.max(2 * MINUTE, bestEnd - bestStart);
  const padding = Math.max(MINUTE, denseSpan * 0.12);
  const framed = fitDomain([bestStart - padding, bestEnd + padding], fullDomain);
  return framed[1] - framed[0] >= (fullDomain[1] - fullDomain[0]) * 0.85
    ? [...fullDomain]
    : framed;
};

const nearestZoomIndex = (factor) => ZOOM_FACTORS.reduce(
  (bestIndex, candidate, index) => (
    Math.abs(candidate - factor) < Math.abs(ZOOM_FACTORS[bestIndex] - factor)
      ? index
      : bestIndex
  ),
  0,
);

const scaleX = (value, domain) => {
  const span = Math.max(1, domain[1] - domain[0]);
  return MARGIN.left + ((value - domain[0]) / span) * (CHART_WIDTH - MARGIN.left - MARGIN.right);
};

const scaleY = (value, domain, height) => {
  const span = Math.max(Number.EPSILON, domain[1] - domain[0]);
  return MARGIN.top + ((domain[1] - value) / span) * (height - MARGIN.top - MARGIN.bottom);
};

const linePoints = (points, domain, valueDomain, height) => points
  .map((point) => `${scaleX(point.timeMs, domain)},${scaleY(point.value, valueDomain, height)}`)
  .join(" ");

function Grid({ domain, fractionDigits = 0, height, valueDomain }) {
  const xTicks = Array.from({ length: 6 }, (_, index) => (
    domain[0] + ((domain[1] - domain[0]) * index) / 5
  ));
  const yTicks = Array.from({ length: 5 }, (_, index) => (
    valueDomain[0] + ((valueDomain[1] - valueDomain[0]) * index) / 4
  ));
  return (
    <g className="decision-chart__grid" aria-hidden="true">
      {xTicks.map((tick, index) => {
        const x = scaleX(tick, domain);
        return (
          <g key={tick}>
            <line x1={x} x2={x} y1={MARGIN.top} y2={height - MARGIN.bottom} />
            <text
              textAnchor={index === 0 ? "start" : index === xTicks.length - 1 ? "end" : "middle"}
              x={x}
              y={height - 10}
            >
              {dateFormatter.format(new Date(tick))}
            </text>
          </g>
        );
      })}
      {yTicks.map((tick) => {
        const y = scaleY(tick, valueDomain, height);
        return (
          <g key={tick}>
            <line x1={MARGIN.left} x2={CHART_WIDTH - MARGIN.right} y1={y} y2={y} />
            <text textAnchor="end" x={MARGIN.left - 8} y={y + 4}>
              {Number(tick).toLocaleString("pt-BR", {
                minimumFractionDigits: fractionDigits,
                maximumFractionDigits: fractionDigits,
              })}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function GapAreas({ domain, gaps, height }) {
  return (
    <g aria-hidden="true" className="decision-chart__gaps">
      {gaps.map((gap) => {
        const start = Math.max(domain[0], gap.startMs);
        const end = Math.min(domain[1], gap.endMs);
        if (end <= start) return null;
        const x = scaleX(start, domain);
        return (
          <rect
            height={height - MARGIN.top - MARGIN.bottom}
            key={gap.gapId}
            width={Math.max(1, scaleX(end, domain) - x)}
            x={x}
            y={MARGIN.top}
          />
        );
      })}
    </g>
  );
}

function PointButton({ candidate, color, cx, cy, label, onActivate, selected, title }) {
  return (
    <circle
      aria-label={label}
      className="decision-chart__point"
      cx={cx}
      cy={cy}
      data-candidate={candidate ? "true" : "false"}
      data-selected={selected ? "true" : "false"}
      fill={candidate ? "#8b5cf6" : color}
      onClick={onActivate}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onActivate();
        }
      }}
      r={selected ? 5.5 : candidate ? 4.5 : 2.8}
      role="button"
      stroke="#07111f"
      strokeWidth="1.5"
      tabIndex="0"
    >
      <title>{title}</title>
    </circle>
  );
}

export default function DecisionTimelineChart({
  assessmentOverview,
  model,
  onSelectPoint,
  selectedPointId,
  selectedAt,
  visibleSensors,
}) {
  const fullDomain = model.domain ?? [0, 1];
  const domainKey = `${fullDomain[0]}:${fullDomain[1]}`;
  const visibleTimes = useMemo(() => model.series
    .filter((series) => visibleSensors.has(series.sensorId))
    .flatMap((series) => series.points.map((point) => point.timeMs)), [model.series, visibleSensors]);
  const autoDomain = useMemo(
    () => denseDataDomain(visibleTimes, fullDomain),
    [domainKey, visibleTimes],
  );
  const [viewport, setViewport] = useState(() => ({
    domain: null,
    key: null,
    mode: "auto",
  }));
  const viewportMode = viewport.key === domainKey ? viewport.mode : "auto";
  const domain = viewport.key === domainKey && viewport.domain !== null && viewport.mode !== "auto"
    ? viewport.domain
    : autoDomain;
  const fullSpan = Math.max(1, fullDomain[1] - fullDomain[0]);
  const visibleSpan = Math.max(1, domain[1] - domain[0]);
  const zoomFactor = fullSpan / visibleSpan;
  const zoomIndex = nearestZoomIndex(zoomFactor);
  const setManualDomain = (nextDomain, mode = "manual") => {
    setViewport({ domain: fitDomain(nextDomain, fullDomain), key: domainKey, mode });
  };
  const applyZoomIndex = (nextIndex) => {
    const boundedIndex = Math.max(0, Math.min(ZOOM_FACTORS.length - 1, nextIndex));
    const nextSpan = fullSpan / ZOOM_FACTORS[boundedIndex];
    const center = (domain[0] + domain[1]) / 2;
    setManualDomain([center - nextSpan / 2, center + nextSpan / 2]);
  };
  const pan = (direction) => {
    const shift = visibleSpan * 0.45 * direction;
    setManualDomain([domain[0] + shift, domain[1] + shift]);
  };
  const visibleSeries = useMemo(
    () => model.series
      .filter((series) => visibleSensors.has(series.sensorId))
      .map((series) => ({
        ...series,
        points: series.points.filter((point) => point.timeMs >= domain[0] && point.timeMs <= domain[1]),
      }))
      .filter((series) => series.points.length > 0),
    [domain, model.series, visibleSensors],
  );
  const sensorDomain = useMemo(() => {
    const values = visibleSeries.flatMap((series) => series.points.map((point) => point.value));
    if (values.length === 0) return [0, 1];
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const padding = Math.max((maximum - minimum) * 0.08, maximum * 0.02, 0.01);
    return [Math.max(0, minimum - padding), maximum + padding];
  }, [visibleSeries]);
  const candidatePointIds = useMemo(() => new Set(
    assessmentOverview?.series?.flatMap((series) => series.points)
      .filter((point) => point.candidateState === "candidate_not_ground_truth")
      .map((point) => point.anchorPointId) ?? [],
  ), [assessmentOverview]);
  const scoreSeries = useMemo(() => (
    assessmentOverview?.series?.filter((series) => visibleSensors.has(series.sensorId)) ?? []
  ), [assessmentOverview, visibleSensors]);
  const sensorPoints = useMemo(() => {
    const unique = new Map();
    visibleSeries.forEach((series) => {
      series.points.forEach((point) => {
        if (!unique.has(point.pointId)) unique.set(point.pointId, { ...point, sensorId: series.sensorId });
      });
    });
    return [...unique.values()];
  }, [visibleSeries]);
  const scoreRuns = useMemo(() => scoreSeries.flatMap((series) => (
    ["anomalyScore", "deteriorationScore"].flatMap((scoreKey) => (
      splitScoreRuns(
        series.points.filter((point) => {
          const timeMs = Date.parse(point.eventAt);
          return timeMs >= domain[0] && timeMs <= domain[1];
        }),
        scoreKey,
      ).map((points) => ({
        points,
        scoreKey,
        seriesId: series.seriesId,
      }))
    ))
  )), [domain, scoreSeries]);
  const scoreMarkers = useMemo(() => {
    const unique = new Map();
    scoreSeries.flatMap((series) => series.points).forEach((point) => {
      const timeMs = Date.parse(point.eventAt);
      if (timeMs >= domain[0]
        && timeMs <= domain[1]
        && (point.candidateState === "candidate_not_ground_truth" || point.anchorPointId === selectedPointId)) {
        unique.set(point.anchorPointId, point);
      }
    });
    return [...unique.values()];
  }, [domain, scoreSeries, selectedPointId]);
  const parsedSelectedTime = selectedAt === null ? null : Date.parse(selectedAt);
  const selectedTime = parsedSelectedTime !== null
    && parsedSelectedTime >= domain[0]
    && parsedSelectedTime <= domain[1]
    ? parsedSelectedTime
    : null;
  const visiblePointCount = visibleSeries.reduce((total, series) => total + series.points.length, 0);
  const pointCountLabel = `${visiblePointCount}/${visibleTimes.length} pontos visíveis`;
  const zoomModeLabel = viewportMode === "auto"
    ? `Zoom automático · ${Math.max(1, Math.round(zoomFactor))}×`
    : viewportMode === "full"
      ? "Janela completa · 1×"
      : `Zoom manual · ${Math.max(1, Math.round(zoomFactor))}×`;
  const zoomLabel = `${zoomModeLabel} · ${pointCountLabel}`;

  return (
    <div className="decision-chart" data-testid="decision-timeline-chart">
      <div aria-label="Controle de zoom do gráfico" className="decision-chart__zoom" role="group">
        <button
          disabled={domain[0] <= fullDomain[0]}
          onClick={() => pan(-1)}
          type="button"
        >
          Período anterior
        </button>
        <button
          aria-label="Reduzir zoom"
          disabled={zoomIndex === 0}
          onClick={() => applyZoomIndex(zoomIndex - 1)}
          type="button"
        >
          Menos zoom
        </button>
        <label className="decision-chart__zoom-level">
          <span>Nível de zoom</span>
          <input
            aria-label="Nível de zoom"
            max={ZOOM_FACTORS.length - 1}
            min="0"
            onChange={(event) => applyZoomIndex(Number(event.target.value))}
            step="1"
            type="range"
            value={zoomIndex}
          />
        </label>
        <output aria-live="polite">{zoomLabel}</output>
        <button
          aria-label="Aumentar zoom"
          disabled={zoomIndex === ZOOM_FACTORS.length - 1}
          onClick={() => applyZoomIndex(zoomIndex + 1)}
          type="button"
        >
          Mais zoom
        </button>
        <button
          disabled={domain[1] >= fullDomain[1]}
          onClick={() => pan(1)}
          type="button"
        >
          Período seguinte
        </button>
        <button
          onClick={() => setViewport({ domain: null, key: domainKey, mode: "auto" })}
          type="button"
        >
          Enquadrar dados
        </button>
        <button onClick={() => setManualDomain(fullDomain, "full")} type="button">
          Mostrar janela completa
        </button>
      </div>
      <section aria-labelledby="sensor-chart-title" className="decision-chart__section">
        <div className="decision-chart__heading">
          <h3 id="sensor-chart-title">Vibração · velocidade RMS</h3>
          <div aria-label="Legenda dos sensores" className="decision-chart__legend" role="group">
            <span><i data-sensor="s1" />S1 (mm/s)</span>
            <span><i data-sensor="s2" />S2 (mm/s)</span>
            <span><i data-kind="gap" />Lacuna de cobertura</span>
            <span><i data-kind="candidate" />Candidato</span>
          </div>
        </div>
        <div className="decision-chart__canvas">
          <svg
            aria-label="Telemetria histórica sincronizada"
            data-domain-from={domain[0]}
            data-domain-to={domain[1]}
            role="img"
            viewBox={`0 0 ${CHART_WIDTH} ${SENSOR_CHART_HEIGHT}`}
          >
            <Grid
              domain={domain}
              fractionDigits={sensorDomain[1] - sensorDomain[0] < 0.1 ? 3 : 2}
              height={SENSOR_CHART_HEIGHT}
              valueDomain={sensorDomain}
            />
            <GapAreas domain={domain} gaps={model.gaps} height={SENSOR_CHART_HEIGHT} />
            {visibleSeries.map((series) => (
              <polyline
                aria-hidden="true"
                data-sensor={series.sensorId}
                key={`${series.segmentId}:${series.sensorId}`}
                points={linePoints(series.points, domain, sensorDomain, SENSOR_CHART_HEIGHT)}
              />
            ))}
            {selectedTime === null ? null : (
              <line
                className="decision-chart__crosshair"
                x1={scaleX(selectedTime, domain)}
                x2={scaleX(selectedTime, domain)}
                y1={MARGIN.top}
                y2={SENSOR_CHART_HEIGHT - MARGIN.bottom}
              />
            )}
            {sensorPoints.map((point) => {
              const activate = () => onSelectPoint(point.pointId);
              return (
                <PointButton
                  candidate={candidatePointIds.has(point.pointId)}
                  color={SENSOR_COLORS[point.sensorId]}
                  cx={scaleX(point.timeMs, domain)}
                  cy={scaleY(point.value, sensorDomain, SENSOR_CHART_HEIGHT)}
                  key={point.pointId}
                  label={`Inspecionar ponto ${point.pointId}`}
                  onActivate={activate}
                  selected={point.pointId === selectedPointId}
                  title={`${point.sensorId.toUpperCase()} · ${dateFormatter.format(new Date(point.timeMs))} · ${point.value}`}
                />
              );
            })}
          </svg>
        </div>
      </section>

      <section aria-labelledby="score-chart-title" className="decision-chart__section decision-chart__section--scores">
        <div className="decision-chart__heading">
          <h3 id="score-chart-title">Scores relativos · 0–100</h3>
          <div aria-label="Legenda dos scores" className="decision-chart__legend" role="group">
            <span><i data-score="anomaly" />Anomalia relativa</span>
            <span><i data-score="deterioration" />Deterioração relativa</span>
          </div>
        </div>
        {scoreSeries.length === 0 ? (
          <div className="decision-chart__empty-score">
            <strong>Sem scores materializados neste período</strong>
            <span>Nenhum valor foi inferido ou preenchido com zero.</span>
          </div>
        ) : (
          <div className="decision-chart__canvas">
            <svg
              aria-label="Scores históricos sincronizados"
              data-domain-from={domain[0]}
              data-domain-to={domain[1]}
              role="img"
              viewBox={`0 0 ${CHART_WIDTH} ${SCORE_CHART_HEIGHT}`}
            >
              <Grid domain={domain} height={SCORE_CHART_HEIGHT} valueDomain={[0, 100]} />
              <GapAreas domain={domain} gaps={model.gaps} height={SCORE_CHART_HEIGHT} />
              {scoreRuns.map((run, index) => (
                <polyline
                  aria-hidden="true"
                  data-score={run.scoreKey === "anomalyScore" ? "anomaly" : "deterioration"}
                  key={`${run.seriesId}:${run.scoreKey}:${index}`}
                  points={linePoints(run.points, domain, [0, 100], SCORE_CHART_HEIGHT)}
                />
              ))}
              {selectedTime === null ? null : (
                <line
                  className="decision-chart__crosshair"
                  x1={scaleX(selectedTime, domain)}
                  x2={scaleX(selectedTime, domain)}
                  y1={MARGIN.top}
                  y2={SCORE_CHART_HEIGHT - MARGIN.bottom}
                />
              )}
              {scoreMarkers.map((point) => {
                const value = Math.max(point.anomalyScore ?? 0, point.deteriorationScore ?? 0);
                const activate = () => onSelectPoint(point.anchorPointId);
                return (
                  <PointButton
                    candidate={point.candidateState === "candidate_not_ground_truth"}
                    color="#5eead4"
                    cx={scaleX(Date.parse(point.eventAt), domain)}
                    cy={scaleY(value, [0, 100], SCORE_CHART_HEIGHT)}
                    key={point.anchorPointId}
                    label={`Inspecionar evidência ${point.anchorPointId}`}
                    onActivate={activate}
                    selected={point.anchorPointId === selectedPointId}
                    title={`${dateFormatter.format(new Date(point.eventAt))} · score ${value}`}
                  />
                );
              })}
            </svg>
          </div>
        )}
      </section>
    </div>
  );
}
