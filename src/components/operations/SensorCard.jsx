import React from "react";
import { formatDateTime } from "../../lib/displayTime.js";
import "./operationalDetails.css";

const numberFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const measurementRows = [
  ["vibrationVelocityRms", "Velocidade de vibração RMS"],
  ["vibrationAcceleration", "Aceleração de vibração"],
  ["temperature", "Temperatura"],
];

const capturedAt = (channel) => {
  const timestamp = channel.observedAt ?? channel.receivedAt;
  return formatDateTime(timestamp, null);
};

export default function SensorCard({ channel }) {
  const captured = capturedAt(channel);
  const componentLabel = channel.sensorId === "s1" ? "Motor" : "Bomba";
  const qualityLabel = channel.qualityFlags.length === 1 && channel.qualityFlags.includes("last_known")
    ? "Leitura anterior"
    : channel.qualityFlags.length === 0 ? "Sem alertas de qualidade" : "Dados com ressalvas";

  return (
    <article className="panel sensor-card" data-sensor={channel.sensorId} aria-labelledby={`sensor-${channel.sensorId}`}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Leitura do sensor</p>
          <h2 id={`sensor-${channel.sensorId}`}><span className="sensor-identity-dot" aria-hidden="true" />{channel.sensorId.toUpperCase()} · {componentLabel}</h2>
        </div>
        <span className="quality-chip">
          {qualityLabel}
        </span>
      </div>
      <p className="sensor-placement-note">Vínculo com {componentLabel.toLowerCase()} e posição assumidos para demonstração.</p>

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
        <p>{captured ? `Capturado pelo TwinOps às ${captured} · São Paulo` : "Horário indisponível"}</p>
        {channel.timestampQuality === "assumed_from_retrieval" && (
          <small>Horário assumido a partir da captura; não fornecido pelo sensor.</small>
        )}
      </div>
    </article>
  );
}
