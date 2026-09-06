import React, { useEffect, useRef, useState } from "react";
import { MAX_HISTORY_ANSWER_CHARACTERS } from "../../contracts/rag.js";
import ConciseAnswer from "../assistant/ConciseAnswer.jsx";
import { promptSuggestions } from "../assistant/promptSuggestions.js";
import { formatTimestampText } from "../../lib/displayTime.js";

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

function AssistantAnswer({ response, answerRef, stateLabel, renderStateEvidence, statusNotices }) {
  return <article className="assistant-answer" data-testid="assistant-answer" ref={answerRef} tabIndex={-1} aria-label="Resposta validada do assistente técnico">
    <ConciseAnswer response={response} stateLabel={stateLabel} renderStateEvidence={renderStateEvidence} statusNotices={statusNotices} />
  </article>;
}

export default function TechnicalAssistantPanel({ assetId, enabled, dataSource, isActive = true, stateLabel = "Estado atual", renderStateEvidence, statusNotices, suggestionContext }) {
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

  const ask = async (value) => {
    const submittedQuestion = value.trim();
    if (!submittedQuestion || enabled !== true || loading || requestRef.current.controller) return;

    const controller = new AbortController();
    const requestId = requestRef.current.id + 1;
    requestRef.current = { id: requestId, controller };
    setQuestion(submittedQuestion);
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

      <div className="prompt-suggestions" aria-label="Sugestões de perguntas">
        {promptSuggestions({ ...suggestionContext, answered: turns.length > 0 }).map((suggestion) => <button key={suggestion.label} type="button" disabled={loading} onClick={() => ask(suggestion.question)}>{suggestion.label}</button>)}
      </div>
      <form className="assistant-form" aria-label="Consultar o assistente técnico" onSubmit={(event) => { event.preventDefault(); ask(question); }}>
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
            <p>Buscando no manual e preparando a resposta. As citações serão validadas antes de aparecer.</p>
          </div>
        ) : null}
        {error ? (
          <p className="warning-banner" role="alert">
            O assistente técnico está temporariamente indisponível. Tente novamente mais tarde.
          </p>
        ) : null}
      </div>

      {response && turns.length > 0 ? <p className="assistant-latest-question"><strong>{turns[turns.length - 1].question}</strong></p> : null}
      {response ? <AssistantAnswer response={response} answerRef={answerRef} stateLabel={stateLabel} renderStateEvidence={renderStateEvidence} statusNotices={statusNotices} /> : null}

      {turns.length > 1 ? (
        <details className="assistant-session-history">
          <summary>Perguntas anteriores ({turns.length - 1})</summary>
          <ol>
            {turns.slice(0, -1).map((turn, index) => (
              <li key={`${turn.question}-${index}`}>
                <strong>{turn.question}</strong>
                <p>{formatTimestampText(turn.answer)}</p>
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </section>
  );
}
