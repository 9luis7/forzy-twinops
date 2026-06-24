// Provenance.jsx — trilha de auditoria por leitura: de onde veio cada número,
// por onde passou, qual doc embasa a leitura e o estado da validação humana.
// Fecha a etapa [6] DECISÃO: o dado vira decisão com origem rastreável.

import { getAsset, latestReading, assetStatus } from "../data/mock.js";

// Cada métrica da leitura é atribuída ao sensor físico que a produz + faixa válida.
// (espelha o pipeline: ESP32 + DHT22 / MPU6050 / clamp de corrente / encoder)
const SOURCES = [
  { key: "temperature", label: "Temperatura", unit: "°C", sensor: "DHT22", range: [35, 85] },
  { key: "vibration", label: "Vibração", unit: "m/s²", sensor: "MPU6050", range: [0.5, 8] },
  { key: "current", label: "Corrente", unit: "A", sensor: "Clamp / ACS712", range: [0, 60] },
  { key: "rotation", label: "Rotação", unit: "RPM", sensor: "Encoder óptico", range: [0, 4000] },
];

// Documentos que embasam a leitura (mock da camada de conhecimento).
const DOCS = [
  { label: "Datasheet do motor", meta: "PDF · ficha do fabricante" },
  { label: "ISO 10816-3", meta: "norma de severidade de vibração" },
  { label: "Plano de manutenção", meta: "histórico + periodicidade" },
];

// Estado da validação humana derivado do estado operacional.
const VALIDATION = {
  critico: { label: "Pendente — aguarda parecer do técnico", color: "var(--critico)" },
  alerta: { label: "Em análise pela equipe de manutenção", color: "var(--alerta)" },
  normal: { label: "Confirmado automaticamente (dentro da faixa)", color: "var(--ok)" },
  desconhecido: { label: "Sem validação", color: "var(--texto-fraco)" },
};

function inRange(v, [lo, hi]) {
  return v >= lo && v <= hi;
}

function Row({ children }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1.1fr 1fr 0.9fr 0.9fr 0.5fr",
        gap: 8,
        padding: "6px 0",
        borderBottom: "1px solid var(--borda)",
        fontSize: 13,
        alignItems: "center",
      }}
    >
      {children}
    </div>
  );
}

export default function Provenance({ tag }) {
  const asset = tag ? getAsset(tag) : null;
  const reading = tag ? latestReading(tag) : null;

  const wrap = {
    background: "var(--surface)",
    border: "1px solid var(--borda)",
    borderRadius: 12,
    padding: 16,
    marginTop: 16,
  };

  if (!asset || !reading) {
    return (
      <section style={wrap}>
        <h3 style={{ marginTop: 0 }}>Procedência / auditoria</h3>
        <p style={{ color: "var(--texto-fraco)", fontSize: 13 }}>
          Selecione um motor para ver a trilha de auditoria.
        </p>
      </section>
    );
  }

  const status = assetStatus(tag);
  const val = VALIDATION[status] ?? VALIDATION.desconhecido;
  const when = new Date(reading.ts).toLocaleString("pt-BR");
  const topic = `forzy/${asset.sector.toLowerCase()}/${asset.tag.toLowerCase()}`;

  return (
    <section style={wrap}>
      <h3 style={{ marginTop: 0 }}>
        Procedência / auditoria{" "}
        <span style={{ color: "var(--texto-fraco)", fontWeight: 400, fontSize: 13 }}>
          · leitura de {when}
        </span>
      </h3>

      {/* Origem rastreável de cada número da leitura */}
      <strong style={{ fontSize: 14 }}>Origem rastreável</strong>
      <div style={{ marginTop: 6 }}>
        <Row>
          <span style={{ color: "var(--texto-fraco)" }}>Métrica</span>
          <span style={{ color: "var(--texto-fraco)" }}>Sensor</span>
          <span style={{ color: "var(--texto-fraco)" }}>Valor</span>
          <span style={{ color: "var(--texto-fraco)" }}>Faixa válida</span>
          <span style={{ color: "var(--texto-fraco)" }}>OK</span>
        </Row>
        {SOURCES.map((s) => {
          const v = reading[s.key];
          const ok = inRange(v, s.range);
          return (
            <Row key={s.key}>
              <span>{s.label}</span>
              <span style={{ fontFamily: "monospace", fontSize: 12 }}>{s.sensor}</span>
              <span>
                {v} {s.unit}
              </span>
              <span style={{ color: "var(--texto-fraco)" }}>
                {s.range[0]}–{s.range[1]}
              </span>
              <span style={{ color: ok ? "var(--ok)" : "var(--critico)" }}>
                {ok ? "✓" : "✗"}
              </span>
            </Row>
          );
        })}
      </div>

      {/* Trilha: por onde o dado passou */}
      <div style={{ marginTop: 14 }}>
        <strong style={{ fontSize: 14 }}>Trilha do dado</strong>
        <ol
          style={{
            margin: "8px 0 0",
            paddingLeft: 18,
            fontSize: 13,
            color: "var(--texto-fraco)",
            lineHeight: 1.7,
          }}
        >
          <li>
            Capturado pelo ESP32 no{" "}
            <strong style={{ color: "var(--texto)" }}>{asset.tag}</strong> ({asset.sector})
          </li>
          <li>
            Publicado em <code style={{ color: "var(--roxo-claro)" }}>{topic}</code> (HiveMQ)
          </li>
          <li>
            Validado e inserido pelo n8n em <code>readings</code> (Supabase)
          </li>
          <li>
            Estado avaliado por limiar →{" "}
            <strong style={{ color: val.color }}>{status}</strong>
          </li>
        </ol>
      </div>

      {/* Documentos de apoio */}
      <div style={{ marginTop: 14 }}>
        <strong style={{ fontSize: 14 }}>Documentos de apoio</strong>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          {DOCS.map((d) => (
            <div
              key={d.label}
              title={d.meta}
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--borda)",
                borderRadius: 8,
                padding: "6px 10px",
                fontSize: 12,
              }}
            >
              📄 {d.label}
              <div style={{ color: "var(--texto-fraco)", fontSize: 11 }}>{d.meta}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Validação humana */}
      <div
        style={{
          marginTop: 14,
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 13,
          flexWrap: "wrap",
        }}
      >
        <strong>Validação humana:</strong>
        <span
          style={{
            color: val.color,
            border: `1px solid ${val.color}`,
            borderRadius: 999,
            padding: "2px 10px",
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          {val.label}
        </span>
      </div>
    </section>
  );
}
