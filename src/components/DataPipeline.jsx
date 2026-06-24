// DataPipeline.jsx — as 6 etapas clicáveis do ciclo de vida do dado, em linguagem simples.
// [1] SENSOR → [2] BROKER → [3] INGESTÃO → [4] BANCO → [5] PAINEL → [6] DECISÃO
// Cada etapa lidera com o que ela significa para uma pessoa; o nome técnico fica secundário.

import { useState } from "react";
import { getAsset, latestReading, assetStatus, statusLabel } from "../data/mock.js";

// Recomendação simples derivada do estado (mock da camada de decisão).
function recommendation(status) {
  switch (status) {
    case "critico":
      return "Parada para inspeção recomendada — temperatura/vibração acima do limiar crítico.";
    case "alerta":
      return "Agendar manutenção preventiva — tendência de degradação detectada.";
    case "normal":
      return "Operação dentro do esperado — nenhuma ação necessária.";
    default:
      return "Sem dados suficientes para recomendar.";
  }
}

// Define as 6 etapas. Cada uma traz:
//  - plain: rótulo humano (o que a etapa faz, em linguagem simples)
//  - tech : nome técnico (camada secundária, mono/muted)
//  - detail: contexto do ativo selecionado
const STEPS = [
  {
    key: "sensor",
    n: 1,
    title: "Sensor",
    plain: "O motor é medido",
    ico: "🛰️",
    tech: "ESP32 · DHT22 / MPU6050 / potenciômetro",
    detail: ({ asset }) =>
      `Coleta física no ${asset ? asset.tag : "motor"}: temperatura, vibração, corrente e rotação a ~1 leitura por segundo.`,
  },
  {
    key: "broker",
    n: 2,
    title: "Transporte",
    plain: "A medição viaja em segurança",
    ico: "📡",
    tech: "HiveMQ (MQTT)",
    detail: () =>
      "Recebe a leitura enviada pelo sensor e a entrega à nuvem. Separa a coleta do processamento, sem perder nada no caminho.",
  },
  {
    key: "ingestao",
    n: 3,
    title: "Verificação",
    plain: "O dado é conferido na chegada",
    ico: "✓",
    tech: "n8n",
    detail: () =>
      "Confere se a leitura faz sentido, identifica de qual motor veio e a registra de forma padronizada.",
  },
  {
    key: "supabase",
    n: 4,
    title: "Registro",
    plain: "Fica guardado como histórico",
    ico: "🗄️",
    tech: "PostgreSQL · assets + readings",
    detail: ({ reading }) =>
      reading
        ? `Última leitura guardada: ${reading.temperature} °C · ${reading.vibration} m/s² · ${reading.current} A · ${reading.rotation} RPM.`
        : "Banco de dados com o cadastro dos motores e todas as leituras — a fonte da verdade consultada pelo painel.",
  },
  {
    key: "interface",
    n: 5,
    title: "Painel",
    plain: "Você vê o motor aqui",
    ico: "🖥️",
    tech: "React + Recharts",
    detail: ({ asset }) =>
      asset
        ? `Abrindo o ${asset.tag} você vê a leitura atual, o gráfico ao vivo e a ficha técnica.`
        : "Navegue Planta → Setor → Motor e veja a leitura atual mais a série histórica.",
  },
  {
    key: "decisao",
    n: 6,
    title: "Decisão",
    plain: "Vira uma recomendação",
    ico: "🎯",
    tech: "Alerta + recomendação + procedência",
    detail: ({ status }) => recommendation(status),
  },
];

const STATUS_CLS = { normal: "ok", alerta: "alerta", critico: "critico", desconhecido: "neutro" };

