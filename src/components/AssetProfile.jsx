// AssetProfile.jsx — "perfil" do ativo (cena 2). Identidade por TAG + leitura atual,
// risco preditivo, sensores, gráfico temporal, copiloto e conhecimento vinculado.
// É o "LinkedIn da máquina": tudo o que se sabe do ativo em um lugar.

import { useEffect, useState } from "react";
import {
  getArea,
  latestReading,
  assetStatus,
  assetRisk,
  THRESHOLDS,
  alertsForTag,
  ordersForTag,
  docsForTag,
  componentsForAsset,
  HEARTBEAT,
} from "../data/mock.js";
import { StatusBadge, RiskTag } from "./ui.jsx";
import TimeChart from "./TimeChart.jsx";
import Copilot from "./Copilot.jsx";
import MotorMimic from "./MotorMimic.jsx";
import Gauge from "./Gauge.jsx";

const fmtDate = (d) =>
  d ? new Date(d + "T00:00:00").toLocaleDateString("pt-BR") : "—";

// Ficha técnica em rótulos amigáveis (linguagem simples primeiro, TAG/jargão depois).
function Fact({ label, children, hint }) {
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className="kv-value">
        {children}
        {hint && <span className="muted small" style={{ marginLeft: 6 }}>{hint}</span>}
      </span>
    </div>
  );
}

