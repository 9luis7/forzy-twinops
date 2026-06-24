// TagTree.jsx — navegação hierárquica Planta → Área → Motor → (sensores).
// Reflete o drill-down macro→micro. Estado de seleção vem do App.

import { useState } from "react";
import { PLANT, areas, assetsByArea, assetStatus } from "../data/mock.js";

export default function TagTree({ selectedTag, selectedArea, onSelectAsset }) {
  // Áreas com ativos detalhados começam expandidas; foca a área selecionada.
  const [open, setOpen] = useState(() => {
    const s = new Set(areas.filter((a) => assetsByArea(a.tag).length).map((a) => a.tag));
    if (selectedArea) s.add(selectedArea);
    return s;
  });
  const [openAsset, setOpenAsset] = useState(null);

  const toggle = (tag) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(tag) ? next.delete(tag) : next.add(tag);
      return next;
    });

  return (
    <aside className="card" style={{ alignSelf: "start" }}>
      <h3>Árvore TAG</h3>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>🏭 {PLANT.name}</div>

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
                    return (
                      <li key={m.tag}>
                        <button
                          onClick={() => {
                            onSelectAsset(m.tag);
                            setOpenAsset(expanded ? null : m.tag);
                          }}
                          style={treeBtn(active)}
                        >
                          <span className={`dot ${dotCls(m.tag)}`} style={{ width: 9, height: 9 }} />
                          <span className="mono" style={{ fontSize: 12.5 }}>{m.tag}</span>
                        </button>

                        {expanded && (
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

function dotCls(tag) {
  const s = assetStatus(tag);
  return ["normal", "alerta", "critico"].includes(s) ? s : "neutro";
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
