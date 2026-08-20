import React from "react";

const numberFormatter = new Intl.NumberFormat("pt-BR");
const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  dateStyle: "short",
  timeStyle: "medium",
});
const errorLabels = {
  upstream_unavailable: "Origem indisponível",
  invalid_payload: "Resposta inválida da origem",
  null: "Integração sem erro registrado",
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
          <p className="eyebrow">Fronteira server-side</p>
          <h2>Saúde da integração</h2>
        </div>
      </div>
      <div className="health-grid">
        {Object.entries(integration.sensors).map(([sensorId, health]) => (
          <article className="health-card" key={sensorId}>
            <h3>{sensorId.toUpperCase()}</h3>
            <p className="health-status">{safeErrorLabel(health.error)}</p>
            <dl>
              <div><dt>Última tentativa</dt><dd>{formatDate(health.lastAttemptAt)}</dd></div>
              <div><dt>Último sucesso</dt><dd>{formatDate(health.lastSuccessAt)}</dd></div>
              <div>
                <dt>Latência do gateway</dt>
                <dd>{health.latencyMs === null ? "Indisponível" : `${numberFormatter.format(health.latencyMs)} ms`}</dd>
              </div>
              <div><dt>Amostras reais</dt><dd>{numberFormatter.format(health.sampleCount)}</dd></div>
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}
