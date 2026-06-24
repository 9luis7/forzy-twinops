// PlantOverview.jsx — Cena 1: visão macro. KPIs da planta + mapa de áreas clicáveis.
// É o ponto de partida do drill-down macro→micro.

import {
  PLANT,
  areas,
  kpis,
  assetsByArea,
  assetStatus,
  alerts,
  getAsset,
} from "../data/mock.js";
import { StatusBadge } from "../components/ui.jsx";

const SEV_RANK = { critico: 3, alerta: 2, normal: 1, desconhecido: 0 };

// Pior estado entre os ativos detalhados da área (resumo visual).
function areaStatus(areaTag) {
  const motors = assetsByArea(areaTag);
  if (!motors.length) return "desconhecido";
  return motors
    .map((m) => assetStatus(m.tag))
    .reduce((worst, s) => (SEV_RANK[s] > SEV_RANK[worst] ? s : worst), "normal");
}

function Kpi({ label, value, foot, tone }) {
  return (
    <div className={`kpi ${tone || ""}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-foot">{foot}</div>
    </div>
  );
}

export default function PlantOverview({ nav }) {
  return (
    <div>
      <div className="topbar">
        <div>
          <h1 className="page-title">Visão da Planta</h1>
          <p className="page-sub">
            <span className="mono">{PLANT.tag}</span> · {PLANT.name} — {PLANT.location}
          </p>
        </div>
      </div>

      {/* KPIs */}
      <div className="kpi-row">
        <Kpi label="Ativos monitorados" value={kpis.monitoredAssets} foot="4 áreas · 6 conectados ao vivo" />
        <Kpi label="Alertas críticos" value={kpis.criticalAlerts} tone="crit" foot="1 com inspeção em 72h" />
        <Kpi label="Manutenções previstas" value={kpis.plannedMaintenance} tone="warn" foot="próximos 30 dias" />
        <Kpi label="Confiabilidade dos dados" value={`${kpis.dataReliability}%`} tone="ok" foot="leituras validadas na fonte" />
      </div>

      {/* Mapa de áreas */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3>Mapa da planta · áreas</h3>
        <p className="muted small" style={{ marginTop: -6 }}>
          Partimos do macro para o micro. Clique numa área para descer até o ativo.
        </p>
        <div className="area-grid" style={{ marginTop: 12 }}>
          {areas.map((area) => {
            const motors = assetsByArea(area.tag);
            const st = areaStatus(area.tag);
            return (
              <button key={area.tag} className="area-card" onClick={() => nav.goArea(area.tag)}>
                <div className="area-head">
                  <div className="area-letter">{area.letter}</div>
                  <div style={{ flex: 1 }}>
                    <div className="area-name">{area.icon} {area.name}</div>
                    <div className="area-tag">{area.tag}</div>
                  </div>
                  <StatusBadge status={st} />
                </div>
                <div className="area-meta">
                  <div>Ativos<b>{area.assetsCount}</b></div>
                  <div>Conectados<b>{motors.length}</b></div>
                  <div>Estado<b style={{ fontSize: 13, fontWeight: 600 }}>
                    {motors.length ? "monitorado" : "planejado"}
                  </b></div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Alertas recentes */}
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>Alertas recentes</h3>
          <button className="link-btn" onClick={() => nav.goView("alertas")}>ver todos →</button>
        </div>
        <table className="table" style={{ marginTop: 10 }}>
          <thead>
            <tr><th>Severidade</th><th>Ativo</th><th>Alerta</th><th>Confiança</th></tr>
          </thead>
          <tbody>
            {alerts.map((a) => {
              const asset = getAsset(a.tag);
              return (
                <tr key={a.id} className="clickable" onClick={() => nav.goAsset(a.tag)}>
                  <td><span className={`dot ${a.severity}`} style={{ width: 9, height: 9, marginRight: 6 }} />
                    {a.severity === "critico" ? "Crítico" : "Atenção"}</td>
                  <td className="mono">{a.tag}</td>
                  <td>{a.title} <span className="muted small">· {asset?.name}</span></td>
                  <td>{a.confidence}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
