// AlertsView.jsx — Central de alertas (sala de controle). O alerta crítico do
// MTR-BMB-042 fica em destaque com confiança, origem e base consultada — a leitura
// virando decisão auditável. Clicar leva ao ativo (timeline + evidências).
// Linguagem humana primeiro; TAGs/origens técnicas como camada secundária (mono).

import { alerts, getAsset, assetRisk } from "../data/mock.js";
import { RiskTag } from "../components/ui.jsx";

// Rótulo humano por severidade (jargão "critico/alerta" -> texto claro).
const SEV_LABEL = { critico: "Crítico", alerta: "Atenção" };
const SEV_TEXT = { critico: "var(--critico)", alerta: "var(--alerta)" };

function FeaturedAlert({ alert, nav }) {
  const asset = getAsset(alert.tag);
  const risk = assetRisk(alert.tag);
  const crit = alert.severity === "critico";
  return (
    <div className={`alert-banner ${alert.severity}`} data-tour="featured-alert">
      <div className="alert-icon" aria-hidden>
        <span className={`led ${alert.severity} pulse`} style={{ width: 16, height: 16 }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Significado em linguagem clara primeiro; ID e status como detalhe. */}
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span
            style={{ fontWeight: 800, fontSize: 11.5, letterSpacing: ".6px", textTransform: "uppercase", color: SEV_TEXT[alert.severity] }}
          >
            {SEV_LABEL[alert.severity] ?? "Alerta"}
          </span>
          <span className="alert-title">{alert.title}</span>
          <span className="pill">{alert.status}</span>
          <span className="mono small" style={{ marginLeft: "auto", opacity: .7 }}>{alert.id}</span>
        </div>
        <div className="alert-msg">{alert.message}</div>

        <div className="alert-meta">
          <span>
            Ativo: <b>{asset?.name ?? "—"}</b>{" "}
            <span className="mono" style={{ fontSize: 11, opacity: .75 }}>· {alert.tag}</span>
          </span>
          <span>
            Detectado por: <b>sensor de vibração</b>{" "}
            <span className="mono" style={{ fontSize: 11, opacity: .75 }}>· {alert.origin}</span>
          </span>
          <span>Risco: <b><RiskTag level={risk.level} /></b></span>
          {risk.windowHours && <span>Janela recomendada: <b>{risk.windowHours}h</b></span>}
        </div>

        <div style={{ display: "flex", gap: 28, flexWrap: "wrap", alignItems: "flex-end", marginTop: 12 }}>
          <div className="conf-wrap" style={{ marginTop: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
              <span className="muted">Confiança do modelo</span>
              <b className="readout" style={{ fontSize: 13, color: crit ? "var(--critico)" : "var(--alerta)" }}>
                {alert.confidence}%
              </b>
            </div>
            <div className="conf-track" style={{ marginTop: 5 }}>
              <div className="conf-fill" style={{ width: `${alert.confidence}%` }} />
            </div>
          </div>
          <div className="small">
            <div className="muted" style={{ textTransform: "uppercase", letterSpacing: ".4px", fontSize: 11 }}>
              Base consultada
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
              {alert.bases.map((b) => (
                <span key={b} className="pill" style={{ fontSize: 11 }}>{b}</span>
              ))}
            </div>
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
    <div data-tour="alerts-view">
      <div className="topbar">
        <div>
          <h1 className="page-title">Central de alertas</h1>
          <p className="page-sub">
            Detecções preditivas em linguagem clara — com origem rastreável e nível de confiança do modelo.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="led ok pulse" />
          <span className="small muted">Monitoramento ativo</span>
        </div>
      </div>

      <FeaturedAlert alert={featured} nav={nav} />

      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          Demais alertas
          <span className="pill" style={{ fontSize: 11 }}>{rest.length}</span>
        </h3>
        <table className="table">
          <thead>
            <tr>
              <th>Severidade</th>
              <th>Alerta</th>
              <th>Ativo</th>
              <th>Detectado por</th>
              <th>Confiança</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rest.map((a) => {
              const asset = getAsset(a.tag);
              const crit = a.severity === "critico";
              return (
                <tr key={a.id} className="clickable" onClick={() => nav.goAsset(a.tag)}>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                      <span className={`led ${a.severity}${crit ? " pulse" : ""}`} />
                      <span style={{ fontWeight: 700, color: SEV_TEXT[a.severity] }}>
                        {SEV_LABEL[a.severity] ?? "Alerta"}
                      </span>
                    </span>
                  </td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{a.title}</div>
                    <div className="muted small mono" style={{ fontSize: 10.5, marginTop: 2, opacity: .75 }}>
                      {a.id}
                    </div>
                  </td>
                  <td>
                    <div>{asset?.name ?? "—"}</div>
                    <div className="muted small mono" style={{ fontSize: 10.5, marginTop: 2, opacity: .75 }}>
                      {a.tag}
                    </div>
                  </td>
                  <td>
                    <div className="small">sensor de vibração</div>
                    <div className="muted small mono" style={{ fontSize: 10.5, marginTop: 2, opacity: .75 }}>
                      {a.origin}
                    </div>
                  </td>
                  <td>
                    <span className="readout" style={{ fontSize: 14, color: crit ? "var(--critico)" : "var(--alerta)" }}>
                      {a.confidence}%
                    </span>
                  </td>
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
