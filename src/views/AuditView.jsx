// AuditView.jsx — "Confiança do dado". Reúne o caminho da medição (pipeline clicável)
// e a procedência por leitura, em linguagem simples primeiro e técnica em segundo plano.

import { assets, getAsset, getArea, assetStatus } from "../data/mock.js";
import DataPipeline from "../components/DataPipeline.jsx";
import Provenance from "../components/Provenance.jsx";

const STAR = "MTR-BMB-042";
const STATUS_CLS = { normal: "ok", alerta: "alerta", critico: "critico", desconhecido: "neutro" };

export default function AuditView({ selectedTag, nav }) {
  const tag = selectedTag && getAsset(selectedTag) ? selectedTag : STAR;
  const current = getAsset(tag);
  const area = current ? getArea(current.area) : null;

  return (
    <div data-tour="audit">
      <style>{`
        .au-topbar { display:flex; justify-content:space-between; align-items:flex-end;
          flex-wrap:wrap; gap:14px; }
        .au-pick { display:flex; flex-direction:column; gap:6px; align-items:flex-end; }
        .au-pick-lbl { font-size:11px; letter-spacing:.04em; text-transform:uppercase;
          color:var(--texto-fraco); }
        .au-chips { display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end; }
        .au-chip {
          display:inline-flex; align-items:center; gap:7px;
          background: linear-gradient(180deg, var(--panel-2), var(--panel));
          border:1px solid var(--stroke); border-radius:999px;
          color:var(--texto-fraco); cursor:pointer; padding:6px 12px;
          font-size:12.5px; transition:border-color .15s ease, color .15s ease;
        }
        .au-chip:hover { border-color:var(--roxo-claro); color:var(--texto); }
        .au-chip.active {
          color:var(--texto); border-color:var(--roxo);
          box-shadow:0 0 0 1px var(--roxo) inset, 0 0 14px rgba(124,58,237,.25);
        }
        .au-chip .au-name { font-weight:600; }
        .au-chip .au-tag {
          font-family:ui-monospace,Menlo,monospace; font-size:10.5px;
          color:var(--texto-fraco); opacity:.85;
        }
      `}</style>

      <div className="topbar au-topbar">
        <div>
          <h1 className="page-title">Confiança do dado</h1>
          <p className="page-sub">
            Cada número que você vê tem origem rastreável e prova de que não foi alterado.
            {current ? (
              <> Acompanhando <strong style={{ color: "var(--texto)" }}>{current.name}</strong>
                {area ? <> · {area.name}</> : null}.</>
            ) : null}
          </p>
        </div>

        <div className="au-pick">
          <span className="au-pick-lbl">Escolher motor</span>
          <div className="au-chips">
            {assets.map((a) => {
              const st = assetStatus(a.tag);
              const led = STATUS_CLS[st] ?? "neutro";
              const active = a.tag === tag;
              return (
                <button
                  key={a.tag}
                  className={`au-chip ${active ? "active" : ""}`}
                  onClick={() => nav.goAsset(a.tag, "auditoria")}
                  title={`${a.name} · ${a.tag}`}
                >
                  <span className={`led ${led}${st !== "normal" ? " pulse" : ""}`} />
                  <span className="au-name">{a.name}</span>
                  <span className="au-tag">{a.tag}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <DataPipeline tag={tag} />
      </div>
      <div style={{ marginTop: 16 }}>
        <Provenance tag={tag} />
      </div>
    </div>
  );
}
