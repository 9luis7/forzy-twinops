// DataPipeline.jsx — as 6 etapas clicáveis do ciclo de vida do dado.
// [1] SENSOR → [2] BROKER → [3] INGESTÃO → [4] SUPABASE → [5] INTERFACE → [6] DECISÃO
// Estrela do protótipo: clicar numa etapa abre o detalhe, ancorado no ativo selecionado.

import { useState } from "react";
import { getAsset, latestReading, assetStatus } from "../data/mock.js";

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

// Define as 6 etapas. `detail` recebe o contexto do ativo selecionado.
const STEPS = [
  {
    key: "sensor",
    n: 1,
    title: "Sensor",
    tech: "ESP32 + DHT22 / MPU6050 / potenciômetro",
    detail: ({ asset }) =>
      `Coleta física no ${asset ? asset.tag : "motor"}: temperatura, vibração, corrente e rotação a ~1 leitura/seg.`,
  },
  {
    key: "broker",
    n: 2,
    title: "Broker",
    tech: "HiveMQ (MQTT)",
    detail: () =>
      "Recebe o payload raw publicado pelo ESP32 no tópico do ativo. Desacopla coleta de processamento.",
  },
  {
    key: "ingestao",
    n: 3,
    title: "Ingestão",
    tech: "n8n",
    detail: () =>
      "Valida o payload, faz lookup da TAG em assets e insere a leitura normalizada em readings.",
  },
  {
    key: "supabase",
    n: 4,
    title: "Supabase",
    tech: "PostgreSQL · assets + readings",
    detail: ({ reading }) =>
      reading
        ? `Última linha persistida: ${reading.temperature} °C · ${reading.vibration} m/s² · ${reading.current} A · ${reading.rotation} RPM.`
        : "Tabelas assets e readings — fonte da verdade consultada pela interface.",
  },
  {
    key: "interface",
    n: 5,
    title: "Interface",
    tech: "React + Recharts",
    detail: ({ asset }) =>
      asset
        ? `Navega TAG → ${asset.tag} mostra leitura atual, gráfico temporal e ficha técnica.`
        : "Navega Planta → Setor → Motor e apresenta leitura atual + série histórica.",
  },
  {
    key: "decisao",
    n: 6,
    title: "Decisão",
    tech: "Alerta + recomendação + procedência",
    detail: ({ status }) => recommendation(status),
  },
];

export default function DataPipeline({ tag }) {
  const [active, setActive] = useState("sensor");

  const asset = tag ? getAsset(tag) : null;
  const reading = tag ? latestReading(tag) : null;
  const status = tag ? assetStatus(tag) : "desconhecido";
  const ctx = { asset, reading, status };

  const activeStep = STEPS.find((s) => s.key === active);

  return (
    <section
      style={{
        background: "var(--surface)",
        border: "1px solid var(--borda)",
        borderRadius: 12,
        padding: 16,
      }}
    >
      <h2 style={{ marginTop: 0 }}>
        Pipeline do dado{" "}
        <span style={{ color: "var(--texto-fraco)", fontWeight: 400, fontSize: 13 }}>
          · ciclo de vida {asset ? `· ${asset.tag}` : ""}
        </span>
      </h2>

      {/* Trilha de etapas */}
      <div style={{ display: "flex", alignItems: "stretch", flexWrap: "wrap", gap: 4 }}>
        {STEPS.map((s, i) => {
          const isActive = s.key === active;
          return (
            <div key={s.key} style={{ display: "flex", alignItems: "center" }}>
              <button
                onClick={() => setActive(s.key)}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 2,
                  minWidth: 110,
                  background: isActive ? "var(--surface-2)" : "transparent",
                  border: isActive ? "1px solid var(--roxo)" : "1px solid var(--borda)",
                  borderRadius: 10,
                  color: isActive ? "var(--texto)" : "var(--texto-fraco)",
                  cursor: "pointer",
                  padding: "8px 12px",
                  textAlign: "left",
                }}
              >
                <span style={{ fontSize: 11, color: "var(--roxo-claro)" }}>
                  [{s.n}]
                </span>
                <span style={{ fontSize: 14, fontWeight: 600 }}>{s.title}</span>
              </button>
              {i < STEPS.length - 1 && (
                <span style={{ color: "var(--texto-fraco)", padding: "0 4px" }}>→</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Detalhe da etapa ativa */}
      {activeStep && (
        <div
          style={{
            marginTop: 14,
            background: "var(--surface-2)",
            border: "1px solid var(--borda)",
            borderRadius: 10,
            padding: "12px 14px",
          }}
        >
          <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
            <strong>
              [{activeStep.n}] {activeStep.title}
            </strong>
            <span style={{ color: "var(--texto-fraco)", fontSize: 12 }}>{activeStep.tech}</span>
          </div>
          <p style={{ margin: "8px 0 0", fontSize: 13, lineHeight: 1.5 }}>
            {activeStep.detail(ctx)}
          </p>
        </div>
      )}
    </section>
  );
}
