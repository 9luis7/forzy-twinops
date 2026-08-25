import React, { useMemo } from "react";
import OriginalSamplesTable from "./OriginalSamplesTable.jsx";
import TimelineOverview from "./TimelineOverview.jsx";
import { buildTimelineViewModel } from "./timelineViewModel.js";

export default function TimelineWorkspace({
  overview,
  page,
  context,
  loading,
  errors,
  pendingSelection,
  selectTimelinePoint,
  commitAnnouncement = null,
  children,
}) {
  const model = useMemo(
    () => overview === null ? null : buildTimelineViewModel(overview),
    [overview],
  );
  const selectedPointId = context?.anchor?.pointId ?? null;
  const aggregation = overview?.aggregationSummary ?? null;

  return (
    <section className="timeline-workspace" data-testid="timeline-workspace" aria-labelledby="timeline-title">
      <div className="timeline-workspace__heading">
        <div>
          <p className="eyebrow">Histórico operacional</p>
          <h2 id="timeline-title">Linha temporal original</h2>
        </div>
        {aggregation === null ? null : (
          <p className="timeline-aggregation">
            <strong>{aggregation.returnedPointCount}</strong> de {aggregation.originalPointCount} pontos · {aggregation.reducedSeriesCount} séries reduzidas
          </p>
        )}
      </div>

      {loading.overview ? (
        <p className="timeline-inline-status" role="status">
          {overview === null ? "Carregando cobertura histórica…" : "Atualizando a cobertura; a última linha válida continua visível."}
        </p>
      ) : null}
      {errors.overview ? (
        <p className="timeline-inline-warning" role="alert">
          {overview === null
            ? "A cobertura histórica está indisponível para esta consulta."
            : "A cobertura não pôde ser atualizada. A última linha válida continua visível."}
        </p>
      ) : null}
      {model === null && !loading.overview && !errors.overview ? (
        <p className="timeline-empty">Cobertura histórica indisponível para esta consulta.</p>
      ) : null}
      {model === null ? null : <TimelineOverview model={model} />}

      {errors.context ? (
        <p className="timeline-inline-warning" role="alert">
          {context === null
            ? "O ponto não pôde ser sincronizado. O contexto Agora continua visível."
            : "O ponto não pôde ser sincronizado. O último contexto histórico válido continua visível."}
        </p>
      ) : null}

      {commitAnnouncement === null ? null : (
        <p
          aria-atomic="true"
          aria-live="polite"
          className="visually-hidden timeline-context-commit-status"
          role="status"
        >
          {commitAnnouncement}
        </p>
      )}

      {children}

      <OriginalSamplesTable
        error={errors.page}
        loading={loading.page}
        page={page}
        pendingSelection={pendingSelection}
        selectedPointId={selectedPointId}
        selectTimelinePoint={selectTimelinePoint}
      />
    </section>
  );
}
