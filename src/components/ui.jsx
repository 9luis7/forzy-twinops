// ui.jsx — peças visuais compartilhadas (badge de status, barra de confiança).
import { statusLabel } from "../data/mock.js";

// Badge de estado operacional: normal | alerta | critico | desconhecido.
export function StatusBadge({ status }) {
  const cls = ["normal", "alerta", "critico"].includes(status) ? status : "neutro";
  return (
    <span className={`badge ${cls}`}>
      <span className={`dot ${cls}`} style={{ width: 8, height: 8 }} />
      {statusLabel(status)}
    </span>
  );
}

// Barra de confiança (0–100%) para o output preditivo.
export function ConfidenceBar({ value }) {
  return (
    <div className="conf-wrap">
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
        <span className="muted">Confiança do modelo</span>
        <b>{value}%</b>
      </div>
      <div className="conf-track" style={{ marginTop: 5 }}>
        <div className="conf-fill" style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

// Cor textual por nível de risco.
export function RiskTag({ level }) {
  const map = {
    Baixo: "var(--ok)",
    Médio: "var(--alerta)",
    "Médio/Alto": "var(--alerta)",
    Alto: "var(--critico)",
  };
  const color = map[level] ?? "var(--texto-fraco)";
  return (
    <span style={{ color, fontWeight: 700 }}>{level}</span>
  );
}
