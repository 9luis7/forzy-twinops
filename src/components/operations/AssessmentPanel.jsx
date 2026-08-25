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

function formatMeasurement(value, suffix = "") {
  return Number.isFinite(value) ? `${numberFormatter.format(value)}${suffix}` : "Indisponível";
}

export default function AssessmentPanel({ assessment, historical = false }) {
  const historicalAssessment = historical && assessment?.schemaVersion === "1.0";
  const assessmentValues = assessment === null
    ? null
    : historicalAssessment
      ? {
          status: assessment.status,
          anomalyScore: assessment.anomalyScore,
          deteriorationScore: assessment.deteriorationScore,
          persistenceSeconds: assessment.persistence.persistenceSeconds,
          evidence: assessment.evidence,
          modelName: assessment.modelFamily,
          modelVersion: assessment.modelVersion,
        }
      : {
          status: assessment.assessment.status,
          anomalyScore: assessment.assessment.anomalyScore,
          deteriorationScore: assessment.assessment.deteriorationScore,
          persistenceSeconds: assessment.assessment.persistenceSeconds,
          evidence: assessment.evidence,
          modelName: assessment.model.name,
          modelVersion: assessment.model.version,
        };

  return (
    <section className="panel assessment-panel" data-testid="assessment-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">
            {historical
              ? assessment === null ? "Contexto histórico" : "Avaliação causal publicada"
              : "Baseline clássico publicado"}
          </p>
          <h2>Avaliação do modelo</h2>
        </div>
      </div>

      {assessment === null ? (
        historical ? (
          <p className="empty-state">Avaliação causal indisponível para este ponto</p>
        ) : (
          <>
            <p className="model-disclaimer">
              Desvio relativo ao histórico — não é probabilidade de falha
            </p>
            <p className="empty-state">Avaliação indisponível</p>
          </>
        )
      ) : (
        <>
          <p className="model-disclaimer">
            Desvio relativo ao histórico — não é probabilidade de falha
          </p>
          <p className="assessment-status">
            {statusLabels[assessmentValues.status] ?? "Estado não informado"}
          </p>
          <dl className="score-grid">
            <div>
              <dt>Score de anomalia relativo</dt>
              <dd>{formatMeasurement(assessmentValues.anomalyScore)}</dd>
            </div>
            <div>
              <dt>Score de deterioração relativo</dt>
              <dd>{formatMeasurement(assessmentValues.deteriorationScore)}</dd>
            </div>
            <div>
              <dt>Persistência</dt>
              <dd>{formatMeasurement(assessmentValues.persistenceSeconds, " s")}</dd>
            </div>
          </dl>
          {assessmentValues.evidence.length > 0 ? (
            <div className="assessment-evidence">
              <h3>Evidências numéricas</h3>
              <ul>
                {assessmentValues.evidence.map((evidence) => (
                  <li key={evidence.id}>
                    <span>{evidence.feature}</span>
                    <strong>{formatMeasurement(evidence.value, evidence.unit ? ` ${evidence.unit}` : "")}</strong>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <p className="model-meta">
            Modelo {assessmentValues.modelName} {assessmentValues.modelVersion}. Validação humana obrigatória.
          </p>
        </>
      )}
    </section>
  );
}
