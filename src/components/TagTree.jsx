// TagTree.jsx — navegação Planta → Setor → Motor por TAG.
// Estado de seleção vem do App (selectedTag / onSelect). Setores expandem/colapsam.

import { useMemo, useState } from "react";
import { assets, assetStatus } from "../data/mock.js";

const PLANTA = "Planta Piloto — Forzy";

// Cor do indicador por estado operacional.
const STATUS_COLOR = {
  normal: "var(--ok)",
  alerta: "var(--alerta)",
  critico: "var(--critico)",
  desconhecido: "var(--texto-fraco)",
};

function StatusDot({ status }) {
  return (
    <span
      title={status}
      style={{
        display: "inline-block",
        width: 9,
        height: 9,
        borderRadius: "50%",
        background: STATUS_COLOR[status] ?? "var(--texto-fraco)",
        flexShrink: 0,
      }}
    />
  );
}

export default function TagTree({ selectedTag, onSelect }) {
  // Agrupa ativos por setor: [ ["Compressores", [asset, ...]], ... ]
  const bySector = useMemo(() => {
    const map = new Map();
    for (const a of assets) {
      if (!map.has(a.sector)) map.set(a.sector, []);
      map.get(a.sector).push(a);
    }
    return [...map.entries()];
  }, []);

  // Todos os setores começam expandidos.
  const [open, setOpen] = useState(() => new Set(bySector.map(([s]) => s)));

  const toggle = (sector) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(sector) ? next.delete(sector) : next.add(sector);
      return next;
    });

  return (
    <aside
      style={{
        background: "var(--surface)",
        border: "1px solid var(--borda)",
        borderRadius: 12,
        padding: 16,
        alignSelf: "start",
      }}
    >
      <h3 style={{ marginTop: 0 }}>Árvore TAG</h3>

      {/* Raiz: Planta */}
      <div style={{ fontWeight: 600, marginBottom: 8 }}>🏭 {PLANTA}</div>

      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {bySector.map(([sector, motors]) => {
          const isOpen = open.has(sector);
          return (
            <li key={sector} style={{ marginBottom: 4 }}>
              <button
                onClick={() => toggle(sector)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  width: "100%",
                  background: "transparent",
                  border: "none",
                  color: "var(--texto)",
                  cursor: "pointer",
                  padding: "4px 6px",
                  fontSize: 14,
                  textAlign: "left",
                }}
              >
                <span style={{ color: "var(--texto-fraco)", width: 10 }}>
                  {isOpen ? "▾" : "▸"}
                </span>
                <span>{sector}</span>
                <span style={{ color: "var(--texto-fraco)", fontSize: 12 }}>
                  ({motors.length})
                </span>
              </button>

              {isOpen && (
                <ul style={{ listStyle: "none", margin: 0, padding: "2px 0 2px 22px" }}>
                  {motors.map((m) => {
                    const active = m.tag === selectedTag;
                    return (
                      <li key={m.tag}>
                        <button
                          onClick={() => onSelect(m.tag)}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            width: "100%",
                            background: active ? "var(--surface-2)" : "transparent",
                            border: active
                              ? "1px solid var(--roxo)"
                              : "1px solid transparent",
                            borderRadius: 8,
                            color: active ? "var(--texto)" : "var(--texto-fraco)",
                            cursor: "pointer",
                            padding: "6px 8px",
                            fontSize: 13,
                            textAlign: "left",
                          }}
                        >
                          <StatusDot status={assetStatus(m.tag)} />
                          <span style={{ fontFamily: "monospace" }}>{m.tag}</span>
                          <span
                            style={{
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {m.name}
                          </span>
                        </button>
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
