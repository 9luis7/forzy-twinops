import React from "react";
import "./operationalDetails.css";

const numberFormatter = new Intl.NumberFormat("pt-BR");
const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  dateStyle: "short",
  timeStyle: "medium",
});
const errorLabels = {
  upstream_unavailable: "Origem indisponível",
  invalid_payload: "Resposta inválida da origem",
  null: "Nenhum erro de coleta registrado",
};

const formatDate = (value) => {
  if (value === null) return "Indisponível";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Indisponível" : dateFormatter.format(date);
};

const safeErrorLabel = (error) => {
  const key = error === null ? "null" : error;
  return errorLabels[key] ?? "Erro de integração";
};

export default function IntegrationHealth({ integration }) {
  return (
    <section className="panel integration-panel">
      <div className="panel-heading">
        <div>
          <h2>Atualização dos dados</h2>
        </div>
      </div>
      <p className="model-meta">A disponibilidade da coleta não indica a condição do equipamento.</p>
      <div className="health-grid">
        {Object.entries(integration.sensors).map(([sensorId, health]) => (
          <article className="health-card" key={sensorId}>
            <h3>{sensorId.toUpperCase()} · {sensorId === "s1" ? "Motor" : "Bomba"}</h3>
            <p className="health-status" data-has-error={health.error !== null}>{safeErrorLabel(health.error)}</p>
            <dl>
              <div><dt>Última coleta válida</dt><dd>{formatDate(health.lastSuccessAt)}</dd></div>
            </dl>
            <details className="operational-details">
              <summary>Detalhes técnicos de {sensorId.toUpperCase()}</summary>
              <dl>
                <div><dt>Última tentativa de coleta</dt><dd>{formatDate(health.lastAttemptAt)}</dd></div>
                <div>
                  <dt>Latência do gateway</dt>
                  <dd>{health.latencyMs === null ? "Indisponível" : `${numberFormatter.format(health.latencyMs)} ms`}</dd>
                </div>
                <div><dt>Amostras reais</dt><dd>{numberFormatter.format(health.sampleCount)}</dd></div>
              </dl>
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}