export default function DataPipeline({ tag }) {
  const [active, setActive] = useState("sensor");

  const asset = tag ? getAsset(tag) : null;
  const reading = tag ? latestReading(tag) : null;
  const status = tag ? assetStatus(tag) : "desconhecido";
  const ctx = { asset, reading, status };

  const activeStep = STEPS.find((s) => s.key === active);
  const ledCls = STATUS_CLS[status] ?? "neutro";

  return (
    <section className="panel" style={{ padding: 16 }}>
      <style>{`
        .dp-flow { display:flex; align-items:stretch; flex-wrap:wrap; gap:6px; }
        .dp-step {
          display:flex; flex-direction:column; gap:4px; min-width:128px; flex:1 1 128px;
          background: linear-gradient(180deg, var(--panel-2), var(--panel));
          border:1px solid var(--stroke); border-radius:12px;
          color: var(--texto-fraco); cursor:pointer; padding:10px 12px; text-align:left;
          transition: border-color .15s ease, transform .15s ease, box-shadow .15s ease;
        }
        .dp-step:hover { border-color: var(--roxo-claro); transform: translateY(-1px); }
        .dp-step.is-active {
          border-color: var(--roxo); color: var(--texto);
          box-shadow: 0 0 0 1px var(--roxo) inset, 0 0 18px rgba(124,58,237,.28);
          background: linear-gradient(180deg, var(--surface-3), var(--surface-2));
        }
        .dp-step .dp-head { display:flex; align-items:center; gap:6px; }
        .dp-step .dp-n {
          font-size:10px; font-weight:700; color: var(--roxo-claro);
          border:1px solid var(--stroke); border-radius:6px; padding:1px 5px;
          font-variant-numeric: tabular-nums;
        }
        .dp-step .dp-ico { font-size:13px; }
        .dp-step .dp-plain { font-size:13.5px; font-weight:700; line-height:1.25; color: inherit; }
        .dp-step .dp-tech { font-size:10.5px; color: var(--texto-fraco); opacity:.85;
          font-family: ui-monospace, Menlo, monospace; }
        .dp-arrow { color: var(--stroke); align-self:center; padding:0 1px; font-size:14px; }
        @media (max-width: 760px){ .dp-arrow{ display:none; } }
      `}</style>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
        <span className={`led ${ledCls} pulse`} />
        <h2 style={{ margin: 0, fontSize: 16 }}>Como esse dado chegou até aqui</h2>
      </div>
      <p className="muted small" style={{ margin: "2px 0 14px" }}>
        O caminho da medição, do motor até a recomendação. Toque numa etapa para entender.
        {asset ? <> Acompanhando <strong style={{ color: "var(--texto)" }}>{asset.tag}</strong>.</> : null}
      </p>

      {/* Trilha de etapas — lidera pelo rótulo humano, nome técnico abaixo */}
      <div className="dp-flow">
        {STEPS.map((s, i) => {
          const isActive = s.key === active;
          return (
            <div key={s.key} style={{ display: "contents" }}>
              <button
                className={`dp-step${isActive ? " is-active" : ""}`}
                onClick={() => setActive(s.key)}
                aria-pressed={isActive}
              >
                <div className="dp-head">
                  <span className="dp-n">{s.n}</span>
                  <span className="dp-ico" aria-hidden="true">{s.ico}</span>
                </div>
                <span className="dp-plain">{s.plain}</span>
                <span className="dp-tech">{s.title} · {s.tech}</span>
              </button>
              {i < STEPS.length - 1 && <span className="dp-arrow" aria-hidden="true">›</span>}
            </div>
          );
        })}
      </div>

      {/* Detalhe da etapa ativa */}
      {activeStep && (
        <div
          style={{
            marginTop: 14,
            background: "linear-gradient(180deg, var(--surface-2), var(--surface))",
            border: "1px solid var(--stroke)",
            borderRadius: 12,
            padding: "12px 14px",
          }}
        >
          <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
            <span className="dp-n" style={{ fontSize: 11 }}>{activeStep.n}</span>
            <strong style={{ fontSize: 14 }}>{activeStep.plain}</strong>
          </div>
          <p style={{ margin: "8px 0 0", fontSize: 13.5, lineHeight: 1.55 }}>
            {activeStep.detail(ctx)}
          </p>
          {/* Detalhe técnico — camada secundária, mono e discreta */}
          <p
            className="muted"
            style={{
              margin: "8px 0 0",
              fontSize: 11.5,
              fontFamily: "ui-monospace, Menlo, monospace",
              opacity: 0.8,
            }}
          >
            detalhes técnicos · {activeStep.title} · {activeStep.tech}
            {activeStep.key === "decisao" ? ` · estado: ${statusLabel(status)}` : ""}
          </p>
        </div>
      )}
    </section>
  );
}
