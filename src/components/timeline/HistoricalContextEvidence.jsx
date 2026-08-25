import React from "react";

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  dateStyle: "short",
  timeStyle: "medium",
});
const originLabels = {
  historical_archive: "Arquivo histórico",
  live_collection: "Coleta ao vivo persistida",
};
const timestampQualityLabels = {
  source_without_offset_assumed_timezone: "Fonte sem offset; fuso horário assumido pelo pipeline",
  assumed_from_retrieval: "Horário assumido a partir da captura do gateway",
};
const availabilityLabels = {
  complete: "Cobertura completa no contexto",
  partial: "Cobertura parcial no contexto",
  gap: "Sem cobertura no intervalo",
};

const displayValue = (value) => value ?? "Indisponível";

export default function HistoricalContextEvidence({ context }) {
  const isGap = context.decisionFacts.collectionState === "historical_gap";
  const channels = [context.channels.s1, context.channels.s2].filter(Boolean);
  const anchor = context.anchor;
  const qualityFlags = [...new Set(channels.flatMap((channel) => channel.qualityFlags))].sort();
  const limitations = isGap
    ? "Indisponível sem um ponto original coberto"
    : context.limitations.length > 0
    ? context.limitations.join(" · ")
    : "Nenhuma limitação adicional registrada para este ponto";

  return (
    <section
      className={`historical-context-evidence${isGap ? " historical-context-evidence--gap" : ""}`}
      data-context-kind={isGap ? "gap" : "point"}
      data-testid="historical-context-evidence"
      aria-labelledby="historical-context-title"
    >
      <div className="timeline-section-heading">
        <div>
          <p className="eyebrow">Contexto sincronizado</p>
          <h2 id="historical-context-title">
            {isGap ? "Intervalo sem cobertura" : "Evidência do ponto selecionado"}
          </h2>
        </div>
        <p>
          <time dateTime={context.selectedAt}>{dateTimeFormatter.format(new Date(context.selectedAt))}</time>
        </p>
      </div>

      {isGap ? (
        <p className="historical-gap-copy">
          O TwinOps não tem dados para este intervalo. Isso não implica que o ativo estava parado,
          normal ou sem anomalias.
        </p>
      ) : null}

      <dl className="historical-context-facts">
        <div><dt>Instante selecionado</dt><dd>{dateTimeFormatter.format(new Date(context.selectedAt))}</dd></div>
        <div><dt>Origem</dt><dd>{originLabels[context.provenance.pointSourceKind] ?? "Indisponível"}</dd></div>
        <div><dt>Sistema de origem</dt><dd>{displayValue(context.provenance.pointSourceSystem)}</dd></div>
        <div>
          <dt>Qualidade do timestamp</dt>
          <dd>{timestampQualityLabels[anchor?.timestampQuality] ?? "Indisponível"}</dd>
        </div>
        <div><dt>Flags de qualidade</dt><dd>{qualityFlags.length > 0 ? qualityFlags.join(" · ") : channels.length > 0 ? "Sem flags registradas" : "Indisponível"}</dd></div>
        <div><dt>Política de coleta</dt><dd>{displayValue(context.provenance.collectionPolicyId)}</dd></div>
        <div><dt>Disponibilidade dos dados</dt><dd>{availabilityLabels[context.decisionFacts.dataAvailability] ?? "Indisponível"}</dd></div>
        <div><dt>Limitações declaradas</dt><dd>{limitations}</dd></div>
      </dl>
    </section>
  );
}
