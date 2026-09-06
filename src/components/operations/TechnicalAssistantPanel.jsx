import React, { useEffect, useRef, useState } from "react";
import { MAX_HISTORY_ANSWER_CHARACTERS } from "../../contracts/rag.js";

const STATUS_COPY = Object.freeze({
  manual_insufficient: "O manual ativo não contém evidência suficiente para esta pergunta.",
  operational_unavailable: "O estado operacional está indisponível; a seção do manual permanece separada.",
  out_of_scope: "A solicitação está fora do escopo seguro deste assistente.",
  degraded_fallback:
    "A resposta completa não pôde ser validada; exibindo a orientação de contingência disponível.",
});

const formatNumber = (value) => new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 3,
}).format(value);

const MANUAL_HISTORY_LABEL = "Segundo o manual:\n";

const truncateHistorySection = (value, budget) => {
  if (value.length <= budget) return value;
  if (budget <= 1) return value.slice(0, budget);
  return `${value.slice(0, budget - 1)}…`;
};

export const completedAnswer = (response, stateLabel = "Estado atual") => {
  const currentHistoryLabel = `\n${stateLabel}:\n`;
  const available = MAX_HISTORY_ANSWER_CHARACTERS
    - MANUAL_HISTORY_LABEL.length
    - currentHistoryLabel.length;
  let manualBudget = Math.min(response.answer.manual.length, Math.floor(available / 2));
  let currentBudget = Math.min(response.answer.currentState.length, available - manualBudget);
  let remainder = available - manualBudget - currentBudget;

  const manualRemainder = response.answer.manual.length - manualBudget;
  const manualExtra = Math.min(manualRemainder, remainder);
  manualBudget += manualExtra;
  remainder -= manualExtra;
  currentBudget += Math.min(response.answer.currentState.length - currentBudget, remainder);

  return [
    MANUAL_HISTORY_LABEL,
    truncateHistorySection(response.answer.manual, manualBudget),
    currentHistoryLabel,
    truncateHistorySection(response.answer.currentState, currentBudget),
  ].join("");
};

function ManualCitation({ citation }) {
  const pages = citation.pageStart === citation.pageEnd
    ? `Página ${citation.pageStart}`
    : `Páginas ${citation.pageStart}–${citation.pageEnd}`;
  return (
    <details className="assistant-citation assistant-citation--manual">
      <summary>
        Manual · {citation.manufacturer} {citation.equipmentModel} · revisão {citation.revision}
      </summary>
      <div className="assistant-citation__body">
        <p>{pages} · {citation.section ?? "Seção não identificada"}</p>
        <blockquote>{citation.excerpt}</blockquote>
        <code>SHA-256 {citation.contentHash}</code>
        <a href={citation.sourceUrl} target="_blank" rel="noreferrer">
          Abrir fonte oficial
        </a>
      </div>
    </details>
  );
}

function TelemetryCitation({ citation }) {
  return (
    <details className="assistant-citation assistant-citation--telemetry">
      <summary>Telemetria · {citation.feature}</summary>
      <div className="assistant-citation__body">
        <p><strong>{formatNumber(citation.value)} {citation.unit}</strong></p>
        <p>Assessment {citation.assessmentId}</p>
        <p>Janela <time dateTime={citation.windowStart}>{citation.windowStart}</time> – <time dateTime={citation.windowEnd}>{citation.windowEnd}</time></p>
        <p>Recebido em <time dateTime={citation.receivedAt}>{citation.receivedAt}</time></p>
        <p>Frescor {formatNumber(citation.freshnessMs)} ms · qualidade {citation.qualityStatus}</p>
        {citation.windowSeconds !== null ? <p>Janela de evidência {formatNumber(citation.windowSeconds)} s</p> : null}
        <code>Evidência {citation.evidenceId}</code>
      </div>
    </details>
  );
}

