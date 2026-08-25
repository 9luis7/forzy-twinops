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
const HISTORICAL_SCALE_COPY = "Score relativo ao baseline hist\u00f3rico (escala 0\u2013100). N\u00e3o \u00e9 probabilidade de falha, confian\u00e7a calibrada, RUL nem diagn\u00f3stico.";
const HISTORICAL_CANDIDATE_COPY = "Candidato n\u00e3o confirmado para revis\u00e3o humana. Este desvio n\u00e3o confirma falha, causa ou componente.";
const HISTORICAL_LABELS_COPY = "O conjunto de dados n\u00e3o cont\u00e9m r\u00f3tulos de falha confirmada.";
const HISTORICAL_VALIDATION_COPY = "Valida\u00e7\u00e3o humana obrigat\u00f3ria antes de qualquer a\u00e7\u00e3o operacional.";

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
          trainingEnd: assessment.trainingWindow?.end ?? null,
        }
      : {
          status: assessment.assessment.status,
          anomalyScore: assessment.assessment.anomalyScore,
          deteriorationScore: assessment.assessment.deteriorationScore,
          persistenceSeconds: assessment.assessment.persistenceSeconds,
          evidence: assessment.evidence,
          modelName: assessment.model.name,
          modelVersion: assessment.model.version,
          trainingEnd: assessment.model.trainedUntil ?? null,
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
            {historicalAssessment
              ? HISTORICAL_SCALE_COPY
              : "Desvio relativo ao hist\u00f3rico \u2014 n\u00e3o \u00e9 probabilidade de falha"}
          </p>
          <p className="assessment-status">
            {statusLabels[assessmentValues.status] ?? "Estado não informado"}
          </p>
          {historicalAssessment && ["watch", "alert"].includes(assessmentValues.status) ? (
            <p className="timeline-inline-warning">{HISTORICAL_CANDIDATE_COPY}</p>
          ) : null}
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
          {historicalAssessment ? (
            <>
              <p className="model-meta">
                Modelo {assessmentValues.modelName} {assessmentValues.modelVersion}
                {assessmentValues.trainingEnd === null
                  ? "."
                  : ` \u00b7 treinamento causal encerrado em ${assessmentValues.trainingEnd}.`}
              </p>
              <p className="model-meta">{HISTORICAL_LABELS_COPY}</p>
              <p className="model-meta">{HISTORICAL_VALIDATION_COPY}</p>
            </>
          ) : (
            <p className="model-meta">
              Modelo {assessmentValues.modelName} {assessmentValues.modelVersion}. Validação humana obrigatória.
            </p>
          )}
        </>
      )}
    </section>
  );
}
