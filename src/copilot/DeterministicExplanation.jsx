import React from "react";

export function deterministicExplanationFromAssessment(assessment) {
  if (!assessment) {
    return {
      answer: "Ainda não há uma avaliação estruturada para explicar. Aguarde a recomposição da janela de dados.",
      evidenceRefs: [],
      limitations: ["Assessment indisponível."],
      humanValidationRequired: true,
      provider: "deterministic-ui",
    };
  }

  const insufficient =
    assessment.quality?.status === "insufficient_data" ||
    assessment.assessment?.status === "insufficient_data";
  const evidence = Array.isArray(assessment.evidence) ? assessment.evidence : [];
  const evidenceText = evidence.length
    ? evidence
        .map((item) => `${item.feature} = ${item.value} ${item.unit} (ref. ${item.id})`)
        .join("; ")
    : "nenhuma evidência quantitativa disponível";

  return {
    answer: insufficient
      ? `Os dados são insuficientes. Recomponha a janela e valide a aquisição antes de sugerir ação mecânica; ${evidenceText}.`
      : `Estado ${assessment.assessment?.status ?? "desconhecido"}, qualidade ${assessment.quality?.status ?? "desconhecida"}; ${evidenceText}. Os escores são relativos ao histórico e exigem validação humana.`,
    evidenceRefs: evidence.map((item) => item.id),
    limitations: [
      ...(assessment.limitations ?? []),
      "Esta explicação não diagnostica causa raiz nem estima tempo até falha.",
    ],
    humanValidationRequired: true,
    provider: "deterministic-ui",
  };
}

export default function DeterministicExplanation({ response }) {
  return (
    <div>
      <p>{response.answer}</p>
      {response.evidenceRefs?.length > 0 && (
        <>
          <h5>Evidências citadas</h5>
          {response.evidenceRefs.map((ref) => (
            <div className="evidence" key={ref}>
              <span className="ev-mark">▸</span>
              <span className="mono">{ref}</span>
            </div>
          ))}
        </>
      )}
      {response.limitations?.length > 0 && (
        <>
          <h5>Limitações</h5>
          <ul>
            {response.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
      {response.humanValidationRequired && (
        <p style={{ color: "var(--alerta)" }}>Validação humana necessária.</p>
      )}
    </div>
  );
}
