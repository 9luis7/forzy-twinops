// Provenance.jsx — trilha de auditoria por leitura: de onde veio cada número,
// por onde passou, qual sensor/doc embasa e o estado da validação humana.
// Fecha a etapa [6] DECISÃO: o dado vira decisão com origem rastreável.

import {
  getAsset,
  getArea,
  latestReading,
  assetStatus,
  statusLabel,
} from "../data/mock.js";

// Faixa válida por métrica (clamp físico do pipeline).
const RANGES = {
  temperature: { label: "Temperatura", unit: "°C", type: "Temperatura", range: [35, 92] },
  vibration: { label: "Vibração", unit: "m/s²", type: "Vibração", range: [0.4, 8] },
  current: { label: "Corrente", unit: "A", type: "Corrente", range: [0, 60] },
  rotation: { label: "Rotação", unit: "RPM", type: "Controlador", range: [0, 4000] },
};
const ORDER = ["temperature", "vibration", "current", "rotation"];

const VALIDATION = {
  critico: { label: "Pendente — aguarda parecer do técnico", color: "var(--critico)" },
  alerta: { label: "Em análise pela equipe de manutenção", color: "var(--alerta)" },
  normal: { label: "Confirmado automaticamente (dentro da faixa)", color: "var(--ok)" },
  desconhecido: { label: "Sem validação", color: "var(--texto-fraco)" },
};

const inRange = (v, [lo, hi]) => v >= lo && v <= hi;

function Row({ children }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1.1fr 1.1fr 0.9fr 0.9fr 0.4fr",
        gap: 8,
        padding: "7px 0",
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

  if (!asset || !reading) {
    return (
      <section className="card">
        <h3>Procedência / auditoria</h3>
        <p className="muted small">Selecione um motor para ver a trilha de auditoria.</p>
      </section>
    );
  }

  const area = getArea(asset.area);
  const status = assetStatus(tag);
  const val = VALIDATION[status] ?? VALIDATION.desconhecido;
  const when = new Date(reading.ts).toLocaleString("pt-BR");
  const topic = `forzy/${(area?.name || "").toLowerCase()}/${asset.tag.toLowerCase()}`;
  const sensorFor = (type) => asset.sensors.find((s) => s.type === type)?.tag || "—";

  return (
    <section className="card">
      <h3>
        Procedência / auditoria{" "}
        <span className="muted small" style={{ fontWeight: 400 }}>· leitura de {when}</span>
      </h3>

      {/* Origem rastreável de cada número */}
      <div className="section-title">Origem rastreável da leitura</div>
      <div style={{ marginTop: 6 }}>
        <Row>
          <span className="muted">Métrica</span>
          <span className="muted">Sensor (TAG)</span>
          <span className="muted">Valor</span>
          <span className="muted">Faixa válida</span>
          <span className="muted">OK</span>
        </Row>
        {ORDER.map((key) => {
          const m = RANGES[key];
          const v = reading[key];
          const ok = inRange(v, m.range);
          return (
            <Row key={key}>
              <span>{m.label}</span>
              <span className="mono" style={{ fontSize: 12 }}>{sensorFor(m.type)}</span>
              <span>{v} {m.unit}</span>
              <span className="muted">{m.range[0]}–{m.range[1]}</span>
              <span style={{ color: ok ? "var(--ok)" : "var(--critico)" }}>{ok ? "✓" : "✗"}</span>
            </Row>
          );
        })}
      </div>

      {/* Trilha do dado */}
      <div style={{ marginTop: 16 }}>
        <div className="section-title">Trilha do dado</div>
        <ol style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13, color: "var(--texto-fraco)", lineHeight: 1.7 }}>
          <li>Capturado no <strong style={{ color: "var(--texto)" }}>{asset.tag}</strong> ({area?.name}) via ESP32</li>
          <li>Publicado em <code style={{ color: "var(--roxo-claro)" }}>{topic}</code> (HiveMQ / MQTT)</li>
          <li>Validado e inserido pelo n8n em <code>readings</code> (Supabase)</li>
          <li>Estado avaliado por limiar → <strong style={{ color: val.color }}>{statusLabel(status)}</strong></li>
        </ol>
      </div>

      {/* Metadados de auditoria (estilo painel da especificação) */}
      <div style={{ marginTop: 16 }}>
        <div className="section-title">Painel de auditoria</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2px 24px", marginTop: 8 }}>
          <div className="field"><span className="f-label">Coletado em</span><span>{when}</span></div>
          <div className="field"><span className="f-label">Fonte validada</span><span style={{ color: "var(--ok)" }}>Sim</span></div>
          <div className="field"><span className="f-label">Usado na recomendação</span><span style={{ color: status === "normal" ? "var(--texto-fraco)" : "var(--ok)" }}>{status === "normal" ? "Não" : "Sim"}</span></div>
          <div className="field"><span className="f-label">Validação humana</span>
            <span style={{ color: val.color }}>{val.label}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
