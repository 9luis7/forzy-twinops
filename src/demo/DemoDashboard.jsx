import React, { useEffect, useRef, useState } from "react";
import Twin3D from "../components/Twin3D.jsx";
import CopilotDock from "../components/assistant/CopilotDock.jsx";
import ConciseAnswer from "../components/assistant/ConciseAnswer.jsx";
import { formatDateTime } from "../lib/displayTime.js";
import { useDemoReplay } from "./useDemoReplay.js";
import DemoTrends, { METRICS } from "./DemoTrends.jsx";
import { demoSuggestions } from "./demoSuggestions.js";
import "./demo.css";

export const STATUS_LABELS = { normal: "Sem desvio relevante", watch: "Atenção", alert: "Alerta relativo", insufficient_data: "Dados insuficientes", unknown: "Aguardando avaliação" };
const fmt = (v) => Number.isFinite(v) ? v.toLocaleString("pt-BR", { maximumFractionDigits: 3 }) : "—";
const fullClock = (v) => v ? `${formatDateTime(v)} (São Paulo)` : "Aguardando primeiro par";
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
  const [analysisPending, setAnalysisPending] = useState(false);
  const analysisIntentRef = useRef(null);
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
    analysisIntentRef.current = null;
    setAnalysisPending(false);
    setEventSelection(null);
    setQuestion("");
    setSelected("all");
  }, [controller, replay?.runId, replay?.generation]);
  useEffect(() => () => { analysisIntentRef.current = null; }, [controller]);
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
  const suggestions = demoSuggestions(context);
  const attentionSensors = ["s1", "s2"].filter((id) => ["watch", "alert"].includes(context?.sensors[id]?.assessment?.assessment?.status));
  const canQuery = Boolean(replay?.sourceRow) && ["paused", "completed"].includes(replay?.state)
    && !busy && !state.queuedAction && !state.manualPending && !analysisPending && !error;
  const sendQuestion = (value) => {
    const current = controller.getSnapshot();
    if (!value.trim() || !current.context?.replay.sourceRow || current.busy || current.manualPending || current.queuedAction || current.error
      || !["paused", "completed"].includes(current.context.replay.state) || analysisIntentRef.current) return;
    setEventSelection(null);
    setQuestion(value);
    controller.query(value.trim());
  };
  const pauseAndAnalyze = async () => {
    if (analysisIntentRef.current || controlBusy || state.manualPending || !replay?.sourceRow || error) return;
    const intent = { controller, runId: replay.runId, generation: replay.generation };
    analysisIntentRef.current = intent;
    setAnalysisPending(true);
    try {
      if (replay.state === "running") await controller.command("pause");
      const current = controller.getSnapshot();
      if (analysisIntentRef.current !== intent || current.context?.replay.runId !== intent.runId
        || current.context?.replay.generation !== intent.generation || current.error || current.busy
        || current.queuedAction || !current.context?.replay.sourceRow
        || !["paused", "completed"].includes(current.context.replay.state)) return;
      setEventSelection(null);
      setQuestion(demoSuggestions(current.context)[0].question);
      setCopilotOpen(true);
    } finally {
      if (analysisIntentRef.current === intent) { analysisIntentRef.current = null; setAnalysisPending(false); }
    }
  };
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
          {!attentionSensors.length && <button className="secondary-button" disabled={analysisPending || controlBusy || state.manualPending || !replay.sourceRow || Boolean(error)} onClick={pauseAndAnalyze}>{analysisPending ? "Aguardando pausa…" : replay.state === "running" ? "Pausar e analisar" : "Analisar este instante"}</button>}
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
    <section className="demo-flow panel" aria-label="Como a demonstração funciona">
      <ol><li><strong>1. Dados chegam</strong><span>O histórico avança em pares de S1 e S2.</span></li><li><strong>2. O sistema avalia</strong><span>Regras e scores atualizam gráficos e 3D.</span></li><li><strong>3. Um evento é registrado</strong><span>Quando a atenção persiste ou o estado muda.</span></li><li><strong>4. O copiloto consulta o manual</strong><span>Por evento ou por uma pergunta sua.</span></li></ol>
      <p className="small muted">A avaliação dos sensores é automática. A IA é consultada nos eventos e nas perguntas; não a cada leitura. As sugestões de pergunta são preparadas pelo sistema, sem consultar a IA.</p>
    </section>
    {!context ? <section className="demo-welcome panel"><h2>Escolha um roteiro e prepare a demonstração.</h2><p>Depois, use <strong>Continuar</strong> para receber os dados em sequência ou <strong>Avançar 1 par</strong> para explorar aos poucos. Use <strong>Pausar e analisar</strong> para consultar o copiloto sobre um instante fixo.</p><p className="small muted">O roteiro guiado mostra 300 pares. O roteiro livre permite percorrer o histórico completo.</p></section> : <>
      {attentionSensors.length > 0 && <section className="panel demo-attention" aria-label="Atenção no conjunto" data-status={context.status}>
        <div><h2>{attentionSensors.map((id) => `${id === "s1" ? "Motor" : "Bomba"} (${id.toUpperCase()})`).join(" e ")} exige{attentionSensors.length > 1 ? "m" : ""} atenção</h2><p>Revise os sinais deste instante antes de definir a próxima ação. O alerta indica um desvio relativo ao histórico, não um diagnóstico.</p></div>
        <button onClick={pauseAndAnalyze} disabled={analysisPending || controlBusy || state.manualPending || !replay.sourceRow || Boolean(error)}>{analysisPending ? "Aguardando pausa…" : replay.state === "running" ? "Pausar e analisar" : "Analisar este instante"}</button>
      </section>}
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
          <ConciseAnswer response={selectedEvent.recommendation} />
          <details className="assistant-technical-details"><summary>Detalhes do contexto do evento</summary><p>Linha {selectedEvent.sourceRow} · revisão {selectedEvent.contextRevision}</p></details>
          <button className="button-secondary" onClick={() => { setEventSelection(null); questionRef.current?.focus(); }}>Fechar orientação do evento</button>
        </article>}
        <p className="eyebrow">Manual do motor WEG</p><h2>Pergunte sobre este instante</h2><p className="muted small">A pergunta usa o instante pausado. O manual cobre o motor; os sinais da bomba podem ser consultados, mas seus procedimentos não estão neste manual.</p>
        {!replay?.sourceRow && <p className="assistant-unavailable" role="status">Prepare a reprodução e avance uma leitura para consultar o copiloto.</p>}
        {replay?.sourceRow && replay.state === "running" && <div className="demo-notice"><p>Os dados continuam avançando. Pause para analisar um instante fixo.</p><button className="secondary-button" onClick={pauseAndAnalyze} disabled={analysisPending || controlBusy || state.manualPending || Boolean(error)}>{analysisPending ? "Aguardando pausa…" : "Pausar para analisar"}</button></div>}
        <div className="demo-suggestions" role="group" aria-label="Perguntas sugeridas">{suggestions.map((suggestion) => <button type="button" className="secondary-button" key={suggestion.label} title={suggestion.question} disabled={!canQuery} onClick={() => sendQuestion(suggestion.question)}>{suggestion.label}</button>)}</div>
        <form className="assistant-form" aria-label="Perguntar ao copiloto da demonstração" onSubmit={(e) => { e.preventDefault(); sendQuestion(question); }}>
          <label htmlFor="demo-question">Pergunta</label><textarea id="demo-question" ref={questionRef} value={question} onChange={(e) => setQuestion(e.target.value)} disabled={state.manualPending || !replay?.sourceRow} maxLength={500} placeholder="Quais evidências justificam a atenção e o que verificar no motor?" />
          <button disabled={!canQuery || !question.trim()}>{state.manualPending ? "Consultando manual e IA…" : "Perguntar sobre este instante"}</button>
        </form>
        {state.assistantError && <p role="alert" className="demo-notice">{state.assistantError}</p>}
        {[...state.answers].reverse().map((answer, i) => <article className="demo-manual-answer" key={`${answer.contextRevision}-${i}`} ref={i === 0 ? manualAnswerRef : undefined} tabIndex={-1} aria-label={`Resposta: ${answer.question}`}><h3>{answer.question}</h3><p className="muted small">Instante consultado: {fullClock(answer.observedAt)}{answer.contextRevision !== context?.revision ? " · resposta de um instante anterior" : ""}</p>{i === 0 ? <ConciseAnswer response={answer.response} /> : <details><summary>Reabrir resposta anterior</summary><ConciseAnswer response={answer.response} /></details>}<details className="assistant-technical-details"><summary>Detalhes do contexto da pergunta</summary><p>Revisão {answer.contextRevision} · linha {answer.sourceRow}</p></details></article>)}
      </section>
    </CopilotDock>
  </main>;
}
