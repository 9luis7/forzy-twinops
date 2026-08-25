import React, { useMemo } from "react";

const WIDTH = 720;
const HEIGHT = 240;
const PADDING = Object.freeze({ top: 20, right: 20, bottom: 32, left: 44 });
const SCALE_COPY = "Score relativo ao baseline hist\u00f3rico (escala 0\u2013100). N\u00e3o \u00e9 probabilidade de falha, confian\u00e7a calibrada, RUL nem diagn\u00f3stico.";
const CANDIDATE_COPY = "Candidato n\u00e3o confirmado para revis\u00e3o humana. Este desvio n\u00e3o confirma falha, causa ou componente.";
const EMPTY_COPY = "Avalia\u00e7\u00f5es causais ainda n\u00e3o foram materializadas para este lote. Nenhum score foi inferido nem preenchido com zero.";
const FILTER_EMPTY_COPY = "Nenhuma avalia\u00e7\u00e3o materializada corresponde ao intervalo ou filtro selecionado. Nenhum score foi preenchido com zero.";
const LABELS_COPY = "O conjunto de dados n\u00e3o cont\u00e9m r\u00f3tulos de falha confirmada.";
const VALIDATION_COPY = "Valida\u00e7\u00e3o humana obrigat\u00f3ria antes de qualquer a\u00e7\u00e3o operacional.";

const finiteExtent = (points) => {
  const values = points.map((point) => Date.parse(point.eventAt));
  return [Math.min(...values), Math.max(...values)];
};

const buildRuns = (points, scoreKey) => {
  const runs = [];
  let current = [];
  points.forEach((point) => {
    if (point[scoreKey] === null) {
      if (current.length > 0) runs.push(current);
      current = [];
    } else {
      current.push(point);
    }
  });
  if (current.length > 0) runs.push(current);
  return runs;
};

function ScoreSeries({ series, scoreKey, kind, xFor, yFor }) {
  const runs = buildRuns(series.points, scoreKey);
  return (
    <g data-score-kind={kind} data-series-id={series.seriesId}>
      {runs.map((run) => {
        const coordinates = run.map((point) => `${xFor(point.eventAt)},${yFor(point[scoreKey])}`);
        const key = `${series.seriesId}-${kind}-${run[0].assessmentId}`;
        if (run.length === 1) {
          return <circle cx={xFor(run[0].eventAt)} cy={yFor(run[0][scoreKey])} key={key} r="3" />;
        }
        return <polyline key={key} points={coordinates.join(" ")} />;
      })}
    </g>
  );
}

export default function AssessmentTrend({ overview }) {
  const points = useMemo(
    () => overview?.series?.flatMap((series) => series.points) ?? [],
    [overview],
  );

  if (overview?.materialization?.state !== "materialized" || points.length === 0) {
    const noActiveBatch = overview?.materialization?.state === "no_active_historical_batch";
    const materializedFilterEmpty = overview?.materialization?.state === "materialized";
    return (
      <section className="assessment-trend" data-testid="assessment-trend" aria-labelledby="assessment-trend-title">
        <div className="timeline-section-heading">
          <div>
            <p className="eyebrow">{"Evid\u00eancia de modelo persistida"}</p>
            <h3 id="assessment-trend-title">{"Scores hist\u00f3ricos relativos"}</h3>
          </div>
        </div>
        <p className="timeline-empty">
          {noActiveBatch
            ? "Nenhum lote hist\u00f3rico ativo est\u00e1 dispon\u00edvel. Nenhum score foi inferido nem preenchido com zero."
            : materializedFilterEmpty ? FILTER_EMPTY_COPY : EMPTY_COPY}
        </p>
      </section>
    );
  }

  const [minimumTime, maximumTime] = finiteExtent(points);
  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const timeSpan = Math.max(maximumTime - minimumTime, 1);
  const xFor = (eventAt) => PADDING.left + ((Date.parse(eventAt) - minimumTime) / timeSpan) * plotWidth;
  const yFor = (score) => PADDING.top + ((100 - score) / 100) * plotHeight;
  const hasCandidate = points.some((point) => point.status === "watch" || point.status === "alert");

  return (
    <section className="assessment-trend" data-testid="assessment-trend" aria-labelledby="assessment-trend-title">
      <div className="timeline-section-heading">
        <div>
          <p className="eyebrow">{"Evid\u00eancia de modelo persistida"}</p>
          <h3 id="assessment-trend-title">{"Scores hist\u00f3ricos relativos"}</h3>
        </div>
        <p>{overview.aggregationSummary.returnedAssessmentCount} {"avalia\u00e7\u00f5es exibidas"}</p>
      </div>

      <p className="model-disclaimer">{SCALE_COPY}</p>
      <svg
        aria-label={"Tend\u00eancia hist\u00f3rica de scores relativos na escala de 0 a 100"}
        className="assessment-trend__chart"
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      >
        {[100, 50, 0].map((score) => (
          <g className="assessment-trend__grid" key={score}>
            <line x1={PADDING.left} x2={WIDTH - PADDING.right} y1={yFor(score)} y2={yFor(score)} />
            <text x={PADDING.left - 8} y={yFor(score) + 4}>{score}</text>
          </g>
        ))}
        {overview.series.map((series) => (
          <React.Fragment key={series.seriesId}>
            <ScoreSeries
              kind="anomaly"
              scoreKey="anomalyScore"
              series={series}
              xFor={xFor}
              yFor={yFor}
            />
            <ScoreSeries
              kind="deterioration"
              scoreKey="deteriorationScore"
              series={series}
              xFor={xFor}
              yFor={yFor}
            />
          </React.Fragment>
        ))}
      </svg>

      <div className="assessment-trend__legend" aria-label="Legenda dos scores relativos">
        <span><i data-score-kind="anomaly" />Anomalia relativa</span>
        <span><i data-score-kind="deterioration" />{"Deteriora\u00e7\u00e3o relativa"}</span>
      </div>
      {hasCandidate ? <p className="timeline-inline-warning">{CANDIDATE_COPY}</p> : null}
      <ul className="assessment-trend__models" aria-label={"Modelos causais das s\u00e9ries exibidas"}>
        {overview.series.map((series) => (
          <li key={series.seriesId}>
            Modelo {series.modelFamily} {series.modelVersion}{" \u00b7 treinamento causal encerrado em "}{series.trainingWindow.end}.
          </li>
        ))}
      </ul>
      <p className="model-meta">{LABELS_COPY}</p>
      <p className="model-meta">{VALIDATION_COPY}</p>
    </section>
  );
}
