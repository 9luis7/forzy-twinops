import React, { useEffect, useRef, useState } from "react";
import Twin3D from "../components/Twin3D.jsx";
import CopilotDock from "../components/assistant/CopilotDock.jsx";
import { useDemoReplay } from "./useDemoReplay.js";
import DemoTrends, { clockLabel, METRICS } from "./DemoTrends.jsx";
import "./demo.css";

export const STATUS_LABELS = { normal: "Sem desvio relevante", watch: "Atenção", alert: "Alerta relativo", insufficient_data: "Dados insuficientes", unknown: "Aguardando avaliação" };
const fmt = (v) => Number.isFinite(v) ? v.toLocaleString("pt-BR", { maximumFractionDigits: 3 }) : "—";
const fullClock = (v) => v ? `${new Date(v).toLocaleString("pt-BR", { timeZone: "UTC" })} UTC` : "Aguardando primeiro par";
const EVENT_LABELS = { sustained_watch: "Atenção sustentada", escalation: "Escalada para alerta", recovery: "Recuperação sustentada" };
const EVENT_STATES = { pending: "Na fila", processing: "Consultando manual", ready: "Recomendação disponível", degraded: "Resposta limitada" };

function EventStatus({ event, recommendationPending }) {
  const awaiting = !["ready", "degraded"].includes(event.status)
    && recommendationPending?.eventId === event.eventId
    && recommendationPending.generation === event.generation;
  return <span className="small muted" role="status" title={awaiting ? "Consulta enviada; aguardando resposta do serviço." : undefined}>
    {awaiting ? "Consultando manual" : EVENT_STATES[event.status]}
  </span>;
}

function Answer({ response }) {
  return <div className="demo-answer">
    <p><strong>Leitura operacional</strong><br />{response.answer.currentState}</p>
    <p><strong>Orientação documental</strong><br />{response.answer.manual}</p>
    <ul className="demo-citations">{response.citations.map((citation, i) => <li key={`${citation.type}-${i}`}>
      {citation.type === "manual" ? <><a href={citation.sourceUrl} target="_blank" rel="noreferrer">{citation.manufacturer} · {citation.equipmentModel} · p. {citation.pageStart}–{citation.pageEnd}</a><p>{citation.excerpt}</p></>
        : <span>Evidência: {citation.feature} = {fmt(citation.value)} {citation.unit} · janela {clockLabel(citation.windowStart)}–{clockLabel(citation.windowEnd)} UTC</span>}
    </li>)}</ul>
    {response.limitations.map((limitation, index) => <p className="muted small" key={index}>{limitation}</p>)}
    <p className="muted small">{response.fallbackUsed ? "Resposta de contingência · " : ""}Validação humana obrigatória. Manual do motor WEG; cobertura da bomba não afirmada.</p>
  </div>;
}

function SensorSummary({ id, sensor, selected, onSelect }) {
  const assessment = sensor.assessment?.assessment;
  return <article className={`demo-sensor ${selected === id ? "is-selected" : ""}`} data-status={assessment?.status ?? "unknown"}>
    <button className="demo-sensor-heading" onClick={() => onSelect(selected === id ? "all" : id)} aria-pressed={selected === id}>
      <span><span className={`demo-dot ${id}`} />{id.toUpperCase()} · {id === "s1" ? "Motor" : "Bomba"}</span><span>↗</span>
    </button>
    <p className="small muted">Junto ao acoplamento · posição assumida</p>
    <strong className="demo-status">{STATUS_LABELS[assessment?.status ?? "unknown"]}</strong>
    <dl className="demo-values">{METRICS.map((m) => <div key={m.key}><dt>{m.label}</dt><dd>{fmt(sensor.latest?.measurements[m.key]?.value)} <small>{m.unit}</small></dd></div>)}</dl>
    <div className="demo-score"><span>Score relativo</span><strong>{fmt(assessment?.anomalyScore)}</strong></div>
    <p className="small muted">Persistência {fmt(assessment?.persistenceSeconds)} s · {sensor.assessmentState === "reused" ? "avaliação reaproveitada" : sensor.assessmentState === "computed" ? "avaliação calculada" : "avaliação indisponível"}</p>
    {sensor.assessment?.evidence?.length > 0 && <details><summary>Evidências do sensor</summary><ul>{sensor.assessment.evidence.map((e) => <li key={e.id}>{e.feature}: {fmt(e.value)} {e.unit}</li>)}</ul></details>}
  </article>;
}

