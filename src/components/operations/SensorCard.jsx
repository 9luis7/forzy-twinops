import React from "react";

const numberFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  dateStyle: "short",
  timeStyle: "medium",
});

const measurementRows = [
  ["vibrationVelocityRms", "Velocidade de vibração RMS"],
  ["vibrationAcceleration", "Aceleração de vibração"],
  ["temperature", "Temperatura"],
];

const capturedAt = (channel) => {
  const timestamp = channel?.eventAt ?? channel?.observedAt ?? channel?.receivedAt;
  if (!timestamp) return null;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? null : dateFormatter.format(date);
};

export default function SensorCard({ channel, sensorId = channel?.sensorId, historical = false }) {
  const captured = capturedAt(channel);
  const resolvedSensorId = sensorId ?? "indisponivel";
  const qualityLabel = channel === null
    ? "Canal indisponível"
    : channel.qualityFlags.length === 0
      ? "Sem flags de qualidade"
      : "Qualidade degradada";

  return (
    <article
      className="panel sensor-card"
      aria-labelledby={`sensor-${resolvedSensorId}`}
      data-testid={`sensor-card-${resolvedSensorId}`}
    >
      <div className="panel-heading">
        <div>
          <p className="eyebrow">
            {historical ? channel === null ? "Cobertura histórica" : "Ponto original" : "Canal real"}
          </p>
          <h2 id={`sensor-${resolvedSensorId}`}>{resolvedSensorId.toUpperCase()}</h2>
        </div>
        <span className="quality-chip">{qualityLabel}</span>
      </div>

      <dl className="measurement-list">
        {measurementRows.map(([key, label]) => {
          const measurement = channel?.measurements?.[key] ?? null;
          return (
            <div className="measurement" key={key}>
              <dt>{label}</dt>
              <dd>
                {measurement === null ? (
                  "Indisponível"
                ) : (
                  <>
                    <strong>{numberFormatter.format(measurement.value)}</strong>
                    <span>{measurement.unit}</span>
                  </>
                )}
              </dd>
              {measurement?.statistic === "unknown" && (
                <small>Estatística não confirmada pela origem</small>
              )}
            </div>
          );
        })}
      </dl>

      <div className="capture-note">
        <p>
          {captured
            ? historical ? `Ponto selecionado em ${captured}` : `Capturado pelo TwinOps às ${captured}`
            : "Horário indisponível"}
        </p>
        {channel?.timestampQuality === "assumed_from_retrieval" ? (
          <small>Horário assumido a partir da captura; não fornecido pelo sensor.</small>
        ) : null}
        {channel?.timestampQuality === "source_without_offset_assumed_timezone" ? (
          <small>Fonte sem offset; fuso horário assumido pelo pipeline.</small>
        ) : null}
      </div>
    </article>
  );
}
