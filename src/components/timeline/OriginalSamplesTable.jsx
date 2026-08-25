import React, { useCallback } from "react";

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  dateStyle: "short",
  timeStyle: "medium",
});
const numberFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const sourceLabels = {
  historical_archive: "Arquivo histórico",
  live_collection: "Coleta ao vivo",
};

function formatMeasurement(point) {
  const measurement = point.measurements.vibrationVelocityRms;
  return measurement === null
    ? "Indisponível"
    : `${numberFormatter.format(measurement.value)} ${measurement.unit}`;
}

export default function OriginalSamplesTable({
  page,
  loading,
  error,
  pendingSelection,
  selectedPointId,
  selectTimelinePoint,
}) {
  const handleSelect = useCallback((event) => {
    if (event.currentTarget.getAttribute("aria-disabled") === "true") return;
    void selectTimelinePoint(event.currentTarget.dataset.pointId);
  }, [selectTimelinePoint]);

  if (page === null && loading) {
    return <p className="timeline-inline-status" role="status">Carregando pontos originais…</p>;
  }
  if (page === null && error) {
    return <p className="timeline-inline-warning" role="alert">Os pontos originais estão indisponíveis.</p>;
  }
  if (page === null || page.items.length === 0) {
    return <p className="timeline-empty">Nenhum ponto original foi retornado para este período.</p>;
  }

  return (
    <div className="timeline-samples">
      <div className="timeline-section-heading">
        <div>
          <p className="eyebrow">Leituras persistidas</p>
          <h3>Pontos originais</h3>
        </div>
        <p>
          {page.items.length} pontos nesta página{page.hasMore ? " · há mais pontos na consulta" : ""}.
          {" "}Selecione uma leitura para sincronizar todo o contexto.
        </p>
      </div>
      {loading ? (
        <p className="timeline-inline-status" role="status">
          Atualizando os pontos; a última lista válida continua visível.
        </p>
      ) : null}
      {error ? (
        <p className="timeline-inline-warning" role="alert">
          A atualização da lista falhou. Os últimos pontos válidos continuam visíveis.
        </p>
      ) : null}
      <div className="timeline-table-scroll">
        <table>
          <caption className="visually-hidden">Pontos originais disponíveis para inspeção histórica</caption>
          <thead>
            <tr>
              <th scope="col">Instante</th>
              <th scope="col">Canal</th>
              <th scope="col">Velocidade RMS</th>
              <th scope="col">Origem</th>
              <th scope="col">Ação</th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((point) => {
              const selected = point.pointId === selectedPointId;
              const pending = point.pointId === pendingSelection?.pointId;
              return (
                <tr data-selected={selected ? "true" : "false"} key={point.pointId}>
                  <td data-label="Instante">
                    <time dateTime={point.eventAt}>{dateTimeFormatter.format(new Date(point.eventAt))}</time>
                  </td>
                  <td data-label="Canal">{point.sensorId.toUpperCase()}</td>
                  <td data-label="Velocidade RMS">{formatMeasurement(point)}</td>
                  <td data-label="Origem">{sourceLabels[point.sourceKind] ?? "Indisponível"}</td>
                  <td data-label="Ação">
                    <button
                      aria-busy={pending}
                      aria-disabled={pending}
                      aria-pressed={selected}
                      className="timeline-point-action"
                      data-point-id={point.pointId}
                      onClick={handleSelect}
                      type="button"
                    >
                      {pending ? "Sincronizando…" : "Inspecionar ponto"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
