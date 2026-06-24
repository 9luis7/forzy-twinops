// Sidebar.jsx — navegação principal por estado (sem react-router).
// Trilha de "sala de controle": marca Forzy + 6 acessos + indicador de sistema ao vivo.
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

      <div className="sidebar-status" title="Telemetria recebendo dados ao vivo">
        <span className="led ok pulse" />
        <span>Sistema ao vivo</span>
        <span className="sidebar-status-sub mono">SCADA · OK</span>
      </div>

      <nav className="sidebar-nav">
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
      </nav>

      <div className="sidebar-foot">
        Protótipo navegável · dados sintéticos
        <br />
        Challenge FIAP × Forzy
      </div>

      <style>{`
        .sidebar-status {
          display: flex;
          align-items: center;
          gap: 8px;
          margin: 4px 0 14px;
          padding: 9px 11px;
          border-radius: 10px;
          background: var(--panel-2, rgba(36,26,69,.66));
          border: 1px solid var(--stroke, rgba(154,108,255,.18));
          font-size: 12.5px;
          font-weight: 600;
          color: var(--texto, #ece9f5);
          letter-spacing: .2px;
        }
        .sidebar-status-sub {
          margin-left: auto;
          font-size: 10.5px;
          font-weight: 600;
          color: var(--ok, #34d399);
          opacity: .85;
        }
        .sidebar-nav {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
      `}</style>
    </aside>
  );
}
