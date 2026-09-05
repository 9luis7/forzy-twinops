import React, { useState } from "react";
import Twin3D from "../components/Twin3D.jsx";
import { useDemoReplay } from "./useDemoReplay.js";
import DemoTrends, { clockLabel, METRICS } from "./DemoTrends.jsx";
import "./demo.css";

export const STATUS_LABELS = { normal: "Sem desvio relevante", watch: "Atenção", alert: "Alerta relativo", insufficient_data: "Dados insuficientes", unknown: "Aguardando avaliação" };
const fmt = (v) => Number.isFinite(v) ? v.toLocaleString("pt-BR", { maximumFractionDigits: 3 }) : "—";
const fullClock = (v) => v ? `${new Date(v).toLocaleString("pt-BR", { timeZone: "UTC" })} UTC` : "Aguardando primeiro par";
const EVENT_LABELS = { sustained_watch: "Atenção sustentada", escalation: "Escalada para alerta", recovery: "Recuperação sustentada" };
const EVENT_STATES = { pending: "Na fila", processing: "Consultando manual", ready: "Recomendação disponível", degraded: "Resposta limitada" };

function Answer({ response }) {
  return <div className="demo-answer">
    <p><strong>Leitura operacional</strong><br />{response.answer.currentState}</p>
    <p><strong>Orientação documental</strong><br />{response.answer.manual}</p>
    <ul className="demo-citations">{response.citations.map((citation, i) => <li key={`${citation.type}-${i}`}>
      {citation.type === "manual" ? <><a href={citation.sourceUrl} target="_blank" rel="noreferrer">{citation.manufacturer} · {citation.equipmentModel} · p. {citation.pageStart}–{citation.pageEnd}</a><p>{citation.excerpt}</p></>
        : <span>Evidência: {citation.feature} = {fmt(citation.value)} {citation.unit} · janela {clockLabel(citation.windowStart)}–{clockLabel(citation.windowEnd)} UTC</span>}
    </li>)}</ul>
    {response.limitations.map((limitation, index) => <p className="muted small" key={index}>{limitation}</p>)}
    <p className="muted small">{response.fallbackUsed ? "Resposta de contingência · " : ""}Validação humana obrigatória. Corpus WEG; cobertura da bomba não afirmada.</p>
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
  const replay = context?.replay;
  const running = replay?.state === "running" && !state.suspended;
  const canInterrupt = state.pendingOperation === "advance" && !state.queuedAction;
  const controlBusy = Boolean(state.queuedAction) || (busy && !canInterrupt);
  const toggle = () => controller.command(running ? "pause" : replay?.cursor === 0 ? "play" : "resume");
  const keyboard = (event) => {
    if (["INPUT", "SELECT", "TEXTAREA", "BUTTON", "A", "SUMMARY"].includes(event.target.tagName) || event.ctrlKey || event.metaKey || event.altKey || controlBusy || !context) return;
    if (event.code === "Space" && replay.state !== "completed") { event.preventDefault(); toggle(); }
    if (event.code === "ArrowRight" && !busy && replay.state === "paused") { event.preventDefault(); controller.command("step"); }
  };
  return <main className="demo-shell" onKeyDown={keyboard} tabIndex={0} aria-label="Painel de replay, Espaço para reproduzir ou pausar e seta direita para um par">
    <header className="demo-header"><div><p className="eyebrow">FORZY TWINOPS <span className="demo-mode">REPLAY REAL</span></p><h1>Do sinal à ação.</h1><p className="muted">Histórico real, avaliação por sensor e contexto documental no mesmo gêmeo.</p></div><a className="demo-live-link" href="/">Abrir operação ao vivo ↗</a></header>
    <section className="panel demo-controls" aria-label="Controles do replay">
      <div className="demo-session"><label>Conjunto histórico<select value={datasetId || datasets[0]?.datasetId || ""} onChange={(e) => setDatasetId(e.target.value)} disabled={busy || state.loading}>{datasets.length ? datasets.map((d) => <option key={d.datasetId} value={d.datasetId}>{d.label}</option>) : <option value="">Aguardando backend</option>}</select></label>
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
        <div className="demo-clock-row"><span>Histórico <strong>{fullClock(replay.sourceTime)}</strong></span><span>Chegada <strong>{fullClock(replay.arrivalTime)}</strong></span><span>Revisão <strong>{context.revision}</strong></span></div>
        <p className="small muted">{replay.warmupPairs} pares precarregados para aquecimento · Espaço: reproduzir/pausar · →: um par, com o painel em foco.</p>
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
          <ol>{[...events].reverse().map((event) => <li key={event.eventId} className="demo-event"><div className="demo-event-title"><strong>{EVENT_LABELS[event.kind]}</strong><span className="small muted">{EVENT_STATES[event.status]}</span></div><p className="muted small">{event.sensorIds.map((id) => id.toUpperCase()).join(" + ")} · linha {event.sourceRow} · {clockLabel(event.observedAt)} UTC · revisão {event.contextRevision}</p>{event.recommendation && <details><summary>Ver recomendação e fontes do evento</summary><Answer response={event.recommendation} /></details>}{event.errorCode && <p className="small muted">{event.retryable ? "Aguardando nova tentativa." : "Geração concluída com limitação."}</p>}</li>)}</ol>
        </section>
        <section className="panel demo-copilot"><p className="eyebrow">Copiloto técnico · corpus WEG</p><h2>Pergunte sobre este instante</h2><p className="muted small">A pergunta fixa a revisão exibida ao enviar. Pause o replay para explorar o mesmo instante.</p>
          <form onSubmit={(e) => { e.preventDefault(); if (question.trim()) controller.query(question.trim()); }}><label htmlFor="demo-question">Pergunta</label><textarea id="demo-question" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={500} placeholder="Quais evidências justificam a atenção e o que verificar no motor?" /><button disabled={state.manualPending || !question.trim() || !replay.sourceRow}>{state.manualPending ? "Consultando fontes…" : `Consultar revisão ${context.revision}`}</button></form>
          {state.assistantError && <p role="alert" className="demo-notice">{state.assistantError}</p>}
          {[...state.answers].reverse().map((answer, i) => <article className="demo-manual-answer" key={`${answer.contextRevision}-${i}`}><h3>{answer.question}</h3><p className="muted small">Contexto da pergunta: revisão {answer.contextRevision} · linha {answer.sourceRow} · {clockLabel(answer.observedAt)} UTC{answer.contextRevision !== context.revision ? " · resposta de um instante anterior" : ""}</p><Answer response={answer.response} /></article>)}
        </section>
      </div>
      <section className="panel demo-provenance"><p className="eyebrow">Procedência e processamento real</p><h2>Como este resultado foi produzido</h2><dl className="demo-pipeline">{[["Pares recebidos", context.pipeline.receivedPairs], ["Leituras recebidas", context.pipeline.receivedReadings], ["Leituras novas", context.pipeline.newInformationReadings], ["Repetições", context.pipeline.repeatedReadings], ["Lacunas", context.pipeline.gapCount], ["Avaliações", context.pipeline.assessmentsComputed], ["Eventos", context.pipeline.eventsCreated], ["Último avanço (ms)", context.pipeline.lastAdvanceMs]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{fmt(value)}</dd></div>)}</dl><p className="muted small">{context.dataset.label} · {context.dataset.pairCount} pares / {context.dataset.readingCount} leituras · {context.dataset.sourceFormat}<br />Período: {fullClock(context.dataset.startAt)} — {fullClock(context.dataset.endAt)}<br />SHA-256: <code>{context.dataset.sourceHash}</code></p><p className="demo-disclaimer">Score relativo ao baseline histórico. Não representa probabilidade de falha nem comprovação de antecipação fora da amostra. Aceleração não participa do score.</p></section>
    </>}
  </main>;
}
