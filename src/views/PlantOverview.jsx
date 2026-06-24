// PlantOverview.jsx — Cena 1: sala de controle (SCADA) no nível da planta.
// O sinótico AO VIVO (PlantSynoptic) é a estrela: mímico de cima das 4 áreas com os
// motores conectados. Acima, KPIs como mostradores de instrumento; abaixo, uma lista
// compacta de áreas e os alertas recentes em linguagem clara (texto humano primeiro,
// TAG como detalhe técnico secundário). Ponto de partida do drill-down macro→micro.

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
import PlantSynoptic from "../components/PlantSynoptic.jsx";

const SEV_RANK = { critico: 3, alerta: 2, normal: 1, desconhecido: 0 };

// Pior estado entre os ativos detalhados da área (resumo visual).
function areaStatus(areaTag) {
  const motors = assetsByArea(areaTag);
  if (!motors.length) return "desconhecido";
  return motors
    .map((m) => assetStatus(m.tag))
    .reduce((worst, s) => (SEV_RANK[s] > SEV_RANK[worst] ? s : worst), "normal");
}

// Mostrador de instrumento: número grande (.readout) + rótulo + rodapé curto.
function Kpi({ label, value, foot, tone, readoutTone }) {
  return (
    <div className={`kpi ${tone || ""}`}>
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value readout ${readoutTone || ""}`}>{value}</div>
      <div className="kpi-foot">{foot}</div>
    </div>
  );
}

export default function PlantOverview({ nav }) {
  return (
    <div>
      <div className="topbar">
        <div>
          <h1 className="page-title">Sala de controle · Visão da planta</h1>
          <p className="page-sub">
            {PLANT.name} — {PLANT.location}{" "}
            <span className="mono" style={{ color: "var(--texto-fraco)" }}>
              {PLANT.tag}
            </span>
          </p>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 9,
            alignSelf: "center",
          }}
        >
          <span className="led ok pulse" />
          <span style={{ fontSize: 12.5, color: "var(--texto-fraco)" }}>
            Monitoramento ativo · em tempo real
          </span>
        </div>
      </div>

      {/* KPIs — mostradores de instrumento, números em destaque, rodapé curto. */}
      <div className="kpi-row">
        <Kpi
          label="Ativos monitorados"
          value={kpis.monitoredAssets}
          foot="4 áreas · 6 ao vivo"
        />
        <Kpi
          label="Alertas críticos"
          value={kpis.criticalAlerts}
          tone="crit"
          readoutTone="crit"
          foot="exigem ação imediata"
        />
        <Kpi
          label="Manutenções previstas"
          value={kpis.plannedMaintenance}
          tone="warn"
          readoutTone="warn"
          foot="próximos 30 dias"
        />
        <Kpi
          label="Confiança dos dados"
          value={`${kpis.dataReliability}%`}
          tone="ok"
          readoutTone="ok"
          foot="leituras validadas"
        />
      </div>

      {/* Sinótico AO VIVO — a estrela da visão geral. */}
      <div style={{ marginTop: 16 }}>
        <p className="muted small" style={{ margin: "0 0 8px 2px" }}>
          Este é o mapa vivo da fábrica vista de cima. Cada zona é uma área da
          planta; os motorzinhos são os equipamentos monitorados. Clique num
          motor para abri-lo ou numa zona para ver a área inteira.
        </p>
        <PlantSynoptic nav={nav} />
      </div>

      {/* Lista compacta de áreas (atalho rápido por número). */}
      <div className="card" style={{ marginTop: 16 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <h3 style={{ margin: 0 }}>Áreas da planta</h3>
          <span className="muted small">do macro para o micro</span>
        </div>
        <div className="area-grid" style={{ marginTop: 12 }}>
          {areas.map((area) => {
            const motors = assetsByArea(area.tag);
            const st = areaStatus(area.tag);
            return (
              <button
                key={area.tag}
                className="area-card"
                onClick={() => nav.goArea(area.tag)}
              >
                <div className="area-head">
                  <div className="area-letter">{area.letter}</div>
                  <div style={{ flex: 1 }}>
                    <div className="area-name">
                      {area.icon} {area.name}
                    </div>
                    <div className="area-tag mono">{area.tag}</div>
                  </div>
                  <StatusBadge status={st} />
                </div>
                <div className="area-meta">
                  <div>
                    Ativos<b>{area.assetsCount}</b>
                  </div>
                  <div>
                    Conectados<b>{motors.length}</b>
                  </div>
                  <div>
                    Estado
                    <b style={{ fontSize: 13, fontWeight: 600 }}>
                      {motors.length ? "monitorado" : "planejado"}
                    </b>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Alertas recentes — texto humano primeiro, TAG como detalhe técnico. */}
      <div className="card">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <h3 style={{ margin: 0 }}>Alertas recentes</h3>
          <button className="link-btn" onClick={() => nav.goView("alertas")}>
            ver todos →
          </button>
        </div>

        <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
          {alerts.map((a) => {
            const asset = getAsset(a.tag);
            const crit = a.severity === "critico";
            return (
              <button
                key={a.id}
                className="alert-row"
                onClick={() => nav.goAsset(a.tag)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  width: "100%",
                  textAlign: "left",
                  background: "linear-gradient(180deg, var(--panel-2), var(--panel))",
                  border: "1px solid var(--stroke)",
                  borderLeft: `3px solid ${
                    crit ? "var(--critico)" : "var(--alerta)"
                  }`,
                  borderRadius: 12,
                  padding: "12px 14px",
                  cursor: "pointer",
                }}
              >
                <span
                  className={`led ${a.severity} pulse`}
                  style={{ marginTop: 1 }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* Significado em linguagem clara primeiro. */}
                  <div style={{ fontWeight: 600, color: "var(--texto)" }}>
                    {a.title}
                  </div>
                  <div
                    className="small"
                    style={{ color: "var(--texto-fraco)", marginTop: 2 }}
                  >
                    {asset?.name || "Ativo"}{" "}
                    <span
                      className="mono"
                      style={{ fontSize: 11, opacity: 0.85 }}
                    >
                      · {a.tag}
                    </span>
                  </div>
                </div>
                {/* Severidade + confiança como camada secundária à direita. */}
                <div
                  style={{
                    textAlign: "right",
                    flexShrink: 0,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "flex-end",
                    gap: 3,
                  }}
                >
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 700,
                      color: crit ? "var(--critico)" : "var(--alerta)",
                    }}
                  >
                    {crit ? "Crítico" : "Atenção"}
                  </span>
                  <span
                    className="readout small"
                    style={{ color: "var(--texto-fraco)", fontWeight: 600 }}
                  >
                    {a.confidence}% confiança
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
