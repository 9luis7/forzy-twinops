// OrdersView.jsx — Ordens de manutenção (OS). Inclui a OS preditiva gerada pelo
// alerta e o histórico (OS-2025-118) que o copiloto usa como evidência.

import { maintenanceOrders, getAsset } from "../data/mock.js";

const STATUS_COLOR = {
  Aberta: "var(--critico)",
  Programada: "var(--alerta)",
  Concluída: "var(--ok)",
};
const PRIO_COLOR = { Alta: "var(--critico)", Média: "var(--alerta)", Baixa: "var(--texto-fraco)" };

const fmt = (d) => new Date(d + "T00:00:00").toLocaleDateString("pt-BR");

export default function OrdersView({ nav }) {
  return (
    <div>
      <div className="topbar">
        <div>
          <h1 className="page-title">Ordens de Manutenção</h1>
          <p className="page-sub">Preditivas, preventivas e corretivas — vinculadas ao ativo e à sua origem.</p>
        </div>
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>OS</th><th>Ativo</th><th>Tipo</th><th>Descrição</th>
              <th>Prioridade</th><th>Status</th><th>Prazo</th><th>Origem</th>
            </tr>
          </thead>
          <tbody>
            {maintenanceOrders.map((o) => {
              const asset = getAsset(o.tag);
              return (
                <tr key={o.id} className="clickable" onClick={() => nav.goAsset(o.tag)}>
                  <td className="mono">{o.id}</td>
                  <td className="mono small">{o.tag}<div className="muted small" style={{ fontFamily: "inherit" }}>{asset?.name}</div></td>
                  <td>{o.type}</td>
                  <td>{o.title}</td>
                  <td style={{ color: PRIO_COLOR[o.priority], fontWeight: 600 }}>{o.priority}</td>
                  <td style={{ color: STATUS_COLOR[o.status], fontWeight: 600 }}>● {o.status}</td>
                  <td className="small">{fmt(o.dueAt)}</td>
                  <td className="muted small">{o.origin}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
