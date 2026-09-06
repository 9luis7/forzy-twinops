import React, { useState } from "react";
import { formatDateTime, formatTimestampText } from "../../lib/displayTime.js";
import "./conciseAnswer.css";

const notices = {
  manual_insufficient: "O manual não traz evidência suficiente para esta pergunta.",
  operational_unavailable: "Os dados atuais estão indisponíveis; a orientação do manual aparece separadamente.",
  out_of_scope: "A solicitação está fora do escopo seguro deste assistente.",
  degraded_fallback: "A resposta completa não pôde ser validada; exibindo a orientação de contingência disponível.",
};
const number = (value) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 }).format(value);
const featureNames = {
  velocity_ewma: "Vibração média recente", velocity_slope: "Tendência da vibração",
  velocity_change_point: "Mudança da vibração", temperature_deviation: "Desvio de temperatura",
};
export const evidenceLabel = (feature) => featureNames[feature] ?? feature;
export const evidenceUnit = (unit) => unit === "degC" ? "°C" : unit;

export function responseOrigin(response) {
  if (response.fallbackUsed) return "Resposta de contingência";
  if (response.groundingStatus === "out_of_scope") return "Limite de escopo · sem consulta à IA";
  if (["grounded", "operational_unavailable"].includes(response.groundingStatus)
      && response.citations.some((citation) => citation.type === "manual")) return "IA + manual · fontes validadas";
  return "Manual sem evidência suficiente";
}

function AnswerText({ text, label }) {
  const [expanded, setExpanded] = useState(false);
  const formatted = formatTimestampText(text);
  const long = formatted.length > 480;
  return <div className="concise-answer-text">
    <p className={long && !expanded ? "is-collapsed" : undefined}>{formatted}</p>
    {long && <button type="button" className="answer-text-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      {expanded ? "Recolher texto" : `Ler ${label} completa`}
    </button>}
  </div>;
}

function ManualCitation({ citation }) {
  return <details className="assistant-citation assistant-citation--manual">
    <summary>Manual · {citation.manufacturer} {citation.equipmentModel} · p. {citation.pageStart}{citation.pageEnd !== citation.pageStart ? `–${citation.pageEnd}` : ""}</summary>
    <div className="assistant-citation__body">
      <p>{citation.section ?? "Seção não identificada"} · revisão {citation.revision}</p>
      <blockquote>{citation.excerpt}</blockquote>
      <a href={citation.sourceUrl} target="_blank" rel="noreferrer">Abrir fonte oficial</a>
      <details><summary>Identificação do trecho</summary><code>SHA-256 {citation.contentHash}</code></details>
    </div>
  </details>;
}

function TelemetryCitation({ citation }) {
  return <details className="assistant-citation assistant-citation--telemetry">
    <summary>Sensor · {evidenceLabel(citation.feature)}</summary>
    <div className="assistant-citation__body">
      <p><strong>{number(citation.value)} {evidenceUnit(citation.unit)}</strong></p>
      <p>Janela <time dateTime={citation.windowStart}>{formatDateTime(citation.windowStart)}</time> – <time dateTime={citation.windowEnd}>{formatDateTime(citation.windowEnd)}</time> · São Paulo</p>
      <p>Recebido em <time dateTime={citation.receivedAt}>{formatDateTime(citation.receivedAt)}</time> · São Paulo</p>
      <details><summary>Detalhes da medição</summary>
        <p>Assessment {citation.assessmentId}</p>
        <p>Frescor {number(citation.freshnessMs)} ms · qualidade {citation.qualityStatus}</p>
        {citation.windowSeconds !== null && <p>Janela de evidência {number(citation.windowSeconds)} s</p>}
        <code>Evidência {citation.evidenceId}</code>
      </details>
    </div>
  </details>;
}

export default function ConciseAnswer({ response, stateLabel = "Leitura operacional", renderStateEvidence, statusNotices }) {
  const manual = response.citations.filter((citation) => citation.type === "manual");
  const telemetry = response.citations.filter((citation) => citation.type === "telemetry");
  const notice = statusNotices?.[response.groundingStatus] ?? notices[response.groundingStatus];
  return <div className="concise-answer">
    <p className="answer-origin" data-fallback={response.fallbackUsed}>{responseOrigin(response)}</p>
    {notice && <p className={`assistant-state assistant-state--${response.groundingStatus}`} role="status">{notice}</p>}
    {response.fallbackUsed && response.groundingStatus !== "degraded_fallback" && <p role="alert" className="warning-banner">{notices.degraded_fallback}</p>}
    <section className="concise-answer-section" aria-label={stateLabel}>
      <h3>{stateLabel}</h3>
      <AnswerText key={response.answer.currentState} text={response.answer.currentState} label="leitura" />
    </section>
    <section className="concise-answer-section" aria-label="Segundo o manual">
      <h3>Segundo o manual</h3>
      {response.fallbackUsed
        ? <p>A IA não entregou uma orientação validada. Os trechos disponíveis do manual estão nas fontes abaixo.</p>
        : <AnswerText key={response.answer.manual} text={response.answer.manual} label="orientação" />}
    </section>
    <p className="concise-answer-validation">Validação humana obrigatória. Manual do motor; cobertura da bomba não afirmada.</p>
    <details className="answer-supporting-details">
      <summary>Fontes e evidências</summary>
      {response.fallbackUsed && <details className="assistant-citation"><summary>Texto de contingência</summary><p>{formatTimestampText(response.answer.manual)}</p></details>}
      <div className="assistant-citations" aria-label="Citações do manual">
        {manual.length ? manual.map((citation, index) => <ManualCitation key={`${citation.chunkId}-${index}`} citation={citation} />)
          : <p>Nenhuma citação documental sustentou esta resposta.</p>}
      </div>
      <div className="assistant-citations" aria-label="Evidências operacionais">
        {renderStateEvidence ? renderStateEvidence(response) : telemetry.length
          ? telemetry.map((citation, index) => <TelemetryCitation key={`${citation.evidenceId}-${index}`} citation={citation} />)
          : <p>Nenhuma evidência operacional está disponível.</p>}
      </div>
    </details>
    <details className="answer-supporting-details" aria-label="Limitações da resposta">
      <summary>Limites da análise</summary>
      <ul>{response.limitations.map((limitation, index) => <li key={index}>{formatTimestampText(limitation)}</li>)}</ul>
    </details>
    <details className="assistant-technical-details">
      <summary>Detalhes técnicos da resposta</summary>
      <p>A condição dos sensores vem da avaliação automática. A IA seleciona referências do manual; o sistema valida as citações antes de exibir.</p>
      {response.fallbackUsed && <p>Contingência não confirma uma geração: a consulta pode ter falhado antes ou durante a etapa de IA.</p>}
      <small>Corpus {response.corpus?.corpusId ?? "indisponível"} · trace {response.traceId}</small>
    </details>
  </div>;
}
