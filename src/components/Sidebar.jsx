// Sidebar.jsx — navegação principal por estado (sem react-router).
import { kpis } from "../data/mock.js";

const ITEMS = [
  { key: "planta", icon: "🛰️", label: "Visão da Planta" },
  { key: "ativos", icon: "🔩", label: "Ativos" },
  { key: "alertas", icon: "🚨", label: "Alertas", badge: kpis.criticalAlerts },
  { key: "ordens", icon: "🧰", label: "Ordens de Manutenção" },
  { key: "documentos", icon: "📄", label: "Documentos Técnicos" },
  { key: "auditoria", icon: "🔍", label: "Auditoria" },
];

export default function Sidebar({ view, onNavigate }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">F</div>
        <div>
          <div className="brand-name">Forzy TwinOps</div>
          <div className="brand-sub">Digital Twin · manutenção preditiva</div>
        </div>
      </div>

      {ITEMS.map((it) => (
        <button
          key={it.key}
          className={`nav-item ${view === it.key ? "active" : ""}`}
          onClick={() => onNavigate(it.key)}
        >
          <span className="ico">{it.icon}</span>
          <span>{it.label}</span>
          {it.badge ? <span className="nav-badge">{it.badge}</span> : null}
        </button>
      ))}

      <div className="sidebar-foot">
        Protótipo navegável · dados sintéticos
        <br />
        Challenge FIAP × Forzy
      </div>
    </aside>
  );
}
