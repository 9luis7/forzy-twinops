import React from "react";

const numberFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const statusLabels = {
  normal: "Sem desvio relevante",
  watch: "Atenção",
  alert: "Alerta relativo",
  insufficient_data: "Dados insuficientes",
};

export default function AssessmentPanel({ assessment }) {
  return (
    <section className="panel assessment-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Baseline clássico publicado</p>
          <h2>Avaliação do modelo</h2>
        </div>
      </div>

      <p className="model-disclaimer">
        Desvio relativo ao histórico — não é probabilidade de falha
      </p>

      {assessment === null ? (
        <p className="empty-state">Avaliação indisponível</p>
      ) : (
        <>
          <p className="assessment-status">
            {statusLabels[assessment.assessment.status] ?? "Estado não informado"}
          </p>
          <dl className="score-grid">
            <div>
              <dt>Score de anomalia relativo</dt>
              <dd>{numberFormatter.format(assessment.assessment.anomalyScore)}</dd>
            </div>
            <div>
              <dt>Score de deterioração relativo</dt>
              <dd>{numberFormatter.format(assessment.assessment.deteriorationScore)}</dd>
            </div>
            <div>
              <dt>Persistência</dt>
              <dd>{numberFormatter.format(assessment.assessment.persistenceSeconds)} s</dd>
            </div>
          </dl>
          {assessment.evidence.length > 0 && (
            <div className="assessment-evidence">
              <h3>Evidências numéricas</h3>
              <ul>
                {assessment.evidence.map((evidence) => (
                  <li key={evidence.id}>
                    <span>{evidence.feature}</span>
                    <strong>{numberFormatter.format(evidence.value)} {evidence.unit}</strong>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="model-meta">
            Modelo {assessment.model.name} {assessment.model.version}. Validação humana obrigatória.
          </p>
        </>
      )}
    </section>
  );
}
