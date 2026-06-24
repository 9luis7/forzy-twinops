// Copilot.jsx — Assistente técnico (cena 4). Estilo chat com perguntas sugeridas
// e respostas MOCKADAS, porém asset-aware: o conteúdo muda conforme o estado do
// motor. A ideia é mostrar conhecimento saindo da cabeça do técnico e indo para o
// sistema — com causas, ação recomendada e evidências rastreáveis.

import { useEffect, useMemo, useState } from "react";
import {
  getAsset,
  getComponent,
  assetStatus,
  assetRisk,
  latestReading,
  componentForSensor,
  auditMeta,
} from "../data/mock.js";
import { useLiveTwin } from "../LiveTwinContext.jsx";

// Monta o banco de respostas para um ativo. Todo o conteúdo vem de dados
// estruturados do mock (componentes, sensores, evidências, OS, validação) —
// o copiloto NÃO inventa sensores, documentos nem causas.
function buildAnswers(tag) {
  const asset = getAsset(tag);
  const status = assetStatus(tag);
  const risk = assetRisk(tag);
  const r = latestReading(tag);
  const meta = auditMeta(tag);
  // Componente sob suspeita: derivado do sensor de origem do risco.
  const comp = risk.origin ? componentForSensor(risk.origin) : null;
  const degrading = status !== "normal";

  const causasVibracao = degrading
    ? {
        title: `O que pode estar causando o aumento de vibração no ${tag}?`,
        component: comp ? `${comp.tag} · ${comp.name}` : null,
        sensors: comp ? comp.sensors : risk.origin ? [risk.origin] : [],
        causes: [
          "Desgaste em rolamento",
          "Desalinhamento do eixo",
          "Falta de lubrificação",
          "Sobrecarga operacional",
        ],
        action:
          "Verificar lubrificação e alinhamento na próxima janela de manutenção.",
        evidence: comp
          ? comp.evidence
          : [
              "Vibração aumentou 23% nos últimos 5 dias",
              `Temperatura média subiu de 68 °C para ${r ? r.temperature : 82} °C`,
            ],
        validation: meta.humanValidation,
      }
    : {
        title: `Como está o comportamento de vibração do ${tag}?`,
        component: null,
        sensors: risk.origin ? [risk.origin] : [],
        causes: ["Vibração dentro da faixa de baseline para a carga atual."],
        action: "Nenhuma ação corretiva necessária. Manter monitoramento contínuo.",
        evidence: [
          `Vibração atual ${r ? r.vibration : "—"} m/s² (abaixo do limiar de alerta)`,
          "Sem desvio relevante frente ao histórico do ativo",
        ],
        validation: meta.humanValidation,
      };

  return {
    vibracao: causasVibracao,
    acao: {
      title: "Qual ação você recomenda agora?",
      component: degrading && comp ? `${comp.tag} · ${comp.name}` : null,
      sensors: degrading ? (comp ? comp.sensors : risk.origin ? [risk.origin] : []) : [],
      causes: null,
      action: degrading
        ? `Abrir/priorizar inspeção do ${risk.component.toLowerCase()} em até ${risk.windowHours}h. Conferir lubrificação e alinhamento; reavaliar após intervenção.`
        : "Seguir o plano de manutenção preventiva vigente. Sem intervenção fora de janela.",
      evidence: degrading
        ? [
            `Nível de risco estimado: ${risk.level} (confiança ${risk.confidence}%)`,
            `Origem do sinal: ${risk.origin}`,
            `Pontuado por ${meta.scoringModel} · trace ${meta.traceId}`,
          ]
        : ["Indicadores dentro da faixa esperada"],
      validation: degrading ? meta.humanValidation : null,
    },
    historico: {
      title: "Há histórico de falha parecida nesta planta?",
      component: null,
      sensors: [],
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
      validation: null,
    },
  };
}

