// DocumentsView.jsx — Documentos técnicos (camada de conhecimento). Cada doc é
// vinculado a TAGs — é o conhecimento que sai da cabeça do técnico e entra no sistema.

import { documents } from "../data/mock.js";

export default function DocumentsView({ nav }) {
  return (
    <div>
      <div className="topbar">
        <div>
          <h1 className="page-title">Documentos Técnicos</h1>
          <p className="page-sub">Manuais, normas, datasheets e histórico — vinculados aos ativos que embasam.</p>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        {documents.map((d) => (
          <div className="card" key={d.id} style={{ margin: 0 }}>
            <div style={{ display: "flex", gap: 12 }}>
              <div style={{ fontSize: 26 }}>📄</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700 }}>{d.label}</div>
                <div className="muted small" style={{ marginTop: 2 }}>{d.kind} · {d.meta}</div>
                <div className="toolbar" style={{ marginTop: 10 }}>
                  {d.tags.map((t) => (
                    <button key={t} className="chip" onClick={() => nav.goAsset(t)}>{t}</button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <p className="muted small" style={{ marginTop: 14 }}>
        As TAGs vinculadas alimentam o copiloto e as recomendações — clique para abrir o ativo.
        Sensores (ex.: <span className="mono">SNS-VIB-042B</span>) abrem o ativo correspondente quando conectados.
      </p>
    </div>
  );
}
