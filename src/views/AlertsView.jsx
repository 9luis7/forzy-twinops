// AlertsView.jsx — Cena 3 (parte 1): central de alertas. O alerta crítico do
// MTR-BMB-042 fica em destaque com confiança, origem e base consultada — a leitura
// virando decisão auditável. Clicar leva ao ativo (timeline + evidências).

import { alerts, getAsset, assetRisk } from "../data/mock.js";
import { RiskTag } from "../components/ui.jsx";

function FeaturedAlert({ alert, nav }) {
  const asset = getAsset(alert.tag);
  const risk = assetRisk(alert.tag);
  return (
    <div className={`alert-banner ${alert.severity}`}>
      <div className="alert-icon">{alert.severity === "critico" ? "🚨" : "⚠️"}</div>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span className="mono small">{alert.id}</span>
          <span className="alert-title">{alert.title}</span>
          <span className="pill">{alert.status}</span>
        </div>
        <div className="alert-msg">{alert.message}</div>

        <div className="alert-meta">
          <span>Ativo: <b className="mono">{alert.tag}</b> · {asset?.name}</span>
          <span>Origem: <b className="mono">{alert.origin}</b></span>
          <span>Risco: <b><RiskTag level={risk.level} /></b></span>
          {risk.windowHours && <span>Janela: <b>{risk.windowHours}h</b></span>}
        </div>

        <div style={{ display: "flex", gap: 28, flexWrap: "wrap", alignItems: "flex-end", marginTop: 6 }}>
          <div className="conf-wrap" style={{ marginTop: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
              <span className="muted">Confiança do modelo</span>
              <b>{alert.confidence}%</b>
            </div>
            <div className="conf-track" style={{ marginTop: 5 }}>
              <div className="conf-fill" style={{ width: `${alert.confidence}%` }} />
            </div>
          </div>
          <div className="small">
            <div className="muted">Base consultada</div>
            <div>{alert.bases.join(" + ")}</div>
          </div>
          <button className="btn primary" onClick={() => nav.goAsset(alert.tag)}>
            Abrir ativo · ver evidências →
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AlertsView({ nav }) {
  const [featured, ...rest] = alerts;
  return (
    <div>
      <div className="topbar">
        <div>
          <h1 className="page-title">Alertas</h1>
          <p className="page-sub">Detecções preditivas com origem rastreável e nível de confiança.</p>
        </div>
      </div>

      <FeaturedAlert alert={featured} nav={nav} />

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Demais alertas</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Severidade</th><th>ID</th><th>Ativo</th><th>Alerta</th>
              <th>Origem</th><th>Confiança</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rest.map((a) => {
              const asset = getAsset(a.tag);
              return (
                <tr key={a.id} className="clickable" onClick={() => nav.goAsset(a.tag)}>
                  <td>
                    <span className={`dot ${a.severity}`} style={{ width: 9, height: 9, marginRight: 6 }} />
                    {a.severity === "critico" ? "Crítico" : "Atenção"}
                  </td>
                  <td className="mono small">{a.id}</td>
                  <td className="mono">{a.tag}</td>
                  <td>{a.title} <span className="muted small">· {asset?.name}</span></td>
                  <td className="mono small">{a.origin}</td>
                  <td>{a.confidence}%</td>
                  <td><span className="pill">{a.status}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
