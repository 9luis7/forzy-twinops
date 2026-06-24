// Copilot.jsx — Assistente técnico (cena 4). Estilo chat com perguntas sugeridas
// e respostas MOCKADAS, porém asset-aware: o conteúdo muda conforme o estado do
// motor. A ideia é mostrar conhecimento saindo da cabeça do técnico e indo para o
// sistema — com causas, ação recomendada e evidências rastreáveis.

import { useMemo, useState } from "react";
import { getAsset, assetStatus, assetRisk, latestReading } from "../data/mock.js";

// Monta o banco de respostas para um ativo (depende do estado atual).
function buildAnswers(tag) {
  const asset = getAsset(tag);
  const status = assetStatus(tag);
  const risk = assetRisk(tag);
  const r = latestReading(tag);
  const degrading = status !== "normal";

  const causasVibracao = degrading
    ? {
        title: `O que pode estar causando o aumento de vibração no ${tag}?`,
        causes: [
          "Desgaste em rolamento",
          "Desalinhamento do eixo",
          "Falta de lubrificação",
          "Sobrecarga operacional",
        ],
        action:
          "Verificar lubrificação e alinhamento na próxima janela de manutenção.",
        evidence: [
          "Vibração aumentou 23% nos últimos 5 dias",
          `Temperatura média subiu de 68 °C para ${r ? r.temperature : 82} °C`,
          "Falha semelhante registrada na OS-2025-118",
          "Manual técnico recomenda inspeção acima de 80 °C em operação contínua",
        ],
      }
    : {
        title: `Como está o comportamento de vibração do ${tag}?`,
        causes: ["Vibração dentro da faixa de baseline para a carga atual."],
        action: "Nenhuma ação corretiva necessária. Manter monitoramento contínuo.",
        evidence: [
          `Vibração atual ${r ? r.vibration : "—"} m/s² (abaixo do limiar de alerta)`,
          "Sem desvio relevante frente ao histórico do ativo",
        ],
      };

  return {
    vibracao: causasVibracao,
    acao: {
      title: "Qual ação você recomenda agora?",
      causes: null,
      action: degrading
        ? `Abrir/priorizar inspeção do ${risk.component.toLowerCase()} em até ${risk.windowHours}h. Conferir lubrificação e alinhamento; reavaliar após intervenção.`
        : "Seguir o plano de manutenção preventiva vigente. Sem intervenção fora de janela.",
      evidence: degrading
        ? [
            `Nível de risco estimado: ${risk.level} (confiança ${risk.confidence}%)`,
            `Origem do sinal: ${risk.origin}`,
          ]
        : ["Indicadores dentro da faixa esperada"],
    },
    historico: {
      title: "Há histórico de falha parecida nesta planta?",
      causes: null,
      action: degrading
        ? "Sim. OS-2025-118 registrou falha de rolamento em motor de bomba semelhante — mesmo padrão de vibração+temperatura precedendo a parada."
        : "Não há ocorrência recente relevante para este ativo.",
      evidence: degrading
        ? [
            "OS-2025-118 — substituição de rolamento (motor de bomba)",
            "Padrão de degradação compatível com o caso atual",
          ]
        : ["Sem OS corretivas recentes vinculadas"],
    },
  };
}

const QUESTION_KEYS = ["vibracao", "acao", "historico"];

function Answer({ a }) {
  return (
    <div>
      {a.causes && (
        <>
          <h5>Possíveis causas</h5>
          <ol>
            {a.causes.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ol>
        </>
      )}
      <h5>Ação recomendada</h5>
      <p style={{ margin: "0 0 4px" }}>{a.action}</p>
      <h5>Evidências</h5>
      <div>
        {a.evidence.map((e, i) => (
          <div className="evidence" key={i}>
            <span className="ev-mark">▸</span>
            <span>{e}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Copilot({ tag }) {
  const answers = useMemo(() => buildAnswers(tag), [tag]);
  // Conversa inicia com a pergunta-chave já respondida (caminho ensaiado da demo).
  const [conversation, setConversation] = useState(() => [
    { role: "user", text: answers.vibracao.title },
    { role: "bot", answer: answers.vibracao },
  ]);
  const [asked, setAsked] = useState(() => new Set(["vibracao"]));
  // Obs.: o pai monta <Copilot key={tag} /> — trocar de ativo remonta e reseta a conversa.

  const ask = (qk) => {
    const a = answers[qk];
    setConversation((prev) => [...prev, { role: "user", text: a.title }, { role: "bot", answer: a }]);
    setAsked((prev) => new Set(prev).add(qk));
  };

  return (
    <section className="card">
      <h3>
        🤖 Assistente técnico{" "}
        <span className="muted small" style={{ fontWeight: 400 }}>
          · copiloto de manutenção · {tag}
        </span>
      </h3>

      <div className="copilot-q-row">
        {QUESTION_KEYS.map((qk) => (
          <button
            key={qk}
            className={`copilot-q ${asked.has(qk) ? "active" : ""}`}
            onClick={() => ask(qk)}
          >
            {answers[qk].title}
          </button>
        ))}
      </div>

      <div>
        {conversation
          .filter((m) => m.role)
          .map((m, i) =>
            m.role === "user" ? (
              <div className="chat-msg" key={i}>
                <div className="chat-avatar user">🧑‍🔧</div>
                <div className="chat-bubble user">{m.text}</div>
              </div>
            ) : (
              <div className="chat-msg" key={i}>
                <div className="chat-avatar bot">✨</div>
                <div className="chat-bubble">
                  <Answer a={m.answer} />
                </div>
              </div>
            )
          )}
      </div>

      <p className="muted small" style={{ marginTop: 4 }}>
        Respostas geradas a partir de leituras de sensores, histórico de OS e documentos técnicos
        vinculados ao ativo. (Demo — base de conhecimento simulada.)
      </p>
    </section>
  );
}
