// AssetProfile.jsx — "perfil" do ativo (cena 2). Identidade por TAG + leitura atual,
// risco preditivo, sensores, gráfico temporal, copiloto e conhecimento vinculado.
// É o "LinkedIn da máquina": tudo o que se sabe do ativo em um lugar.

import {
  getArea,
  latestReading,
  assetStatus,
  assetRisk,
  THRESHOLDS,
  alertsForTag,
  ordersForTag,
  docsForTag,
} from "../data/mock.js";
import { StatusBadge, RiskTag } from "./ui.jsx";
import TimeChart from "./TimeChart.jsx";
import Copilot from "./Copilot.jsx";

const fmtDate = (d) =>
  d ? new Date(d + "T00:00:00").toLocaleDateString("pt-BR") : "—";

const tempTone = (t) =>
  t >= THRESHOLDS.temp.crit ? "var(--critico)" : t >= THRESHOLDS.temp.warn ? "var(--alerta)" : "var(--texto)";
const vibTone = (v) =>
  v >= THRESHOLDS.vib.crit ? "var(--critico)" : v >= THRESHOLDS.vib.warn ? "var(--alerta)" : "var(--texto)";

function Reading({ label, value, unit, sensor, tone }) {
  return (
    <div className="reading">
      <div className="r-label">{label}</div>
      <div className="r-value" style={{ color: tone || "var(--texto)" }}>
        {value}
        <span className="r-unit">{unit}</span>
      </div>
      {sensor && <div className="r-sensor">{sensor}</div>}
    </div>
  );
}

function Fact({ label, children }) {
  return (
    <div className="field">
      <span className="f-label">{label}</span>
      <span>{children}</span>
    </div>
  );
}

export default function AssetProfile({ asset, nav }) {
  const tag = asset.tag;
  const reading = latestReading(tag);
  const status = assetStatus(tag);
  const risk = assetRisk(tag);
  const area = getArea(asset.area);
  const alert = alertsForTag(tag)[0];
  const orders = ordersForTag(tag);
  const docs = docsForTag(tag);
  const when = reading ? new Date(reading.ts).toLocaleString("pt-BR") : "—";

  const sensorByType = (type) =>
    asset.sensors.find((s) => s.type === type)?.tag;

  return (
    <div>
      {/* Cabeçalho do ativo */}
      <section className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontSize: 19 }}>
            <span className="tag-mono">{tag}</span> &nbsp;{asset.name}
          </h2>
          <StatusBadge status={status} />
          <span className="pill">Área {area?.letter} · {area?.name}</span>
        </div>

        {/* Banner de alerta preditivo */}
        {alert && status !== "normal" && (
          <div className={`alert-banner ${status}`} style={{ marginTop: 14 }}>
            <div className="alert-icon">{status === "critico" ? "🚨" : "⚠️"}</div>
            <div style={{ flex: 1 }}>
              <div className="alert-title">{alert.title}</div>
              <div className="alert-msg">{alert.message}</div>
              <div className="alert-meta">
                <span>Origem: <b className="mono">{alert.origin}</b></span>
                <span>Risco: <b><RiskTag level={risk.level} /></b></span>
                {risk.windowHours && <span>Janela: <b>{risk.windowHours}h</b></span>}
                <span>Base: <b>{alert.bases.join(" + ")}</b></span>
              </div>
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center", marginTop: 4 }}>
                <div className="conf-wrap" style={{ marginTop: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                    <span className="muted">Confiança</span>
                    <b>{alert.confidence}%</b>
                  </div>
                  <div className="conf-track" style={{ marginTop: 5 }}>
                    <div className="conf-fill" style={{ width: `${alert.confidence}%` }} />
                  </div>
                </div>
                <button className="btn primary" onClick={() => nav.goView("alertas")}>
                  Ver alerta completo →
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Ficha técnica */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 24px", marginTop: 16 }}>
          <div>
            <Fact label="Fabricante / modelo">{asset.manufacturer}</Fact>
            <Fact label="Tipo">{asset.motor_type}</Fact>
            <Fact label="Equipamento pai"><span className="mono">{asset.parent}</span></Fact>
            <Fact label="Horas de operação">{asset.operatingHours.toLocaleString("pt-BR")} h</Fact>
          </div>
          <div>
            <Fact label="Última manutenção">{fmtDate(asset.lastMaintenance)}</Fact>
            <Fact label="Próxima inspeção">{fmtDate(asset.nextInspection)}</Fact>
            <Fact label="Risco de falha"><RiskTag level={risk.level} /> · score {risk.score}/100</Fact>
            <Fact label="Instalado em">{fmtDate(asset.installDate)}</Fact>
          </div>
        </div>
      </section>

      {/* Leitura atual */}
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h3 style={{ margin: 0 }}>Leitura atual</h3>
          <span className="muted small">{when}</span>
        </div>
        {reading ? (
          <div className="reading-row" style={{ marginTop: 12 }}>
            <Reading label="Temperatura" value={reading.temperature} unit="°C"
              sensor={sensorByType("Temperatura")} tone={tempTone(reading.temperature)} />
            <Reading label="Corrente" value={reading.current} unit="A"
              sensor={sensorByType("Corrente")} />
            <Reading label="Vibração" value={reading.vibration} unit="m/s²"
              sensor={sensorByType("Vibração")} tone={vibTone(reading.vibration)} />
            <Reading label="Rotação" value={reading.rotation} unit="RPM" />
          </div>
        ) : (
          <p className="muted small">Sem leituras.</p>
        )}

        {/* Sensores do ativo */}
        <div style={{ marginTop: 14 }}>
          <div className="section-title" style={{ marginBottom: 6 }}>Sensores conectados</div>
          <div className="toolbar">
            {asset.sensors.map((s) => (
              <span className="pill" key={s.tag} title={s.model}>
                {s.tag} · {s.type}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Gráfico temporal */}
      <TimeChart tag={tag} />

      {/* Assistente técnico (copiloto) — remonta ao trocar de ativo */}
      <Copilot key={tag} tag={tag} />

      {/* Conhecimento vinculado */}
      <section className="card">
        <h3>Conhecimento vinculado</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <div className="section-title" style={{ marginBottom: 8 }}>Documentos técnicos</div>
            {docs.length ? (
              docs.map((d) => (
                <div key={d.id} className="field" style={{ alignItems: "flex-start" }}>
                  <span style={{ fontSize: 16 }}>📄</span>
                  <span>
                    <button className="link-btn" onClick={() => nav.goView("documentos")}>
                      {d.label}
                    </button>
                    <div className="muted small">{d.kind} · {d.meta}</div>
                  </span>
                </div>
              ))
            ) : (
              <p className="muted small">Nenhum documento vinculado.</p>
            )}
          </div>
          <div>
            <div className="section-title" style={{ marginBottom: 8 }}>Ordens de manutenção</div>
            {orders.length ? (
              orders.map((o) => (
                <div key={o.id} className="field" style={{ alignItems: "flex-start" }}>
                  <span style={{ fontSize: 16 }}>🧰</span>
                  <span>
                    <button className="link-btn" onClick={() => nav.goView("ordens")}>
                      {o.id}
                    </button>
                    <span className="pill" style={{ marginLeft: 8 }}>{o.status}</span>
                    <div className="muted small">{o.type} · {o.title}</div>
                  </span>
                </div>
              ))
            ) : (
              <p className="muted small">Nenhuma OS vinculada.</p>
            )}
          </div>
        </div>

        <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button className="btn" onClick={() => nav.goView("auditoria")}>
            🔍 Ver auditoria do dado
          </button>
        </div>
      </section>
    </div>
  );
}
