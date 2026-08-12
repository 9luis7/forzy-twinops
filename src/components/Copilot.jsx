import React, { useEffect, useMemo, useRef, useState } from "react";

import { useLiveTwin } from "../LiveTwinContext.jsx";
import { createCopilotClient } from "../copilot/CopilotClient.js";
import { buildExplanationRequest } from "../copilot/buildExplanationContext.js";
import DeterministicExplanation, {
  deterministicExplanationFromAssessment,
} from "../copilot/DeterministicExplanation.jsx";

const DEFAULT_QUESTIONS = [
  "O que mudou nesta avaliação?",
  "Qual ação é segura agora?",
  "Quais evidências sustentam esse estado?",
];

const defaultClient = createCopilotClient();

export function CopilotView({ tag, snapshot, client = defaultClient }) {
  const assessmentId = snapshot?.assessment?.assessmentId ?? "no-assessment";
  const [conversation, setConversation] = useState([]);
  const [pending, setPending] = useState(false);
  const abortRef = useRef(null);

  const fallback = useMemo(
    () => deterministicExplanationFromAssessment(snapshot?.assessment),
    [assessmentId, snapshot?.assessment]
  );

  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setConversation([]);
    setPending(false);
  }, [assessmentId]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function ask(question) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setConversation((items) => [...items, { role: "user", text: question }]);

    if (!snapshot?.assessment || snapshot.capabilities?.copilot !== true) {
      setConversation((items) => [...items, { role: "assistant", response: fallback }]);
      return;
    }

    setPending(true);
    try {
      const request = buildExplanationRequest({ question, snapshot });
      const response = await client.explain(request, { signal: controller.signal });
      setConversation((items) => [...items, { role: "assistant", response }]);
    } catch (error) {
      if (error?.name !== "AbortError") {
        setConversation((items) => [...items, { role: "assistant", response: fallback }]);
      }
    } finally {
      if (abortRef.current === controller) setPending(false);
    }
  }

  return (
    <section className="card">
      <h3>
        🤖 Assistente técnico{" "}
        <span className="muted small" style={{ fontWeight: 400 }}>
          · evidências estruturadas · {tag}
        </span>
      </h3>

      <div className="copilot-q-row">
        {DEFAULT_QUESTIONS.map((question) => (
          <button
            key={question}
            className="copilot-q"
            disabled={pending}
            onClick={() => ask(question)}
          >
            {question}
          </button>
        ))}
      </div>

      {conversation.map((message, index) =>
        message.role === "user" ? (
          <div className="chat-msg" key={`${index}-${message.text}`}>
            <div className="chat-avatar user">🧑‍🔧</div>
            <div className="chat-bubble user">{message.text}</div>
          </div>
        ) : (
          <div className="chat-msg" key={`${index}-${message.response.provider}`}>
            <div className="chat-avatar bot">✨</div>
            <div className="chat-bubble">
              <DeterministicExplanation response={message.response} />
            </div>
          </div>
        )
      )}
      {pending && <p role="status">Gerando explicação…</p>}

      <p className="muted small" style={{ marginTop: 4 }}>
        O copiloto explica o assessment; não recalcula alerta, causa raiz ou tempo até falha.
      </p>
    </section>
  );
}

export default function Copilot({ tag }) {
  const twin = useLiveTwin();
  const snapshot = twin?.snapshot?.assetTag === tag ? twin.snapshot : null;
  return <CopilotView tag={tag} snapshot={snapshot} />;
}