function AssistantAnswer({ response, answerRef, stateLabel, renderStateEvidence, statusNotices }) {
  const manualCitations = response.citations.filter((item) => item.type === "manual");
  const telemetryCitations = response.citations.filter((item) => item.type === "telemetry");
  const stateNotice = statusNotices?.[response.groundingStatus] ?? STATUS_COPY[response.groundingStatus];

  return (
    <article
      className="assistant-answer"
      data-testid="assistant-answer"
      ref={answerRef}
      tabIndex={-1}
      aria-label="Resposta validada do assistente técnico"
    >
      {stateNotice ? (
        <p className={`assistant-state assistant-state--${response.groundingStatus}`} role="status">
          {stateNotice}
        </p>
      ) : null}
      {response.fallbackUsed && response.groundingStatus !== "degraded_fallback" ? (
        <p className="warning-banner" role="alert">
          A resposta completa não pôde ser validada; exibindo a orientação de contingência disponível.
        </p>
      ) : null}

      <div className="assistant-provenance-grid">
        <section aria-labelledby="assistant-manual-title">
          <p className="eyebrow">Documento oficial</p>
          <h3 id="assistant-manual-title">Segundo o manual</h3>
          <p>{response.answer.manual}</p>
          <div className="assistant-citations" aria-label="Citações do manual">
            {manualCitations.length > 0
              ? manualCitations.map((citation, index) => (
                <ManualCitation
                  citation={citation}
                  key={`manual-${citation.documentId}-${citation.chunkId}-${citation.contentHash}-${index}`}
                />
              ))
              : <p className="empty-state">Nenhuma citação documental sustentou esta resposta.</p>}
          </div>
        </section>

        <section aria-labelledby="assistant-current-title">
          <p className="eyebrow">O que os dados mostram</p>
          <h3 id="assistant-current-title">{stateLabel}</h3>
          <p>{response.answer.currentState}</p>
          <div className="assistant-citations" aria-label="Evidências operacionais">
            {renderStateEvidence ? renderStateEvidence(response) : telemetryCitations.length > 0
              ? telemetryCitations.map((citation) => (
                <TelemetryCitation
                  citation={citation}
                  key={`telemetry-${citation.assessmentId}-${citation.evidenceId}`}
                />
              ))
              : <p className="empty-state">Nenhuma evidência operacional está disponível.</p>}
          </div>
        </section>
      </div>

      <aside className="assistant-guardrails" aria-label="Limitações da resposta">
        <strong>Validação humana obrigatória</strong>
        {response.limitations.length > 0 ? (
          <ul>{response.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        ) : null}
        <details className="assistant-technical-details">
          <summary>Detalhes técnicos da resposta</summary>
          <small>Corpus {response.corpus?.corpusId ?? "indisponível"} · trace {response.traceId}</small>
        </details>
      </aside>
    </article>
  );
}

export default function TechnicalAssistantPanel({ assetId, enabled, dataSource, isActive = true, stateLabel = "Estado atual", renderStateEvidence, statusNotices }) {
  if (typeof assetId !== "string" || assetId.length === 0) {
    throw new TypeError("TechnicalAssistantPanel assetId must be a non-empty string");
  }
  if (!dataSource || typeof dataSource.query !== "function") {
    throw new TypeError("TechnicalAssistantPanel dataSource must implement query");
  }

  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const requestRef = useRef({ id: 0, controller: null });
  const mountedRef = useRef(true);
  const answerRef = useRef(null);
  const isActiveRef = useRef(isActive);
  isActiveRef.current = isActive;
  const contextRef = useRef({ enabled, assetId, dataSource });

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestRef.current.id += 1;
      requestRef.current.controller?.abort();
    };
  }, []);

  useEffect(() => {
    if (response && isActiveRef.current) answerRef.current?.focus();
  }, [response]);

  useEffect(() => {
    const previous = contextRef.current;
    const contextChanged = previous.enabled !== enabled
      || previous.assetId !== assetId
      || previous.dataSource !== dataSource;
    contextRef.current = { enabled, assetId, dataSource };
    if (!contextChanged) return;

    requestRef.current.id += 1;
    requestRef.current.controller?.abort();
    requestRef.current.controller = null;
    setLoading(false);
    setQuestion("");
    setTurns([]);
    setConversationId(null);
    setResponse(null);
    setError(null);
  }, [assetId, dataSource, enabled]);

  const cancel = () => {
    requestRef.current.id += 1;
    requestRef.current.controller?.abort();
    requestRef.current.controller = null;
    setLoading(false);
  };

  const submit = async (event) => {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || loading) return;

    const controller = new AbortController();
    const requestId = requestRef.current.id + 1;
    requestRef.current = { id: requestId, controller };
    setLoading(true);
    setError(null);
    try {
      const nextResponse = await dataSource.query(assetId, {
        question: submittedQuestion,
        ...(conversationId ? { conversationId } : {}),
        history: turns,
      }, { signal: controller.signal });
      if (!mountedRef.current || requestRef.current.id !== requestId) return;
      setResponse(nextResponse);
      setConversationId(nextResponse.conversationId);
      setTurns((current) => [...current, {
        question: submittedQuestion,
        answer: completedAnswer(nextResponse, stateLabel),
      }].slice(-4));
      setQuestion("");
    } catch (requestError) {
      if (
        mountedRef.current
        && requestRef.current.id === requestId
        && requestError?.name !== "AbortError"
      ) {
        setError(requestError);
      }
    } finally {
      if (mountedRef.current && requestRef.current.id === requestId) {
        requestRef.current.controller = null;
        setLoading(false);
      }
    }
  };

  if (enabled !== true) {
    return (
      <section className="panel technical-assistant" aria-labelledby="technical-assistant-title">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Manual + estado real</p>
            <h2 id="technical-assistant-title">Assistente técnico</h2>
          </div>
        </div>
        <p className="assistant-unavailable" role="status">
          O manual do equipamento ou o serviço de consulta está indisponível.
          Tente novamente mais tarde.
        </p>
      </section>
    );
  }

  return (
    <section className="panel technical-assistant" aria-labelledby="technical-assistant-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Manual + estado real</p>
          <h2 id="technical-assistant-title">Assistente técnico</h2>
        </div>
      </div>

      <form className="assistant-form" aria-label="Consultar o assistente técnico" onSubmit={submit}>
        <label htmlFor="technical-assistant-question">Pergunta técnica</label>
        <textarea
          id="technical-assistant-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          maxLength={500}
          rows={3}
          disabled={loading}
          aria-describedby="technical-assistant-help"
        />
        <p id="technical-assistant-help">
          Consulte o manual do motor e os dados operacionais disponíveis. A conversa fica apenas nesta sessão.
        </p>
        <div className="assistant-form__actions">
          <button type="submit" disabled={loading || question.trim().length === 0}>
            {loading ? "Consultando…" : "Consultar manual e estado"}
          </button>
          {loading ? <button type="button" className="button-secondary" onClick={cancel}>Cancelar consulta</button> : null}
        </div>
      </form>

      <div className="assistant-live-region" aria-live="polite" aria-atomic="true">
        {loading ? (
          <div role="status" aria-label="Consultando fontes validadas">
            <strong>Consultando fontes validadas…</strong>
            <ol>
              <li>Buscando trechos no manual do motor</li>
              <li>Consultando os dados disponíveis</li>
              <li>Validando citações antes de exibir</li>
            </ol>
          </div>
        ) : null}
        {error ? (
          <p className="warning-banner" role="alert">
            O assistente técnico está temporariamente indisponível. Tente novamente mais tarde.
          </p>
        ) : null}
      </div>

      {response ? <AssistantAnswer response={response} answerRef={answerRef} stateLabel={stateLabel} renderStateEvidence={renderStateEvidence} statusNotices={statusNotices} /> : null}

      {turns.length > 1 ? (
        <details className="assistant-session-history">
          <summary>Perguntas anteriores ({turns.length - 1})</summary>
          <ol>
            {turns.slice(0, -1).map((turn, index) => (
              <li key={`${turn.question}-${index}`}>
                <strong>{turn.question}</strong>
                <p>{turn.answer}</p>
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </section>
  );
}