// Respostas AO VIVO do motor-estrela — refletem o cenário ativo do loop (ou o
// estado estável). É o que mantém o copiloto coerente com o banner/gráfico.
function buildLiveAnswers({ tag, scenario, status, reading, risk, meta }) {
  const degrading = status !== "normal" && !!scenario;
  const comp = scenario ? getComponent(scenario.component) : null;
  const compLabel = comp ? `${comp.tag} · ${comp.name}` : null;

  if (!degrading) {
    return {
      estado: {
        title: `Como está o ${tag} agora?`,
        component: null,
        sensors: [],
        causes: ["Todas as métricas dentro da faixa de baseline para a carga atual."],
        action: "Nenhuma ação corretiva necessária. Manter monitoramento contínuo.",
        evidence: [
          `Temperatura ${reading ? reading.temperature : "—"} °C · vibração ${reading ? reading.vibration : "—"} m/s² · corrente ${reading ? reading.current : "—"} A`,
          "Sem desvio relevante frente aos limiares operacionais",
        ],
        validation: "Não requer validação (dentro da faixa)",
      },
      acao: {
        title: "Qual ação você recomenda agora?",
        component: null,
        sensors: [],
        causes: null,
        action: "Seguir o plano de manutenção preventiva vigente. Sem intervenção fora de janela.",
        evidence: ["Indicadores dentro da faixa esperada"],
        validation: null,
      },
      historico: {
        title: "Há histórico de falha parecida nesta planta?",
        component: null,
        sensors: [],
        causes: null,
        action: "Sem ocorrência relevante para o estado atual deste ativo.",
        evidence: ["Sem OS corretivas recentes vinculadas ao estado atual"],
        validation: null,
      },
    };
  }

  return {
    estado: {
      title: `O que o gêmeo digital está detectando agora no ${tag}?`,
      component: compLabel,
      sensors: [scenario.sensor],
      causes: scenario.causes,
      action: scenario.recommendation,
      evidence: scenario.evidence,
      validation: meta.humanValidation,
    },
    acao: {
      title: "Qual ação você recomenda agora?",
      component: compLabel,
      sensors: [scenario.sensor],
      causes: null,
      action: scenario.recommendation,
      evidence: [
        `Nível de risco estimado: ${risk.level} (confiança ${scenario.confidence}%)`,
        `Origem do sinal: ${scenario.sensor}`,
        `Pontuado por ${meta.scoringModel} · trace ${meta.traceId}`,
      ],
      validation: meta.humanValidation,
    },
    historico: {
      title: "Há histórico de falha parecida nesta planta?",
      component: null,
      sensors: [],
      causes: null,
      action: `Padrão de ${scenario.short.toLowerCase()} comparado ao baseline e ao histórico do ativo (ex.: OS-2025-118, em motor de bomba semelhante).`,
      evidence: [
        "OS-2025-118 — intervenção corretiva registrada em motor de bomba semelhante",
        "Assinatura atual confrontada com o histórico da planta",
      ],
      validation: null,
    },
  };
}

function Answer({ a }) {
  return (
    <div>
      {a.component && (
        <>
          <h5>Componente</h5>
          <p style={{ margin: "0 0 4px" }} className="mono">{a.component}</p>
        </>
      )}
      {a.sensors && a.sensors.length > 0 && (
        <>
          <h5>Sensores de origem</h5>
          <p style={{ margin: "0 0 4px" }} className="mono">{a.sensors.join(" · ")}</p>
        </>
      )}
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
      {a.validation && (
        <>
          <h5>Validação humana</h5>
          <p style={{ margin: "0 0 4px", color: "var(--alerta)" }}>{a.validation}</p>
        </>
      )}
    </div>
  );
}

export default function Copilot({ tag }) {
  const twin = useLiveTwin();
  const isStar = twin.isStar(tag);
  const scenario = twin.scenarioOf(tag);
  const status = twin.statusOf(tag);
  const reading = twin.readingOf(tag);
  const risk = twin.riskOf(tag);
  const meta = auditMeta(tag);

  // Chave do estado vivo: muda quando um cenário entra/sai (estrela); senão, é a TAG.
  const stateKey = isStar ? (scenario ? scenario.id : "normal") : tag;

  const answers = useMemo(
    () =>
      isStar
        ? buildLiveAnswers({ tag, scenario, status, reading, risk, meta })
        : buildAnswers(tag),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stateKey, tag]
  );

  const keys = Object.keys(answers);
  const seedConv = () => [
    { role: "user", text: answers[keys[0]].title },
    { role: "bot", answer: answers[keys[0]] },
  ];

  // Conversa inicia com a pergunta-chave já respondida (caminho ensaiado da demo).
  const [conversation, setConversation] = useState(seedConv);
  const [asked, setAsked] = useState(() => new Set([keys[0]]));

  // Re-semeia quando o estado vivo muda — o copiloto "percebe" o novo problema
  // (ou a normalização), mantendo-se coerente com o banner e o gráfico.
  useEffect(() => {
    setConversation(seedConv());
    setAsked(new Set([keys[0]]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateKey]);

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
        {keys.map((qk) => (
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
        Respostas geradas apenas a partir de dados estruturados do ativo — componentes, sensores,
        evidências, OS e documentos vinculados. Não inventa sensores nem causas; aponta a validação
        humana pendente. (Demo — base de conhecimento simulada.)
      </p>
    </section>
  );
}
