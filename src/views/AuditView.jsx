// AuditView.jsx — Auditoria / honestidade dos dados. Mostra o ciclo de vida do dado
// (pipeline clicável) e a procedência por leitura do ativo. Sem TAG, foca a estrela.

import { assets, getAsset } from "../data/mock.js";
import DataPipeline from "../components/DataPipeline.jsx";
import Provenance from "../components/Provenance.jsx";

const STAR = "MTR-BMB-042";

export default function AuditView({ selectedTag, nav }) {
  const tag = selectedTag && getAsset(selectedTag) ? selectedTag : STAR;

  return (
    <div>
      <div className="topbar">
        <div>
          <h1 className="page-title">Auditoria</h1>
          <p className="page-sub">Honestidade dos dados: ciclo de vida do dado e origem rastreável por leitura.</p>
        </div>
        <div className="toolbar">
          {assets.map((a) => (
            <button
              key={a.tag}
              className={`chip ${a.tag === tag ? "active" : ""}`}
              onClick={() => nav.goAsset(a.tag, "auditoria")}
            >
              {a.tag}
            </button>
          ))}
        </div>
      </div>

      <DataPipeline tag={tag} />
      <div style={{ marginTop: 16 }}>
        <Provenance tag={tag} />
      </div>
    </div>
  );
}
