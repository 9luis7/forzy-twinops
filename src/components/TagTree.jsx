// TagTree.jsx — navegação hierárquica Planta → Área → Motor → Componente → Sensor.
// Reflete o drill-down macro→micro. Estado de seleção vem do App.

import { useState } from "react";
import {
  PLANT,
  areas,
  assetsByArea,
  componentForSensor,
} from "../data/mock.js";
import { useLiveTwin } from "../LiveTwinContext.jsx";

export default function TagTree({
  selectedTag,
  selectedArea,
  selectedComponent,
  onSelectAsset,
  onSelectComponent,
}) {
  const twin = useLiveTwin();
  // Áreas com ativos detalhados começam expandidas; foca a área selecionada.
  const [open, setOpen] = useState(() => {
    const s = new Set(areas.filter((a) => assetsByArea(a.tag).length).map((a) => a.tag));
    if (selectedArea) s.add(selectedArea);
    return s;
  });
  const [openAsset, setOpenAsset] = useState(selectedTag || null);
  const [openCmp, setOpenCmp] = useState(selectedComponent || null);

  const toggle = (tag) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(tag) ? next.delete(tag) : next.add(tag);
      return next;
    });

  return (
    <aside className="card" style={{ alignSelf: "start" }}>
      <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="led ok pulse" />
        Navegação do ativo
      </h3>
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontWeight: 600 }}>🏭 {PLANT.name}</div>
        <div className="muted mono" style={{ fontSize: 11.5, marginTop: 1 }}>{PLANT.tag}</div>
      </div>

      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {areas.map((area) => {
          const motors = assetsByArea(area.tag);
          const isOpen = open.has(area.tag);
          const hasMotors = motors.length > 0;
          return (
            <li key={area.tag} style={{ marginBottom: 4 }}>
              <button
                onClick={() => hasMotors && toggle(area.tag)}
                title={area.tag}
                style={treeBtn(false)}
              >
                <span style={{ color: "var(--texto-fraco)", width: 10 }}>
                  {hasMotors ? (isOpen ? "▾" : "▸") : "·"}
                </span>
                <span>{area.icon} Área {area.letter} — {area.name}</span>
                <span className="muted" style={{ fontSize: 12 }}>
                  ({hasMotors ? motors.length : area.assetsCount})
                </span>
              </button>

              {isOpen && hasMotors && (
                <ul style={{ listStyle: "none", margin: 0, padding: "2px 0 2px 20px" }}>
                  {motors.map((m) => {
                    const active = m.tag === selectedTag;
                    const expanded = openAsset === m.tag;
                    const comps = twin.componentsOf(m.tag);
                    return (
                      <li key={m.tag}>
                        <button
                          onClick={() => {
                            onSelectAsset(m.tag);
                            setOpenAsset(expanded ? null : m.tag);
                          }}
                          style={treeBtn(active)}
                        >
                          <span className={`led ${ledCls(cmpCls(twin.statusOf(m.tag)))}`} />
                          <span className="mono" style={{ fontSize: 12.5 }}>{m.tag}</span>
                        </button>

                        {expanded && comps.length > 0 && (
                          <ul style={{ listStyle: "none", margin: "2px 0", padding: "0 0 0 18px" }}>
                            {comps.map((c) => {
                              const cActive = c.tag === selectedComponent;
                              const cOpen = openCmp === c.tag;
                              return (
                                <li key={c.tag}>
                                  <button
                                    onClick={() => {
                                      onSelectComponent(c.tag);
                                      setOpenCmp(cOpen ? null : c.tag);
                                    }}
                                    style={treeBtn(cActive)}
                                    title={c.name}
                                  >
                                    <span style={{ color: "var(--texto-fraco)", width: 10 }}>
                                      {cOpen ? "▾" : "▸"}
                                    </span>
                                    <span className={`led ${ledCls(cmpCls(c.status))}`} />
                                    <span className="mono" style={{ fontSize: 12 }}>{c.tag}</span>
                                  </button>

                                  {cOpen && (
                                    <ul style={{ listStyle: "none", margin: "2px 0", padding: "0 0 0 30px" }}>
                                      {c.sensors.map((st) => (
                                        <li
                                          key={st}
                                          className="muted mono"
                                          style={{ fontSize: 11.5, padding: "2px 0" }}
                                        >
                                          ↳ {st}
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </li>
                              );
                            })}

                            {/* Sensores do motor não ligados a um componente (ex.: PLC) */}
                            {m.sensors
                              .filter((s) => !componentForSensor(s.tag))
                              .map((s) => (
                                <li
                                  key={s.tag}
                                  className="muted mono"
                                  style={{ fontSize: 11.5, padding: "2px 0 2px 28px" }}
                                  title={`${s.type} (sem componente)`}
                                >
                                  ↳ {s.tag}
                                </li>
                              ))}
                          </ul>
                        )}

                        {expanded && comps.length === 0 && (
                          <ul style={{ listStyle: "none", margin: "2px 0", padding: "0 0 0 26px" }}>
                            {m.sensors.map((s) => (
                              <li
                                key={s.tag}
                                className="muted mono"
                                style={{ fontSize: 11.5, padding: "2px 0" }}
                              >
                                ↳ {s.tag}
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

function cmpCls(status) {
  return ["normal", "alerta", "critico"].includes(status) ? status : "neutro";
}

// Mapeia o estado (normal|alerta|critico|neutro) para as classes do LED (.led),
// que usa ok/alerta/critico. "alerta"/"critico" pulsam para chamar atenção.
function ledCls(state) {
  if (state === "normal") return "ok";
  if (state === "alerta") return "alerta pulse";
  if (state === "critico") return "critico pulse";
  return "";
}

function treeBtn(active) {
  return {
    display: "flex",
    alignItems: "center",
    gap: 8,
    width: "100%",
    background: active ? "var(--surface-2)" : "transparent",
    border: active ? "1px solid var(--roxo)" : "1px solid transparent",
    borderRadius: 8,
    color: active ? "var(--texto)" : "var(--texto-fraco)",
    cursor: "pointer",
    padding: "6px 8px",
    fontSize: 13,
    textAlign: "left",
  };
}
