import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Twin3D from "../components/Twin3D.jsx";
import DemoTrends, { METRICS } from "../demo/DemoTrends.jsx";
import { HistoryGatewayError } from "./GatewayHistoryDataSource.js";
import HistoricalCopilot from "./HistoricalCopilot.jsx";
import { formatDateTime } from "../lib/displayTime.js";
import "./history.css";

const labels = { normal: "Sem desvio relevante", watch: "Atenção", alert: "Alerta relativo", insufficient_data: "Dados insuficientes", unknown: "Sem avaliação disponível" };
const number = (value) => Number.isFinite(value) ? value.toLocaleString("pt-BR", { maximumFractionDigits: 3 }) : "Indisponível";
const date = (value) => formatDateTime(value, "Não informado");
const emptyDraft = { datasetId: "", from: "", to: "", sensor: "all" };

export function brasiliaInputToIso(value) {
  if (!value) return null;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?$/.test(value)) throw new Error("Informe uma data e hora válidas.");
  const normalized = value.replace(/\.0+$/, "");
  const iso = `${normalized.length === 16 ? `${normalized}:00` : normalized}-03:00`;
  const instant = new Date(iso);
  if (!Number.isFinite(instant.getTime()) || new Date(instant.getTime() - 3 * 3600000).toISOString().slice(0, 19) !== iso.slice(0, 19)) {
    throw new Error("Informe uma data e hora válidas.");
  }
  return iso;
}

function HistoricalSensor({ id, sensor, selected, onSelect }) {
  const assessment = sensor.assessment?.assessment;
  return <article className="historical-sensor" data-sensor={id} data-selected={selected === id}>
    <button className="historical-sensor-heading" aria-pressed={selected === id} onClick={() => onSelect(selected === id ? "all" : id)}>
      <span className="historical-sensor-dot" aria-hidden="true" />{id.toUpperCase()} · {id === "s1" ? "Motor" : "Bomba"}
    </button>
    <p className="historical-condition" data-status={assessment?.status ?? "unknown"}>{labels[assessment?.status ?? "unknown"]}</p>
    <dl className="historical-values">{METRICS.map((metric) => <div key={metric.key}><dt>{metric.label}</dt><dd>{number(sensor.latest?.measurements[metric.key]?.value)} <small>{metric.unit}</small></dd></div>)}</dl>
    <p className="historical-note">Persistência: {number(assessment?.persistenceSeconds)} s</p>
    <details><summary>Detalhes da avaliação de {id.toUpperCase()}</summary>
      <p>Score relativo: {number(assessment?.anomalyScore)} · Deterioração relativa: {number(assessment?.deteriorationScore)}</p>
      {sensor.assessment?.model && <p>Modelo {sensor.assessment.model.name} · {sensor.assessment.model.version}</p>}
      {sensor.assessment?.model?.trainedUntil && <p>Treinado com dados até {date(sensor.assessment.model.trainedUntil)} · São Paulo</p>}
      {sensor.assessment?.evidence?.length > 0 && <ul>{sensor.assessment.evidence.map((evidence) => <li key={evidence.id}>{evidence.feature}: {number(evidence.value)} {evidence.unit}</li>)}</ul>}
    </details>
  </article>;
}