export default function DemoDashboard({ dataSource }) {
  const state = useDemoReplay(dataSource);
  const { context, controller, datasets, busy, error, events } = state;
  const [scenario, setScenario] = useState("guided"), [datasetId, setDatasetId] = useState("");
  const [selected, setSelected] = useState("all"), [question, setQuestion] = useState("");
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [eventSelection, setEventSelection] = useState(null);
  const eventAnswerRef = useRef(null);
  const manualAnswerRef = useRef(null);
  const questionRef = useRef(null);
  const copilotOpenRef = useRef(copilotOpen);
  copilotOpenRef.current = copilotOpen;
  const replay = context?.replay;
  const selectedEvent = eventSelection && eventSelection.runId === replay?.runId
    && eventSelection?.generation === replay?.generation
    ? events.find((item) => item.eventId === eventSelection.eventId && item.recommendation)
    : null;
  const readyCount = events.filter((item) => item.recommendation && ["ready", "degraded"].includes(item.status)).length;
  useEffect(() => {
    setEventSelection(null);
    setQuestion("");
    setSelected("all");
  }, [controller, replay?.runId, replay?.generation]);
  useEffect(() => {
    if (copilotOpen && selectedEvent) eventAnswerRef.current?.focus();
  }, [copilotOpen, selectedEvent?.eventId]);
  useEffect(() => {
    if (state.answers.length && copilotOpenRef.current) manualAnswerRef.current?.focus();
  }, [state.answers.length]);
  const openEvent = (item) => {
    setEventSelection({ runId: replay.runId, generation: replay.generation, eventId: item.eventId });
    setCopilotOpen(true);
    if (copilotOpen && selectedEvent?.eventId === item.eventId) eventAnswerRef.current?.focus();
  };
  const running = replay?.state === "running" && !state.suspended;
  const canInterrupt = state.pendingOperation === "advance" && !state.queuedAction;
  const controlBusy = Boolean(state.queuedAction) || (busy && !canInterrupt);
  const toggle = () => controller.command(running ? "pause" : replay?.cursor === 0 ? "play" : "resume");
  const keyboard = (event) => {
    // React events bubble through the portal owner even though the chat is
    // outside this main in the DOM. Chat reading must never control playback.
    if (!event.currentTarget.contains(event.target)) return;
    if (["INPUT", "SELECT", "TEXTAREA", "BUTTON", "A", "SUMMARY"].includes(event.target.tagName) || event.ctrlKey || event.metaKey || event.altKey || controlBusy || !context) return;
    if (event.code === "Space" && replay.state !== "completed") { event.preventDefault(); toggle(); }
    if (event.code === "ArrowRight" && !busy && replay.state === "paused") { event.preventDefault(); controller.command("step"); }
  };
  return <main className={`demo-shell${copilotOpen ? " has-copilot-open" : ""}`} onKeyDown={keyboard} tabIndex={0} aria-label="Painel de replay, Espaço para reproduzir ou pausar e seta direita para um par">
    <header className="demo-header"><div><p className="eyebrow">FORZY TWINOPS <span className="demo-mode">DEMONSTRAÇÃO</span></p><h1>Reprodução do histórico</h1><p className="muted">Dados reais chegando em sequência para demonstrar o sistema. As medições são históricas, não uma coleta ao vivo.</p></div><a className="demo-live-link" href="/">Voltar à visão geral</a></header>
    <section className="panel demo-controls" aria-label="Controles do replay">
      <div className="demo-session"><label>Conjunto histórico<select value={datasetId || datasets[0]?.datasetId || ""} onChange={(e) => setDatasetId(e.target.value)} disabled={busy || state.loading}>{datasets.length ? datasets.map((d) => <option key={d.datasetId} value={d.datasetId}>{d.label}</option>) : <option value="">Carregando conjuntos disponíveis</option>}</select></label>
        <label>Roteiro<select value={scenario} onChange={(e) => setScenario(e.target.value)} disabled={busy}><option value="guided">Guiado · 300 pares</option><option value="full">Livre · histórico completo</option></select></label>
        <button className="secondary-button" disabled={busy || !datasets.length || state.loading} onClick={() => controller.create(datasetId || datasets[0].datasetId, scenario)}>{context ? "Nova sessão" : "Preparar replay"}</button>
      </div>
      {state.loading && <p role="status">Carregando histórico e sessão…</p>}
      {context && <>
        <div className="demo-playback"><button disabled={controlBusy || replay.state === "completed" || Boolean(error)} onClick={toggle}>{state.queuedAction === "pause" ? "Pausa solicitada…" : running ? "Ⅱ Pausar" : "▶ Continuar"}</button>
          <button className="secondary-button" disabled={busy || replay.state !== "paused" || Boolean(error)} onClick={() => controller.command("step")}>Avançar 1 par</button>
          <button className="secondary-button" disabled={controlBusy} onClick={() => controller.command("restart")}>{state.queuedAction === "restart" ? "Reinício solicitado…" : "Reiniciar"}</button>
          <label>Ritmo<select value={replay.speed} disabled={busy} onChange={(e) => controller.command("speed", Number(e.target.value))}>{[1, 2, 5].map((speed) => <option key={speed} value={speed}>{speed} {speed === 1 ? "par" : "pares"}/s</option>)}</select></label>
          <span className="demo-progress-label">{replay.cursor} / {replay.totalPairs} pares · {replay.state === "completed" ? "Concluído" : running ? "Reproduzindo" : "Pausado"}</span>
        </div>
        <progress value={replay.cursor} max={replay.totalPairs} aria-label="Progresso do replay" />
        <div className="demo-clock-row"><span>Medição histórica <strong>{fullClock(replay.sourceTime)}</strong></span><span>Chegada na reprodução <strong>{fullClock(replay.arrivalTime)}</strong></span></div>
        <p className="small muted">Fonte: {context.dataset.label}. Espaço: reproduzir/pausar · →: um par, com o painel em foco.</p>
      </>}
      {state.queuedAction && <p role="status" className="demo-notice">{state.queuedAction === "pause" ? "Pausa" : "Reinício"} solicitado. Aguardando a confirmação do avanço em curso; novos avanços estão suspensos.</p>}
      {state.suspended && context && !state.queuedAction && <p role="status" className="demo-notice">Replay suspenso. Use Continuar para retomar a reprodução.</p>}
      {error && <div role="alert" className="demo-notice"><p>{error}</p><button className="secondary-button" disabled={busy} onClick={() => controller.refresh()}>Reconectar</button></div>}
    </section>
    {!context ? <section className="demo-welcome panel"><p className="eyebrow">Uma demonstração orientada por evidências</p><h2>Prepare o replay para acompanhar o conjunto.</h2><p>O roteiro guiado percorre as linhas 141–440 do histórico. Cada avanço preserva os dois canais, as repetições e as lacunas originais.</p><div className="demo-flow"><span>01 · Sensores</span><span>02 · Histórico</span><span>03 · Avaliação</span><span>04 · Orientação</span></div><img src="/models/conjunto-motor-bomba-preview.png" alt="Conjunto CAD de motor, acoplamento e bomba utilizado na demonstração" /></section> : <>
      <div className="demo-twin-grid" data-revision={context.revision}>
        <section className="panel demo-twin"><div className="panel-heading"><div><p className="eyebrow">Conjunto motor + bomba</p><h2>Gêmeo operacional</h2></div><span className="demo-state-chip" data-status={context.status}>{STATUS_LABELS[context.status]}</span></div><Twin3D snapshot={context} selectedSensor={selected} onSelectSensor={setSelected} /><p className="muted small">S1 no motor e S2 na bomba, junto ao acoplamento. Posições assumidas para demonstração, não validadas fisicamente. Sem simulação mecânica.</p></section>
        <aside className="demo-sensors" aria-label="Avaliações por sensor">{["s1", "s2"].map((id) => <SensorSummary key={id} id={id} sensor={context.sensors[id]} selected={selected} onSelect={setSelected} />)}</aside>
      </div>
      <DemoTrends context={context} selected={selected} onSelect={setSelected} />
      <div className="demo-bottom-grid">
        <section className="panel demo-events"><p className="eyebrow">Episódios preservados</p><h2>Eventos e recomendações</h2><p className="muted small">Cada resposta pertence ao contexto congelado do evento, mesmo quando o replay avança.</p>
          {!events.length && <p className="empty-state">Nenhum episódio sustentado neste prefixo do histórico.</p>}
          <ol>{[...events].reverse().map((event) => <li key={event.eventId} className="demo-event"><div className="demo-event-title"><strong>{EVENT_LABELS[event.kind]}</strong><EventStatus event={event} recommendationPending={state.recommendationPending} /></div><p className="muted small">{event.sensorIds.map((id) => id.toUpperCase()).join(" + ")} · {fullClock(event.observedAt)}</p>{event.recommendation && <button className="secondary-button" onClick={() => openEvent(event)} aria-label={`Ver orientação: ${EVENT_LABELS[event.kind]} · ${event.sensorIds.map((id) => id.toUpperCase()).join(" + ")}`}>Ver orientação</button>}{event.errorCode && <p className="small muted">{event.retryable ? "Aguardando nova tentativa." : "Geração concluída com limitação."}</p>}</li>)}</ol>
        </section>
      </div>
      <p className="demo-disclaimer">Score relativo ao histórico de referência. Não representa probabilidade de falha nem comprovação de antecipação fora da amostra. Aceleração não participa do score.</p>
      <details className="panel demo-provenance"><summary>Detalhes do processamento e da origem</summary><dl className="demo-pipeline">{[["Pares recebidos", context.pipeline.receivedPairs], ["Leituras recebidas", context.pipeline.receivedReadings], ["Leituras novas", context.pipeline.newInformationReadings], ["Repetições", context.pipeline.repeatedReadings], ["Lacunas", context.pipeline.gapCount], ["Avaliações", context.pipeline.assessmentsComputed], ["Eventos", context.pipeline.eventsCreated], ["Último avanço (ms)", context.pipeline.lastAdvanceMs]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{fmt(value)}</dd></div>)}</dl><p className="muted small">Revisão {context.revision} · {replay.warmupPairs} pares precarregados para aquecimento.<br />{context.dataset.label} · {context.dataset.pairCount} pares / {context.dataset.readingCount} leituras · {context.dataset.sourceFormat}<br />Período: {fullClock(context.dataset.startAt)} — {fullClock(context.dataset.endAt)}<br />SHA-256: <code>{context.dataset.sourceHash}</code></p></details>
    </>}
    <CopilotDock open={copilotOpen} onOpenChange={setCopilotOpen} notificationCount={readyCount} contextLabel={replay?.sourceTime ? `Demonstração · medição histórica de ${fullClock(replay.sourceTime)}` : "Demonstração · aguardando uma leitura do histórico"}>
      <section className="demo-copilot demo-assistant" aria-label="Copiloto da demonstração">
        {selectedEvent && <article className="demo-event-answer" ref={eventAnswerRef} tabIndex={-1} aria-label="Orientação do evento selecionado">
          <p className="eyebrow">Orientação já produzida</p><h3>{EVENT_LABELS[selectedEvent.kind]}</h3>
          <p className="muted small">{selectedEvent.sensorIds.map((id) => id.toUpperCase()).join(" + ")} · {fullClock(selectedEvent.observedAt)}. Contexto fixado no evento; a reprodução pode continuar.</p>
          <Answer response={selectedEvent.recommendation} />
          <details className="assistant-technical-details"><summary>Detalhes do contexto do evento</summary><p>Linha {selectedEvent.sourceRow} · revisão {selectedEvent.contextRevision}</p></details>
          <button className="button-secondary" onClick={() => { setEventSelection(null); questionRef.current?.focus(); }}>Fechar orientação do evento</button>
        </article>}
        <p className="eyebrow">Manual do motor WEG</p><h2>Pergunte sobre este instante</h2><p className="muted small">Cada pergunta usa o instante exibido ao enviar. Pause a reprodução para explorar o mesmo instante. O manual não cobre a bomba.</p>
        {!replay?.sourceRow && <p className="assistant-unavailable" role="status">Prepare a reprodução e avance uma leitura para consultar o copiloto.</p>}
        <form className="assistant-form" aria-label="Perguntar ao copiloto da demonstração" onSubmit={(e) => { e.preventDefault(); if (question.trim() && replay?.sourceRow && !state.manualPending) controller.query(question.trim()); }}>
          <label htmlFor="demo-question">Pergunta</label><textarea id="demo-question" ref={questionRef} value={question} onChange={(e) => setQuestion(e.target.value)} disabled={state.manualPending || !replay?.sourceRow} maxLength={500} placeholder="Quais evidências justificam a atenção e o que verificar no motor?" />
          <button disabled={state.manualPending || !question.trim() || !replay?.sourceRow}>{state.manualPending ? "Consultando fontes…" : "Perguntar sobre este instante"}</button>
        </form>
        {state.assistantError && <p role="alert" className="demo-notice">{state.assistantError}</p>}
        {[...state.answers].reverse().map((answer, i) => <article className="demo-manual-answer" key={`${answer.contextRevision}-${i}`} ref={i === 0 ? manualAnswerRef : undefined} tabIndex={-1} aria-label={`Resposta: ${answer.question}`}><h3>{answer.question}</h3><p className="muted small">Instante consultado: {fullClock(answer.observedAt)}{answer.contextRevision !== context?.revision ? " · resposta de um instante anterior" : ""}</p>{i === 0 ? <Answer response={answer.response} /> : <details><summary>Reabrir resposta anterior</summary><Answer response={answer.response} /></details>}<details className="assistant-technical-details"><summary>Detalhes do contexto da pergunta</summary><p>Revisão {answer.contextRevision} · linha {answer.sourceRow}</p></details></article>)}
      </section>
    </CopilotDock>
  </main>;
}