// Limites operacionais configurados — a "parametrização que dispara o alerta"
// (conceito central da solução Forzy). Mostra os limiares e o estado atual.
function LimitRow({ metric, unit, warn, crit, value }) {
  const state =
    value == null ? "neutro" : value >= crit ? "critico" : value >= warn ? "alerta" : "normal";
  const label = {
    normal: "dentro do limite",
    alerta: "em atenção",
    critico: "acima do crítico",
    neutro: "—",
  }[state];
  return (
    <div
      style={{
        flex: "1 1 220px",
        background: "var(--surface-2)",
        border: "1px solid var(--borda)",
        borderRadius: 12,
        padding: "11px 13px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span style={{ fontWeight: 600 }}>{metric}</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span className={`led ${state === "normal" ? "ok" : state}`} />
          <span className="muted small">{label}</span>
        </span>
      </div>
      <div className="muted small" style={{ marginTop: 6 }}>
        Atenção ≥ <b style={{ color: "var(--alerta)" }}>{warn} {unit}</b> · Crítico ≥{" "}
        <b style={{ color: "var(--critico)" }}>{crit} {unit}</b>
      </div>
    </div>
  );
}

// Valor atual por TAG de sensor (mapeia o tipo do sensor → métrica da leitura).
function sensorValue(asset, sensorTag, reading) {
  const s = asset.sensors.find((x) => x.tag === sensorTag);
  if (!s || !reading) return null;
  const map = {
    Temperatura: { v: reading.temperature, unit: "°C" },
    Vibração: { v: reading.vibration, unit: "m/s²" },
    Corrente: { v: reading.current, unit: "A" },
  };
  return map[s.type] || null;
}

// Componentes (nível entre Motor e Sensor). Torna a recomendação física:
// o sensor de vibração está montado NO rolamento sob suspeita.
function Components({ asset, reading, comps, selected, onSelect }) {
  const current = comps.find((c) => c.tag === selected) || comps[0];
  return (
    <section className="card">
      <h3>
        Componentes{" "}
        <span className="muted small" style={{ fontWeight: 400 }}>
          · Motor → Componente → Sensor
        </span>
      </h3>

      <div className="cmp-row">
        {comps.map((c) => (
          <button
            key={c.tag}
            className={`cmp-card ${c.tag === current.tag ? "active" : ""}`}
            onClick={() => onSelect(c.tag)}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              <span className="cmp-tag">{c.tag}</span>
              <span className={`dot ${c.status}`} style={{ width: 9, height: 9 }} />
            </div>
            <div className="cmp-name">{c.name}</div>
            <div className="cmp-type">{c.type} · risco <RiskTag level={c.risk.level} /></div>
          </button>
        ))}
      </div>

      {current && (
        <div className="cmp-detail">
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span className="tag-mono" style={{ fontSize: 14 }}>{current.tag}</span>
            <strong>{current.name}</strong>
            <StatusBadge status={current.status} />
            <span className="pill">{current.type}</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 24px", marginTop: 12 }}>
            <div>
              <div className="section-title" style={{ marginBottom: 6 }}>Sensores conectados</div>
              {current.sensors.map((st) => {
                const val = sensorValue(asset, st, reading);
                const s = asset.sensors.find((x) => x.tag === st);
                return (
                  <div key={st} className="field" style={{ alignItems: "baseline" }}>
                    <span style={{ fontSize: 14 }}>🛰️</span>
                    <span>
                      <span className="mono" style={{ fontSize: 12.5 }}>{st}</span>
                      <span className="muted small"> · {s?.type}</span>
                      {val && <b style={{ marginLeft: 8 }}>{val.v} {val.unit}</b>}
                    </span>
                  </div>
                );
              })}
              <div className="field" style={{ marginTop: 6 }}>
                <span className="f-label">Risco do componente</span>
                <span><RiskTag level={current.risk.level} /> · score {current.risk.score}/100</span>
              </div>
            </div>
            <div>
              <div className="section-title" style={{ marginBottom: 6 }}>Evidências</div>
              {current.evidence.map((e, i) => (
                <div className="evidence" key={i}>
                  <span className="ev-mark">▸</span>
                  <span>{e}</span>
                </div>
              ))}
              {current.note && (
                <p className="muted small" style={{ marginTop: 8 }}>{current.note}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default function AssetProfile({ asset, nav, selectedComponent }) {
  const tag = asset.tag;
  const reading = latestReading(tag);
  const status = assetStatus(tag);
  const risk = assetRisk(tag);
  const area = getArea(asset.area);
  const alert = alertsForTag(tag)[0];
  const orders = ordersForTag(tag);
  const docs = docsForTag(tag);
  const comps = componentsForAsset(tag);
  const when = reading ? new Date(reading.ts).toLocaleString("pt-BR") : "—";
  const isLive = tag === HEARTBEAT.tag;

  // Componente selecionado: prop (vinda da árvore TAG) tem prioridade.
  const [activeComp, setActiveComp] = useState(selectedComponent || (comps[0] && comps[0].tag));
  useEffect(() => {
    if (selectedComponent) setActiveComp(selectedComponent);
  }, [selectedComponent]);

  return (
    <div>
      {/* Estilos locais (layout do perfil) — sem tocar styles.css. */}
      <style>{`
        .ap-twin-grid {
          display: grid;
          grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr);
          gap: 16px;
          align-items: stretch;
        }
        .ap-twin-grid > .card { margin: 0; }
        @media (max-width: 1080px) {
          .ap-twin-grid { grid-template-columns: 1fr; }
        }
        .gauge-row {
          display: flex;
          flex-wrap: wrap;
          gap: 18px 26px;
          justify-content: space-around;
          align-items: flex-end;
        }
        .kv-list { display: flex; flex-direction: column; gap: 2px; }
        .ap-twin-grid .kv {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          gap: 12px;
          padding: 7px 0;
          border-bottom: 1px dashed var(--stroke, rgba(154,108,255,.18));
        }
        .ap-twin-grid .kv:last-child { border-bottom: none; }
        .kv-label {
          color: var(--texto-fraco);
          font-size: 12.5px;
          text-transform: uppercase;
          letter-spacing: .04em;
          white-space: nowrap;
        }
        .kv-value { text-align: right; font-weight: 600; }
        .ap-tech { margin-top: 12px; }
        .ap-tech > summary {
          cursor: pointer;
          color: var(--texto-fraco);
          font-size: 12.5px;
          text-transform: uppercase;
          letter-spacing: .04em;
          list-style: none;
          user-select: none;
          padding: 6px 0;
        }
        .ap-tech > summary::-webkit-details-marker { display: none; }
        .ap-tech > summary::before { content: "▸ "; color: var(--roxo-claro); }
        .ap-tech[open] > summary::before { content: "▾ "; }
      `}</style>

      {/* Cabeçalho do ativo */}
      <section className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontSize: 20 }}>{asset.name}</h2>
          <StatusBadge status={status} />
          <span className="pill">Área {area?.letter} · {area?.name}</span>
          <span className="tag-mono muted" style={{ fontSize: 12 }}>{tag}</span>
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

      </section>

      {/* Gêmeo digital + ficha técnica lado a lado */}
      <div className="ap-twin-grid">
        {/* Desenho 2.5D do motor (sincronizado com a seleção de componente) */}
        {comps.length > 0 ? (
          <MotorMimic
            asset={asset}
            reading={reading}
            components={comps}
            status={status}
            activeComponent={activeComp}
            onSelectComponent={setActiveComp}
          />
        ) : (
          <MotorMimic asset={asset} reading={reading} components={[]} status={status} />
        )}

        {/* Ficha técnica — rótulos amigáveis, detalhe técnico em segundo plano */}
        <section className="card">
          <h3 style={{ marginTop: 0 }}>Ficha do equipamento</h3>
          <div className="kv-list">
            <Fact label="O que é">{asset.motor_type}</Fact>
            <Fact label="Fabricante">{asset.manufacturer}</Fact>
            <Fact label="Tempo em operação">
              {asset.operatingHours.toLocaleString("pt-BR")} h
            </Fact>
            <Fact label="Última manutenção">{fmtDate(asset.lastMaintenance)}</Fact>
            <Fact label="Próxima inspeção">{fmtDate(asset.nextInspection)}</Fact>
            <Fact label="Instalado em">{fmtDate(asset.installDate)}</Fact>
            <Fact label="Risco de falha">
              <RiskTag level={risk.level} />{" "}
              <span className="muted small">· score {risk.score}/100</span>
            </Fact>
          </div>
          <details className="ap-tech">
            <summary>Detalhes técnicos</summary>
            <div className="kv-list" style={{ marginTop: 8 }}>
              <Fact label="TAG do ativo">
                <span className="mono">{tag}</span>
              </Fact>
              <Fact label="Equipamento pai">
                <span className="mono">{asset.parent}</span>
              </Fact>
              <Fact label="Área">
                <span className="mono">{asset.area}</span>{" "}
                <span className="muted small">· {area?.name}</span>
              </Fact>
              {asset.note && <Fact label="Observação">{asset.note}</Fact>}
            </div>
          </details>
        </section>
      </div>

      {/* Leitura atual — instrumentos (gauges) */}
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
          <h3 style={{ margin: 0 }}>
            Leitura atual{" "}
            <span className="muted small" style={{ fontWeight: 400 }}>· instrumentos ao vivo</span>
          </h3>
          <span className="muted small" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {isLive && <span className="led ok pulse" />}
            {when}
          </span>
        </div>
        {reading ? (
          <div className="gauge-row" style={{ marginTop: 12 }}>
            <Gauge label="Temperatura" value={reading.temperature} unit="°C"
              min={20} max={100} warn={THRESHOLDS.temp.warn} crit={THRESHOLDS.temp.crit} size={168} />
            <Gauge label="Vibração" value={reading.vibration} unit="m/s²"
              min={0} max={10} warn={THRESHOLDS.vib.warn} crit={THRESHOLDS.vib.crit} size={168} />
            <Gauge label="Corrente" value={reading.current} unit="A"
              min={0} max={120} warn={null} crit={null} size={168} />
            <Gauge label="Rotação" value={reading.rotation} unit="RPM"
              min={0} max={3600} warn={null} crit={null} size={168} />
          </div>
        ) : (
          <p className="muted small">Sem leituras.</p>
        )}

        {/* Limites operacionais — a parametrização que dispara o alerta (visão Forzy) */}
        <div style={{ marginTop: 16 }}>
          <div
            className="section-title"
            style={{ marginBottom: 8, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}
          >
            <span>
              Limites operacionais{" "}
              <span className="muted small" style={{ fontWeight: 400 }}>
                · o sistema alerta ao atingir estes valores
              </span>
            </span>
            <button
              className="btn"
              disabled
              title="Demo — limites fixos nesta versão do protótipo"
              style={{ opacity: 0.65, cursor: "default" }}
            >
              ⚙ Ajustar limites
            </button>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <LimitRow metric="Temperatura" unit="°C" warn={THRESHOLDS.temp.warn} crit={THRESHOLDS.temp.crit} value={reading?.temperature} />
            <LimitRow metric="Vibração" unit="m/s²" warn={THRESHOLDS.vib.warn} crit={THRESHOLDS.vib.crit} value={reading?.vibration} />
          </div>
        </div>

        {/* Sensores do ativo */}
        <div style={{ marginTop: 14 }}>
          <div className="section-title" style={{ marginBottom: 6 }}>Sensores conectados</div>
          <div className="toolbar">
            {asset.sensors.map((s) => (
              <span className="pill" key={s.tag} title={s.model}>
                <span className="muted">{s.type}</span> · {s.tag}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Componentes (nível entre Motor e Sensor) */}
      {comps.length > 0 && (
        <Components
          asset={asset}
          reading={reading}
          comps={comps}
          selected={activeComp}
          onSelect={setActiveComp}
        />
      )}

      {/* Gráfico temporal (ao vivo na estrela) */}
      <TimeChart tag={tag} live={isLive} />

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