export default function HistoricalWorkspace({ dataSource, compact = false, liveUnavailable = false, Twin3DComponent = Twin3D }) {
  const [datasets, setDatasets] = useState([]), [context, setContext] = useState(null);
  const [draft, setDraft] = useState(emptyDraft), [applied, setApplied] = useState(null), [selected, setSelected] = useState("all");
  const [busy, setBusy] = useState(true), [error, setError] = useState(null), [catalogueLoaded, setCatalogueLoaded] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const sequence = useRef(0), pending = useRef(null), retry = useRef(null);
  const titleId = compact ? "historical-overview-title" : "historical-workspace-title";

  const loadContext = useCallback(async (query) => {
    const version = ++sequence.current;
    pending.current?.abort();
    const controller = new AbortController(); pending.current = controller; retry.current = query;
    setBusy(true); setError(null);
    try {
      const result = await dataSource.context(query.datasetId, { from: query.from, to: query.to, endRow: query.endRow ?? null, limit: 300 }, { signal: controller.signal });
      if (version !== sequence.current) return;
      setContext(result); setApplied(query); setSelected(query.sensor);
    } catch (failure) {
      if (version !== sequence.current || failure.name === "AbortError") return;
      setError(failure instanceof HistoryGatewayError ? failure.message : "Não foi possível consultar o histórico. Tente novamente.");
    } finally { if (version === sequence.current) setBusy(false); }
  }, [dataSource]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    sequence.current += 1; pending.current?.abort();
    setDatasets([]); setContext(null); setApplied(null); setDraft(emptyDraft); setBusy(true); setError(null); setCatalogueLoaded(false); retry.current = null;
    dataSource.datasets({ signal: controller.signal }).then((catalogue) => {
      if (!active) return;
      setDatasets(catalogue); setCatalogueLoaded(true);
      if (!catalogue.length) { setBusy(false); return; }
      setDraft({ ...emptyDraft, datasetId: catalogue[0].datasetId });
      loadContext({ datasetId: catalogue[0].datasetId, from: null, to: null, sensor: "all" });
    }).catch((failure) => {
      if (!active || failure.name === "AbortError") return;
      setBusy(false); setError(failure instanceof HistoryGatewayError ? failure.message : "Não foi possível carregar os conjuntos históricos.");
    });
    return () => { active = false; controller.abort(); pending.current?.abort(); sequence.current += 1; };
  }, [dataSource, loadContext]);

  const apply = (event) => {
    event.preventDefault();
    try {
      const from = brasiliaInputToIso(draft.from), to = brasiliaInputToIso(draft.to);
      if (from && to && Date.parse(from) > Date.parse(to)) throw new Error("O início deve ser anterior ou igual ao fim do período.");
      loadContext({ datasetId: draft.datasetId, from, to, sensor: draft.sensor });
    } catch (failure) { setError(failure.message); }
  };
  const selectSensor = (sensor) => { setSelected(sensor); setDraft((current) => ({ ...current, sensor })); };
  const rows = useMemo(() => {
    const grouped = new Map();
    context?.history.forEach((frame) => {
      if (!grouped.has(frame.sourceRow)) grouped.set(frame.sourceRow, { row: frame.sourceRow, observedAt: frame.observedAt });
      grouped.get(frame.sourceRow)[frame.sensorId] = frame;
    });
    return [...grouped.values()];
  }, [context]);
  const navigate = (endRow) => loadContext({ ...applied, sensor: selected, endRow });

  return <section className={`historical-workspace ${compact ? "historical-workspace--compact" : ""}${copilotOpen && context ? " has-copilot-open" : ""}`} aria-labelledby={titleId} aria-busy={busy}>
    <header className="historical-header"><div>{!compact && <p className="eyebrow">Dados reais preservados</p>}<h2 id={titleId}>{compact ? "Últimos dados disponíveis" : "Histórico do equipamento"}</h2>{!compact && <p>Consulte os registros do equipamento e sua avaliação no instante selecionado.</p>}</div>{compact && <a className="historical-link" href="/history">Consultar histórico →</a>}</header>
    {liveUnavailable && <p className="historical-notice" role="status">A coleta atual está indisponível. Os registros históricos continuam disponíveis para consulta.</p>}
    {!compact && datasets.length > 0 && <form className="historical-filters panel" onSubmit={apply} aria-label="Filtros do histórico">
      <label>Conjunto histórico<select value={draft.datasetId} onChange={(event) => setDraft({ ...draft, datasetId: event.target.value })}>{datasets.map((dataset) => <option value={dataset.datasetId} key={dataset.datasetId}>{dataset.label}</option>)}</select></label>
      <label>Início — São Paulo<input type="datetime-local" step="1" value={draft.from} onChange={(event) => setDraft({ ...draft, from: event.target.value })} /></label>
      <label>Fim — São Paulo<input type="datetime-local" step="1" value={draft.to} onChange={(event) => setDraft({ ...draft, to: event.target.value })} /></label>
      <label>Sensor<select value={draft.sensor} onChange={(event) => setDraft({ ...draft, sensor: event.target.value })}><option value="all">Todos os sensores</option><option value="s1">S1 · Motor</option><option value="s2">S2 · Bomba</option></select></label>
      <button type="submit">Aplicar filtros</button>
    </form>}
    {busy && <p role="status">Consultando registros históricos…{context ? " A última seleção válida permanece abaixo até a nova consulta terminar." : ""}</p>}
    {error && <div className="historical-notice" role="alert"><p>{error}{context ? " A seleção anterior continua exibida; o novo período não foi aplicado." : ""}</p>{retry.current && <button className="secondary-button" disabled={busy} onClick={() => loadContext(retry.current)}>Tentar novamente</button>}{!catalogueLoaded && <button className="secondary-button" onClick={() => window.location.reload()}>Recarregar histórico</button>}</div>}
    {catalogueLoaded && datasets.length === 0 && <p className="empty-state">Nenhum conjunto histórico está disponível para consulta.</p>}
    {context && <div className="historical-applied" data-revision={context.revision}>
      <section className="panel historical-selection" aria-label="Seleção histórica exibida">
        <p className="eyebrow">Fonte histórica · {context.dataset.label}</p>
        <h3>Instante consultado: <time dateTime={context.selection.observedAt}>{date(context.selection.observedAt)}</time> · São Paulo</h3>
        {!compact && <p>Último registro do conjunto: {date(context.dataset.endAt)} · São Paulo</p>}
        {!compact && <p>Período aplicado: {applied.from ? date(applied.from) : "Início do conjunto"} — {applied.to ? date(applied.to) : "Fim do conjunto"} · São Paulo<br />{context.selection.returnedPairs} pares exibidos de {context.selection.totalPairs} encontrados no período.</p>}
        <p className="historical-note">{compact ? "Análise retrospectiva · score relativo, não probabilidade de falha. Validação humana obrigatória." : "Avaliação retrospectiva, relativa ao histórico; não representa probabilidade de falha. Validação humana obrigatória."}</p>
      </section>
      <div className="historical-twin-grid">
        <section className="panel historical-twin"><div className="panel-heading"><h3>Equipamento neste instante</h3><span className="historical-condition" data-status={context.status}>{labels[context.status]}</span></div><Twin3DComponent snapshot={context} selectedSensor={selected} onSelectSensor={selectSensor} /><p className="historical-note">S1 no motor e S2 na bomba, junto ao acoplamento: vínculos e posições assumidos, sem validação física.</p></section>
        <aside className="historical-sensors" aria-label="Sensores no instante consultado">{["s1", "s2"].map((id) => <HistoricalSensor id={id} key={id} sensor={context.sensors[id]} selected={selected} onSelect={selectSensor} />)}</aside>
      </div>
      <DemoTrends context={context} selected={selected} onSelect={selectSensor} />
      {!compact && <section className="panel historical-records" aria-label="Registros do período">
        <div className="historical-records-heading"><h3>Leituras do período</h3><div className="historical-pagination"><button className="secondary-button" disabled={busy || !context.selection.hasPrevious} onClick={() => navigate(context.selection.previousEndRow)}>Anterior</button><button className="secondary-button" disabled={busy || !context.selection.hasNext} onClick={() => navigate(context.selection.nextEndRow)}>Próximo</button></div></div>
        <div className="historical-table-scroll"><table><caption>Vibração RMS em mm/s · Horário de São Paulo</caption><thead><tr><th scope="col">Data e hora</th>{selected !== "s2" && <th scope="col">S1 · Motor</th>}{selected !== "s1" && <th scope="col">S2 · Bomba</th>}<th scope="col">Consulta</th></tr></thead><tbody>{rows.map((row) => <tr key={row.row} aria-current={row.row === context.selection.endRow ? "true" : undefined}><th scope="row"><time dateTime={row.observedAt}>{date(row.observedAt)}</time></th>{selected !== "s2" && <td>{number(row.s1?.measurements.vibrationVelocityRms?.value)}</td>}{selected !== "s1" && <td>{number(row.s2?.measurements.vibrationVelocityRms?.value)}</td>}<td><button className="secondary-button" disabled={busy || row.row === context.selection.endRow} onClick={() => navigate(row.row)} aria-label={`Analisar instante ${date(row.observedAt)}, registro ${row.row}`}>{row.row === context.selection.endRow ? "Instante exibido" : "Analisar este instante"}</button></td></tr>)}</tbody></table></div>
      </section>}
      <details className="historical-provenance"><summary>Detalhes da fonte e da avaliação</summary><p>{context.dataset.pairCount} pares / {context.dataset.readingCount} leituras · Formato {context.dataset.sourceFormat}</p><p>Período do conjunto: {date(context.dataset.startAt)} — {date(context.dataset.endAt)} · São Paulo</p><p>Revisão: <code>{context.revision}</code> · Registro {context.selection.endRow}</p><p>Aceleração exibida nos gráficos, sem participação no score. A consulta mantém a ordem, as repetições e as lacunas dos registros originais.</p></details>
    </div>}
    {context && <HistoricalCopilot context={context} dataSource={dataSource} open={copilotOpen} onOpenChange={setCopilotOpen} />}
  </section>;
}
