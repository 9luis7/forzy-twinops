// AssetPanel.jsx — ficha técnica + leitura atual (temp, corrente, vibração, rotação) + estado.
// Consome a TAG selecionada (prop `tag`) e lê do mock: getAsset, latestReading, assetStatus.

import { getAsset, latestReading, assetStatus } from "../data/mock.js";

const STATUS_META = {
  normal: { label: "Normal", color: "var(--ok)" },
  alerta: { label: "Alerta", color: "var(--alerta)" },
  critico: { label: "Crítico", color: "var(--critico)" },
  desconhecido: { label: "Desconhecido", color: "var(--texto-fraco)" },
};

// Cards de leitura instantânea. `tone` realça métricas fora da faixa.
function ReadingCard({ label, value, unit, tone = "var(--texto)" }) {
  return (
    <div
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--borda)",
        borderRadius: 10,
        padding: "12px 14px",
        flex: "1 1 120px",
      }}
    >
      <div style={{ color: "var(--texto-fraco)", fontSize: 12 }}>{label}</div>
      <div style={{ marginTop: 4, fontSize: 22, fontWeight: 600, color: tone }}>
        {value}
        <span style={{ fontSize: 13, fontWeight: 400, color: "var(--texto-fraco)" }}>
          {" "}
          {unit}
        </span>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div style={{ display: "flex", gap: 8, fontSize: 13, marginBottom: 4 }}>
      <span style={{ color: "var(--texto-fraco)", minWidth: 64 }}>{label}</span>
      <span>{children}</span>
    </div>
  );
}

// Limiares para realce visual (espelham os do mock).
const TEMP_WARN = 65;
const TEMP_CRIT = 75;
const VIB_WARN = 4.5;
const VIB_CRIT = 6;

const tempTone = (t) =>
  t >= TEMP_CRIT ? "var(--critico)" : t >= TEMP_WARN ? "var(--alerta)" : "var(--texto)";
const vibTone = (v) =>
  v >= VIB_CRIT ? "var(--critico)" : v >= VIB_WARN ? "var(--alerta)" : "var(--texto)";

export default function AssetPanel({ tag }) {
  const asset = tag ? getAsset(tag) : null;
  const reading = tag ? latestReading(tag) : null;

  const wrap = {
    background: "var(--surface)",
    border: "1px solid var(--borda)",
    borderRadius: 12,
    padding: 16,
  };

  if (!asset) {
    return (
      <section style={wrap}>
        <h3 style={{ marginTop: 0 }}>Painel do ativo</h3>
        <p style={{ color: "var(--texto-fraco)", fontSize: 13 }}>
          Selecione um motor na árvore TAG.
        </p>
      </section>
    );
  }

  const status = assetStatus(tag);
  const meta = STATUS_META[status] ?? STATUS_META.desconhecido;
  const when = reading ? new Date(reading.ts).toLocaleString("pt-BR") : "—";

  return (
    <section style={wrap}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>
          <span style={{ fontFamily: "monospace", color: "var(--laranja)" }}>{asset.tag}</span>{" "}
          {asset.name}
        </h3>
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: meta.color,
            border: `1px solid ${meta.color}`,
            borderRadius: 999,
            padding: "2px 10px",
          }}
        >
          ● {meta.label}
        </span>
      </div>

      {/* Ficha técnica */}
      <div style={{ marginTop: 12 }}>
        <Field label="Tipo">{asset.motor_type}</Field>
        <Field label="Setor">{asset.sector}</Field>
        {asset.note && (
          <Field label="Nota">
            <span style={{ color: "var(--texto-fraco)" }}>{asset.note}</span>
          </Field>
        )}
      </div>

      {/* Leitura atual */}
      <div style={{ marginTop: 14 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginBottom: 8,
          }}
        >
          <strong style={{ fontSize: 14 }}>Leitura atual</strong>
          <span style={{ color: "var(--texto-fraco)", fontSize: 12 }}>{when}</span>
        </div>

        {reading ? (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <ReadingCard
              label="Temperatura"
              value={reading.temperature}
              unit="°C"
              tone={tempTone(reading.temperature)}
            />
            <ReadingCard label="Corrente" value={reading.current} unit="A" />
            <ReadingCard
              label="Vibração"
              value={reading.vibration}
              unit="m/s²"
              tone={vibTone(reading.vibration)}
            />
            <ReadingCard label="Rotação" value={reading.rotation} unit="RPM" />
          </div>
        ) : (
          <p style={{ color: "var(--texto-fraco)", fontSize: 13 }}>Sem leituras.</p>
        )}
      </div>
    </section>
  );
}
