// Provenance.jsx — trilha de auditoria por leitura: de onde veio cada número
// (procedência), se foi adulterado (integridade), por onde passou (rastreabilidade)
// e quem assinou (trilha de auditoria). Fecha a etapa [6] DECISÃO.

import {
  getAsset,
  getArea,
  getComponent,
  latestReading,
  assetStatus,
  statusLabel,
  auditMeta,
  kpis,
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

function Group({ ico, title, children }) {
  return (
    <div className="audit-group">
      <div className="ag-title">
        <span className="ag-ico">{ico}</span>
        {title}
      </div>
      {children}
    </div>
  );
}

function KV({ label, children, mono }) {
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className={`kv-value${mono ? " mono" : ""}`}>{children}</span>
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
  const meta = auditMeta(tag);
  const component = meta.componentTag ? getComponent(meta.componentTag) : null;
  const allInRange = ORDER.every((k) => inRange(reading[k], RANGES[k].range));
  const usedInRec = status !== "normal";

  return (
    <section className="card">
      <h3>
        Procedência &amp; trilha de auditoria{" "}
        <span className="muted small" style={{ fontWeight: 400 }}>· leitura de {when}</span>
      </h3>

      {/* -------------------------------------------------------- PROCEDÊNCIA */}
      <Group ico="📍" title="Procedência — de onde veio o dado">
        <div className="kv-grid">
          <KV label="Planta / área">{area?.name} ({area?.tag})</KV>
          <KV label="Ativo monitorado" mono>{asset.tag}</KV>
          <KV label="Equipamento pai" mono>{meta.parentAssetTag}</KV>
          <KV label="Componente">
            {component ? (
              <span><span className="mono">{component.tag}</span> · {component.name}</span>
            ) : "—"}
          </KV>
          <KV label="Sensores de origem" mono>{meta.sourceSensorTags.join(" + ") || "—"}</KV>
          <KV label="Tópico MQTT" mono>{topic}</KV>
        </div>
      </Group>

      {/* -------------------------------------------------------- INTEGRIDADE */}
      <Group ico="🔒" title="Integridade — o dado não foi adulterado">
        <div className="kv-grid" style={{ marginBottom: 8 }}>
          <KV label="Input hash" mono>{meta.inputHash}</KV>
          <KV label="Confiabilidade do dado">
            <span style={{ color: "var(--ok)" }}>{kpis.dataReliability}%</span>
          </KV>
          <KV label="Fonte validada"><span style={{ color: "var(--ok)" }}>Sim</span></KV>
          <KV label="Leituras na faixa válida">
            <span style={{ color: allInRange ? "var(--ok)" : "var(--critico)" }}>
              {allInRange ? "Todas ✓" : "Há desvio ✗"}
            </span>
          </KV>
        </div>
        <div style={{ marginTop: 4 }}>
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
      </Group>

      {/* ----------------------------------------------------- RASTREABILIDADE */}
      <Group ico="🧭" title="Rastreabilidade — por onde o dado passou">
        <div className="kv-grid">
          <KV label="Trace ID" mono>{meta.traceId}</KV>
          <KV label="Pipeline" mono>{meta.pipelineVersion}</KV>
          <KV label="Modelo de scoring" mono>{meta.scoringModel}</KV>
          <KV label="Usado na recomendação">
            <span style={{ color: usedInRec ? "var(--ok)" : "var(--texto-fraco)" }}>
              {usedInRec ? "Sim" : "Não"}
            </span>
          </KV>
        </div>
        <ol style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 13, color: "var(--texto-fraco)", lineHeight: 1.7 }}>
          <li>Capturado no <strong style={{ color: "var(--texto)" }}>{asset.tag}</strong> ({area?.name}) via ESP32</li>
          <li>Publicado em <code style={{ color: "var(--roxo-claro)" }}>{topic}</code> (HiveMQ / MQTT)</li>
          <li>Validado e inserido pelo n8n em <code>readings</code> (Supabase)</li>
          <li>Pontuado por <code>{meta.scoringModel}</code> → estado <strong style={{ color: val.color }}>{statusLabel(status)}</strong></li>
        </ol>
      </Group>

      {/* ----------------------------------------------------- TRILHA DE AUDITORIA */}
      <Group ico="✍️" title="Trilha de auditoria — assinatura e validação">
        <div className="kv-grid">
          <KV label="Coletado em">{when}</KV>
          <KV label="Assinado por">{meta.signedBy}</KV>
          <KV label="Estado avaliado">
            <span style={{ color: val.color, fontWeight: 700 }}>{statusLabel(status)}</span>
          </KV>
          <KV label="Validação humana">
            <span style={{ color: val.color }}>{meta.humanValidation}</span>
          </KV>
        </div>
        <p className="muted small" style={{ marginTop: 8 }}>
          {val.label}.
        </p>
      </Group>
    </section>
  );
}
