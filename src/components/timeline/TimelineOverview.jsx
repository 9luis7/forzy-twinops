import React, { useId } from "react";

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  dateStyle: "short",
  timeStyle: "short",
});

const sourceLabels = {
  historical_archive: "Arquivo histórico",
  live_collection: "Coleta ao vivo",
};

const sensorIds = ["s1", "s2"];

const formatTimestamp = (value) => dateTimeFormatter.format(new Date(value));
const originalPointLabel = (count) => (
  `${count} ${count === 1 ? "ponto original" : "pontos originais"}`
);

function TimelineLane({ gaps, sensorId, series }) {
  const sensorSeries = series.filter((entry) => entry.sensorId === sensorId);
  const values = sensorSeries.flatMap((entry) => entry.points.map((point) => point.value));
  const minimum = values.length > 0 ? Math.min(...values) : 0;
  const maximum = values.length > 0 ? Math.max(...values) : 0;
  const valueSpan = maximum - minimum;
  const yPosition = (value) => valueSpan === 0 ? 20 : 34 - ((value - minimum) / valueSpan) * 28;

  return (
    <div className="timeline-lane" data-sensor-id={sensorId}>
      <div className="timeline-lane__label">
        <strong>{sensorId.toUpperCase()}</strong>
        <span>{values.length === 0 ? "Sem pontos no período" : `${values.length} pontos reduzidos`}</span>
      </div>
      <svg
        aria-hidden="true"
        className="timeline-lane__plot"
        preserveAspectRatio="none"
        viewBox="0 0 100 40"
      >
        {gaps.map((gap) => (
          <rect
            className="timeline-lane__gap"
            data-gap-id={gap.gapId}
            height="40"
            key={gap.gapId}
            width={gap.widthPercent}
            x={gap.startPercent}
            y="0"
          />
        ))}
        {sensorSeries.map((entry) => {
          if (entry.points.length === 0) return null;
          const className = `timeline-lane__series timeline-source--${entry.sourceKind}`;
          if (entry.showSinglePointMarker) {
            const point = entry.points[0];
            return (
              <circle
                className={className}
                cx={point.xPercent}
                cy={yPosition(point.value)}
                data-segment-id={entry.segmentId}
                data-source-kind={entry.sourceKind}
                key={`${entry.segmentId}:${entry.sensorId}`}
                r="1.4"
                vectorEffect="non-scaling-stroke"
              />
            );
          }
          return (
            <polyline
              className={className}
              data-segment-id={entry.segmentId}
              data-source-kind={entry.sourceKind}
              fill="none"
              key={`${entry.segmentId}:${entry.sensorId}`}
              points={entry.points.map((point) => `${point.xPercent},${yPosition(point.value)}`).join(" ")}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>
    </div>
  );
}

export default function TimelineOverview({ model }) {
  const segmentDescriptionId = useId();

  if (model.domain === null) {
    return <p className="timeline-empty">Não há cobertura no período solicitado.</p>;
  }

  const [from, to] = model.domain;
  const label = `Cobertura temporal proporcional com ${model.segments.length} trechos e ${model.gaps.length} lacunas`;
  const segmentDescriptionIds = model.segments.map(
    (_segment, index) => `${segmentDescriptionId}-segment-${index}`,
  );

  return (
    <figure className="timeline-overview" aria-labelledby="timeline-evidence-title">
      <figcaption className="timeline-overview__caption">
        <div>
          <p className="eyebrow">Escala de calendário</p>
          <h3 id="timeline-evidence-title">Linha de evidência</h3>
        </div>
        <p>
          <time dateTime={new Date(from).toISOString()}>{formatTimestamp(from)}</time>
          <span aria-hidden="true"> → </span>
          <time dateTime={new Date(to).toISOString()}>{formatTimestamp(to)}</time>
        </p>
      </figcaption>

      <div
        aria-describedby={segmentDescriptionIds.length > 0 ? segmentDescriptionIds.join(" ") : undefined}
        aria-label={label}
        className="timeline-overview__rail"
        role="img"
      >
        {model.segments.map((segment) => (
          <span
            aria-hidden="true"
            className={`timeline-segment timeline-source--${segment.sourceKind}`}
            data-source-kind={segment.sourceKind}
            data-testid="timeline-segment"
            key={segment.segmentId}
            style={{ left: `${segment.startPercent}%`, width: `${segment.widthPercent}%` }}
            title={`${sourceLabels[segment.sourceKind] ?? "Origem indisponível"}: ${formatTimestamp(segment.startMs)} a ${formatTimestamp(segment.endMs)}`}
          />
        ))}
        {model.gaps.map((gap) => (
          <span
            aria-hidden="true"
            className="timeline-gap"
            data-gap-type={gap.gapType}
            data-testid="timeline-gap"
            key={gap.gapId}
            style={{ left: `${gap.startPercent}%`, width: `${gap.widthPercent}%` }}
            title={`Lacuna sem cobertura: ${formatTimestamp(gap.startMs)} a ${formatTimestamp(gap.endMs)}`}
          />
        ))}
      </div>
      <ul
        aria-label="Trechos com cobertura na linha temporal"
        className="timeline-segment-register"
      >
        {model.segments.map((segment, index) => (
          <li id={segmentDescriptionIds[index]} key={segment.segmentId}>
            <span>
              <small>Origem</small>
              {sourceLabels[segment.sourceKind] ?? "Origem indispon\u00edvel"}
            </span>
            <span>
              <small>{"In\u00edcio"}</small>
              <time dateTime={new Date(segment.startMs).toISOString()}>
                {formatTimestamp(segment.startMs)}
              </time>
            </span>
            <span>
              <small>Fim</small>
              <time dateTime={new Date(segment.endMs).toISOString()}>
                {formatTimestamp(segment.endMs)}
              </time>
            </span>
            <span>
              <small>Amostras</small>
              <strong>{originalPointLabel(segment.totalPoints)}</strong>
            </span>
          </li>
        ))}
      </ul>
      <ul className="visually-hidden" aria-label="Lacunas sem cobertura na linha temporal">
        {model.gaps.map((gap) => (
          <li key={gap.gapId}>
            Lacuna sem cobertura de {formatTimestamp(gap.startMs)} a {formatTimestamp(gap.endMs)}
          </li>
        ))}
      </ul>

      <div className="timeline-lanes" aria-label="Séries reduzidas por canal" role="group">
        {sensorIds.map((sensorId) => (
          <TimelineLane
            gaps={model.gaps}
            key={sensorId}
            sensorId={sensorId}
            series={model.series}
          />
        ))}
      </div>

      <div className="timeline-legend" aria-label="Legenda da linha de evidência" role="group">
        <span><i className="timeline-legend__archive" />Arquivo histórico · traço interrompido</span>
        <span><i className="timeline-legend__live" />Coleta ao vivo · traço contínuo</span>
        <span><i className="timeline-legend__gap" />Lacuna · cobertura ausente</span>
      </div>
      <p className="timeline-gap-note">
        As rupturas interrompem fisicamente as séries. Ausência de cobertura não implica que o ativo
        estava parado, normal ou sem anomalias.
      </p>
    </figure>
  );
}
