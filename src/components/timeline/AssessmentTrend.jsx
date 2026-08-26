import React, { useMemo } from "react";

const SCALE_COPY = "Score relativo ao baseline hist\u00f3rico (escala 0\u2013100). N\u00e3o \u00e9 probabilidade de falha, confian\u00e7a calibrada, RUL nem diagn\u00f3stico.";
const CANDIDATE_COPY = "Candidato n\u00e3o confirmado para revis\u00e3o humana. Este desvio n\u00e3o confirma falha, causa ou componente.";
const EMPTY_COPY = "Avalia\u00e7\u00f5es causais ainda n\u00e3o foram materializadas para este lote. Nenhum score foi inferido nem preenchido com zero.";
const FILTER_EMPTY_COPY = "Nenhuma avalia\u00e7\u00e3o materializada corresponde ao intervalo ou filtro selecionado. Nenhum score foi preenchido com zero.";
const LABELS_COPY = "O conjunto de dados n\u00e3o cont\u00e9m r\u00f3tulos de falha confirmada.";
const VALIDATION_COPY = "Valida\u00e7\u00e3o humana obrigat\u00f3ria antes de qualquer a\u00e7\u00e3o operacional.";

const countCandidateEpisodes = (series) => series.reduce((total, item) => {
  let episodeCount = 0;
  let insideEpisode = false;
  for (const point of item.points) {
    const candidate = point.status === "watch" || point.status === "alert";
    if (candidate && !insideEpisode) episodeCount += 1;
    insideEpisode = candidate;
  }
  return total + episodeCount;
}, 0);

export default function AssessmentTrend({ overview }) {
  const points = useMemo(
    () => overview?.series?.flatMap((series) => series.points) ?? [],
    [overview],
  );
  const modelSummaries = useMemo(() => {
    const groups = new Map();
    for (const series of overview?.series ?? []) {
      const key = JSON.stringify([
        series.modelFamily,
        series.modelVersion,
        series.modelHash,
      ]);
      const group = groups.get(key) ?? {
        key,
        modelFamily: series.modelFamily,
        modelVersion: series.modelVersion,
        modelHash: series.modelHash,
        windows: new Map(),
      };
      const windowKey = JSON.stringify([
        series.foldId,
        series.trainingWindow.start,
        series.trainingWindow.end,
      ]);
      group.windows.set(windowKey, series.trainingWindow.end);
      groups.set(key, group);
    }
    return [...groups.values()]
      .sort((left, right) => left.key.localeCompare(right.key))
      .map((group) => {
        const trainingEnds = [...group.windows.values()].sort();
        return {
          ...group,
          windowCount: group.windows.size,
          firstTrainingEnd: trainingEnds[0],
          lastTrainingEnd: trainingEnds.at(-1),
        };
      });
  }, [overview]);
  const candidateEpisodeCount = useMemo(
    () => countCandidateEpisodes(overview?.series ?? []),
    [overview],
  );
  const sensorLabel = useMemo(() => {
    const sensors = [...new Set(overview?.series?.map((series) => series.sensorId) ?? [])]
      .sort()
      .map((sensorId) => sensorId.toUpperCase());
    return sensors.join(sensors.length === 2 ? " e " : ", ");
  }, [overview]);
  const causalWindowCount = modelSummaries.reduce(
    (total, model) => total + model.windowCount,
    0,
  );

  if (overview?.materialization?.state !== "materialized" || points.length === 0) {
    const noActiveBatch = overview?.materialization?.state === "no_active_historical_batch";
    const materializedFilterEmpty = overview?.materialization?.state === "materialized";
    return (
      <section className="assessment-trend" data-testid="assessment-trend" aria-labelledby="assessment-trend-title">
        <div className="timeline-section-heading">
          <div>
            <p className="eyebrow">{"Evid\u00eancia de modelo persistida"}</p>
            <h3 id="assessment-trend-title">{"Scores hist\u00f3ricos relativos"}</h3>
          </div>
        </div>
        <p className="timeline-empty">
          {noActiveBatch
            ? "Nenhum lote hist\u00f3rico ativo est\u00e1 dispon\u00edvel. Nenhum score foi inferido nem preenchido com zero."
            : materializedFilterEmpty ? FILTER_EMPTY_COPY : EMPTY_COPY}
        </p>
      </section>
    );
  }

  return (
    <section className="assessment-trend" data-testid="assessment-trend" aria-labelledby="assessment-trend-title">
      <div className="timeline-section-heading">
        <div>
          <p className="eyebrow">{"Evid\u00eancia de modelo persistida"}</p>
          <h3 id="assessment-trend-title">{"Resumo dos scores hist\u00f3ricos"}</h3>
        </div>
        <p>{overview.aggregationSummary.returnedAssessmentCount} {"avalia\u00e7\u00f5es no recorte"}</p>
      </div>

      <p className="model-disclaimer">{SCALE_COPY}</p>
      <ul aria-label={"Resumo da evid\u00eancia persistida"} className="assessment-trend__summary">
        <li>
          <span>{"Avalia\u00e7\u00f5es"}</span>
          <strong>
            {overview.aggregationSummary.returnedAssessmentCount} de {overview.aggregationSummary.originalAssessmentCount}
          </strong>
          <small>exibidas no recorte</small>
        </li>
        <li>
          <span>{"Epis\u00f3dios candidatos"}</span>
          <strong>
            {candidateEpisodeCount} {candidateEpisodeCount === 1 ? "n\u00e3o confirmado" : "n\u00e3o confirmados"}
          </strong>
          <small>{"revis\u00e3o humana obrigat\u00f3ria"}</small>
        </li>
        <li>
          <span>Sensores</span>
          <strong>{sensorLabel}</strong>
          <small>{"s\u00e9ries mantidas separadas"}</small>
        </li>
        <li>
          <span>Treinamento</span>
          <strong>{causalWindowCount} {causalWindowCount === 1 ? "janela causal" : "janelas causais"}</strong>
          <small>sem aprendizado online</small>
        </li>
      </ul>
      {candidateEpisodeCount > 0 ? <p className="timeline-inline-warning">{CANDIDATE_COPY}</p> : null}
      <ul className="assessment-trend__models" aria-label={"Modelos causais das s\u00e9ries exibidas"}>
        {modelSummaries.map((model) => (
          <li key={model.key}>
            Modelo {model.modelFamily} {model.modelVersion}{" \u00b7 "}
            {model.windowCount === 1 ? (
              <>
                1 janela causal{" \u00b7 treinamento causal encerrado em "}
                <time dateTime={model.firstTrainingEnd}>{model.firstTrainingEnd}</time>
              </>
            ) : (
              <>
                {model.windowCount} janelas causais{" \u00b7 cortes de treinamento de "}
                <time dateTime={model.firstTrainingEnd}>{model.firstTrainingEnd}</time>
                {" a "}
                <time dateTime={model.lastTrainingEnd}>{model.lastTrainingEnd}</time>
              </>
            )}
            {" \u00b7 hash "}<code>{model.modelHash}</code>.
          </li>
        ))}
      </ul>
      <p className="model-meta">{LABELS_COPY}</p>
      <p className="model-meta">{VALIDATION_COPY}</p>
    </section>
  );
}
