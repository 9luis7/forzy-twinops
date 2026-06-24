// DocumentsView.jsx — Documentos técnicos (camada de conhecimento), sala de
// controle. Cada doc é vinculado a TAGs — é o conhecimento que sai da cabeça do
// técnico e entra no sistema. Tipo + título humanos primeiro; TAGs como chips.

import { documents, getAsset } from "../data/mock.js";

// Ícone por tipo de documento (jargão "kind" -> pictograma de painel).
const KIND_ICON = {
  "Manual do fabricante": "📘",
  "Norma técnica": "📐",
  "Datasheet de sensor": "🔧",
  "Plano interno": "🗂️",
  "Histórico de OS": "🧾",
};

export default function DocumentsView({ nav }) {
  return (
    <div data-tour="documents-view">
      <div className="topbar">
        <div>
          <h1 className="page-title">Documentos técnicos</h1>
          <p className="page-sub">
            Manuais, normas, datasheets e histórico — vinculados aos ativos que embasam.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="pill">{documents.length} documentos</span>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        {documents.map((d) => (
          <div className="card" key={d.id} style={{ margin: 0 }}>
            <div style={{ display: "flex", gap: 14 }}>
              <div
                style={{
                  fontSize: 22,
                  width: 44,
                  height: 44,
                  flexShrink: 0,
                  display: "grid",
                  placeItems: "center",
                  borderRadius: 12,
                  background: "linear-gradient(180deg, var(--surface-2), var(--surface))",
                  border: "1px solid var(--stroke)",
                  boxShadow: "var(--inset-top)",
                }}
                aria-hidden
              >
                {KIND_ICON[d.kind] ?? "📄"}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Tipo (linguagem clara) primeiro; título do documento em destaque. */}
                <div className="muted small" style={{ textTransform: "uppercase", letterSpacing: ".4px", fontSize: 10.5 }}>
                  {d.kind}
                </div>
                <div style={{ fontWeight: 700, marginTop: 2 }}>{d.label}</div>
                <div className="muted small" style={{ marginTop: 3 }}>{d.meta}</div>

                <div className="muted small" style={{ marginTop: 12, textTransform: "uppercase", letterSpacing: ".4px", fontSize: 10 }}>
                  Ativos vinculados
                </div>
                <div className="toolbar" style={{ marginTop: 6, gap: 6 }}>
                  {d.tags.map((t) => {
                    const asset = getAsset(t);
                    return (
                      <button
                        key={t}
                        className="chip"
                        onClick={() => nav.goAsset(t)}
                        title={asset ? `${asset.name} · ${t}` : t}
                      >
                        {asset ? (
                          <>
                            {asset.name}{" "}
                            <span className="mono" style={{ opacity: .6, fontSize: 10.5 }}>· {t}</span>
                          </>
                        ) : (
                          <span className="mono">{t}</span>
                        )}
                      </button>
                    );
                  })}
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
