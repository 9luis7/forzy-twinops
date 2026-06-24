// OrdersView.jsx — Ordens de manutenção (OS), sala de controle. Inclui a OS
// preditiva gerada pelo alerta e o histórico (OS-2025-118) que o copiloto usa
// como evidência. Descrição humana primeiro; OS/TAG/origem como camada técnica.

import { maintenanceOrders, getAsset } from "../data/mock.js";

// Status -> LED de painel (mapeia para as classes .led padrão).
const STATUS_LED = {
  Aberta: "critico",
  Programada: "alerta",
  Concluída: "ok",
};
const STATUS_COLOR = {
  Aberta: "var(--critico)",
  Programada: "var(--alerta)",
  Concluída: "var(--ok)",
};
const PRIO_COLOR = { Alta: "var(--critico)", Média: "var(--alerta)", Baixa: "var(--texto-fraco)" };

const fmt = (d) => new Date(d + "T00:00:00").toLocaleDateString("pt-BR");

// Contadores para a faixa de instrumentos no topo.
function counts() {
  const c = { aberta: 0, programada: 0, concluida: 0 };
  for (const o of maintenanceOrders) {
    if (o.status === "Aberta") c.aberta++;
    else if (o.status === "Programada") c.programada++;
    else if (o.status === "Concluída") c.concluida++;
  }
  return c;
}

export default function OrdersView({ nav }) {
  const c = counts();
  return (
    <div data-tour="orders-view">
      <div className="topbar">
        <div>
          <h1 className="page-title">Ordens de manutenção</h1>
          <p className="page-sub">
            Preditivas, preventivas e corretivas — vinculadas ao ativo e à sua origem.
          </p>
        </div>
        <div className="reading-row" style={{ flex: "0 0 auto" }}>
          <div className="reading" style={{ minWidth: 90, padding: "8px 12px" }}>
            <div className="r-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="led critico" /> Abertas
            </div>
            <div className="r-value readout crit" style={{ fontSize: 22 }}>{c.aberta}</div>
          </div>
          <div className="reading" style={{ minWidth: 90, padding: "8px 12px" }}>
            <div className="r-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="led alerta" /> Programadas
            </div>
            <div className="r-value readout warn" style={{ fontSize: 22 }}>{c.programada}</div>
          </div>
          <div className="reading" style={{ minWidth: 90, padding: "8px 12px" }}>
            <div className="r-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="led ok" /> Concluídas
            </div>
            <div className="r-value readout ok" style={{ fontSize: 22 }}>{c.concluida}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Ordem</th>
              <th>Ativo</th>
              <th>Tipo</th>
              <th>Descrição</th>
              <th>Prioridade</th>
              <th>Prazo</th>
              <th>Origem</th>
            </tr>
          </thead>
          <tbody>
            {maintenanceOrders.map((o) => {
              const asset = getAsset(o.tag);
              const led = STATUS_LED[o.status] ?? "neutro";
              return (
                <tr key={o.id} className="clickable" onClick={() => nav.goAsset(o.tag)}>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                      <span className={`led ${led}${o.status === "Aberta" ? " pulse" : ""}`} />
                      <span style={{ color: STATUS_COLOR[o.status], fontWeight: 700 }}>{o.status}</span>
                    </span>
                  </td>
                  <td className="mono small" style={{ opacity: .85 }}>{o.id}</td>
                  <td>
                    <div>{asset?.name ?? "—"}</div>
                    <div className="muted small mono" style={{ fontSize: 10.5, marginTop: 2, opacity: .75 }}>
                      {o.tag}
                    </div>
                  </td>
                  <td><span className="pill">{o.type}</span></td>
                  <td style={{ maxWidth: 280 }}>{o.title}</td>
                  <td style={{ color: PRIO_COLOR[o.priority], fontWeight: 700 }}>{o.priority}</td>
                  <td className="small">{fmt(o.dueAt)}</td>
                  <td className="muted small">{o.origin}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="muted small" style={{ marginTop: 14 }}>
        OS preditivas nascem de um alerta do modelo; o histórico de OS realimenta o copiloto como evidência.
        Clique em uma linha para abrir o ativo correspondente.
      </p>
    </div>
  );
}
