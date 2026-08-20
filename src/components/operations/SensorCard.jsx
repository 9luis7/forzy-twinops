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
  const timestamp = channel.observedAt ?? channel.receivedAt;
  if (!timestamp) return null;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? null : dateFormatter.format(date);
};

export default function SensorCard({ channel }) {
  const captured = capturedAt(channel);

  return (
    <article className="panel sensor-card" aria-labelledby={`sensor-${channel.sensorId}`}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Canal real</p>
          <h2 id={`sensor-${channel.sensorId}`}>{channel.sensorId.toUpperCase()}</h2>
        </div>
        <span className="quality-chip">
          {channel.qualityFlags.length === 0 ? "Sem flags de qualidade" : "Qualidade degradada"}
        </span>
      </div>

      <dl className="measurement-list">
        {measurementRows.map(([key, label]) => {
          const measurement = channel.measurements[key];
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
        <p>{captured ? `Capturado pelo TwinOps às ${captured}` : "Horário indisponível"}</p>
        {channel.timestampQuality === "assumed_from_retrieval" && (
          <small>Horário assumido a partir da captura; não fornecido pelo sensor.</small>
        )}
      </div>
    </article>
  );
}
