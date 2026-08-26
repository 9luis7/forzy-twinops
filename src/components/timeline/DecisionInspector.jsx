import React from "react";

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  dateStyle: "short",
  timeStyle: "medium",
});
const numberFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const sourceLabels = Object.freeze({
  historical_archive: "Arquivo histórico",
  live_collection: "Coleta ao vivo persistida",
});
const availabilityLabels = Object.freeze({
  complete: "Adequada · canais pareados",
  partial: "Parcial · um canal indisponível",
  gap: "Lacuna sem cobertura",
});
const limitationLabels = Object.freeze({
  causal_assessment_not_available: "Score causal histórico ainda não materializado para este ponto.",
  candidate_not_ground_truth: "Candidato exige confirmação ou rejeição humana.",
  no_confirmed_failure_labels: "Não há falhas confirmadas no conjunto de treinamento.",
  relative_score_not_failure_probability: "Score relativo; não representa probabilidade de falha.",
  timeline_coverage_gap: "Sem cobertura neste intervalo; isso não descreve o estado físico do ativo.",
});

const measurement = (channel) => channel?.measurements?.vibrationVelocityRms ?? null;
const formattedMeasurement = (channel) => {
  const value = measurement(channel);
  return value === null ? "Indisponível" : `${numberFormatter.format(value.value)} ${value.unit}`;
};
const formattedScore = (value) => value === null || value === undefined
  ? "Indisponível"
  : `${numberFormatter.format(value)} / 100`;
const formattedLimitations = (limitations) => limitations.length === 0
  ? "Nenhuma limitação adicional registrada"
  : limitations.map((code) => limitationLabels[code] ?? `Limitação técnica: ${code}`).join(" ");

export default function DecisionInspector({
  context,
  error,
  loading,
  onOpenEvidence,
  onRetry,
  requestedPointId,
}) {
  const assessment = context?.assessment ?? null;
  const assessmentStatus = assessment?.status ?? assessment?.assessment?.status ?? null;
  const anomalyScore = assessment?.anomalyScore ?? assessment?.assessment?.anomalyScore ?? null;
  const deteriorationScore = assessment?.deteriorationScore
    ?? assessment?.assessment?.deteriorationScore
    ?? null;
  const modelFamily = assessment?.modelFamily ?? assessment?.model?.name ?? null;
  const modelVersion = assessment?.modelVersion ?? assessment?.model?.version ?? null;
  const trainedUntil = assessment?.trainingWindow?.end ?? assessment?.model?.trainedUntil ?? null;
  const assessmentLimitations = assessment?.limitations ?? [];
  const candidate = ["watch", "alert"].includes(assessmentStatus);

  return (
    <aside aria-label="Ponto selecionado" className="decision-inspector">
      <p className="eyebrow">Ponto selecionado</p>
      {loading ? (
        <div className="decision-inspector__state" role="status">
          <strong>Sincronizando evidência…</strong>
          <span>O último contexto válido continua preservado.</span>
        </div>
      ) : null}
      {error ? (
        <div className="decision-inspector__state decision-inspector__state--error" role="alert">
          <strong>Não foi possível carregar este ponto.</strong>
          <span>A falha foi mantida visível ao lado do gráfico.</span>
          {requestedPointId === null ? null : (
            <button onClick={() => onRetry(requestedPointId)} type="button">Tentar novamente</button>
          )}
        </div>
      ) : null}
      {context === null ? (
        <div className="decision-inspector__empty">
          <strong>Selecione um ponto no gráfico</strong>
          <p>S1, S2, scores, origem e qualidade aparecerão aqui sem mudar sua posição na página.</p>
        </div>
      ) : (
        <>
          <h2>{dateFormatter.format(new Date(context.selectedAt))}</h2>
          <p className="decision-inspector__timezone">America/Sao_Paulo</p>

          <dl className="decision-inspector__measurements">
            <div data-sensor="s1">
              <dt>S1 · Velocidade RMS</dt>
              <dd>{formattedMeasurement(context.channels.s1)}</dd>
            </div>
            <div data-sensor="s2">
              <dt>S2 · Velocidade RMS</dt>
              <dd>{formattedMeasurement(context.channels.s2)}</dd>
            </div>
            <div data-score="anomaly">
              <dt>Anomalia relativa</dt>
              <dd>{formattedScore(anomalyScore)}</dd>
            </div>
            <div data-score="deterioration">
              <dt>Deterioração relativa</dt>
              <dd>{formattedScore(deteriorationScore)}</dd>
            </div>
          </dl>

          <div className="decision-inspector__status">
            <small>Status</small>
            <strong data-candidate={candidate ? "true" : "false"}>
              {assessment === null
                ? "Sem score materializado neste ponto"
                : candidate
                  ? "Candidato não confirmado"
                  : "Nenhum candidato neste ponto"}
            </strong>
          </div>

          <dl className="decision-inspector__facts">
            <div><dt>Origem dos dados</dt><dd>{sourceLabels[context.provenance.pointSourceKind] ?? "Indisponível"}</dd></div>
            <div><dt>Qualidade do ponto</dt><dd>{context.anchor?.qualityFlags?.length ? context.anchor.qualityFlags.join(" · ") : "Sem flags registradas"}</dd></div>
            <div><dt>Cobertura</dt><dd>{availabilityLabels[context.decisionFacts.dataAvailability] ?? "Indisponível"}</dd></div>
            {modelFamily === null || modelVersion === null || trainedUntil === null ? null : (
              <>
                <div><dt>Modelo</dt><dd>{modelFamily} {modelVersion}</dd></div>
                <div><dt>Treinado até</dt><dd>{dateFormatter.format(new Date(trainedUntil))}</dd></div>
                {assessmentLimitations.includes("no_confirmed_failure_labels") ? (
                  <div><dt>Falhas confirmadas</dt><dd>Ausentes no conjunto de treinamento</dd></div>
                ) : null}
              </>
            )}
            <div><dt>Limitação</dt><dd>{formattedLimitations(context.limitations)}</dd></div>
          </dl>

          <div className="decision-inspector__disclaimer">
            <strong>Score relativo ao baseline histórico</strong>
            <span>Não é probabilidade de falha</span>
          </div>

          <div className="decision-inspector__actions">
            <button onClick={onOpenEvidence} type="button">Revisar evidência</button>
            <button className="decision-inspector__secondary" onClick={onOpenEvidence} type="button">
              Ver leitura original
            </button>
          </div>
        </>
      )}
    </aside>
  );
}
