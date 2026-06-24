// Breadcrumb.jsx — trilha de navegação PLT → AREA → MTR (drill-down macro→micro).
import { PLANT, getArea, getAsset } from "../data/mock.js";

export default function Breadcrumb({ areaTag, assetTag, nav }) {
  const area = areaTag ? getArea(areaTag) : null;
  const asset = assetTag ? getAsset(assetTag) : null;

  return (
    <nav className="breadcrumb">
      <button onClick={() => nav.goPlant()} title={PLANT.name}>
        <span aria-hidden="true">🏭</span>
        <span className="bc-label">Planta</span>
        <span className="mono bc-tag">{PLANT.tag}</span>
      </button>
      {area && (
        <>
          <span className="sep">›</span>
          <button onClick={() => nav.goArea(area.tag)} title={area.name}>
            <span className="bc-label">Área {area.letter}</span>
            <span className="mono bc-tag">{area.tag}</span>
          </button>
        </>
      )}
      {asset && (
        <>
          <span className="sep">›</span>
          <span className="crumb-static">
            <span className="bc-label">{asset.name}</span>
            <span className="mono bc-tag">{asset.tag}</span>
          </span>
        </>
      )}

      <style>{`
        .breadcrumb .bc-label { font-weight: 600; }
        .breadcrumb .bc-tag {
          margin-left: 7px;
          font-size: 11px;
          padding: 1px 6px;
          border-radius: 6px;
          background: var(--panel-2, rgba(36,26,69,.66));
          border: 1px solid var(--stroke, rgba(154,108,255,.18));
          color: var(--texto-fraco, #a89fc4);
        }
        .breadcrumb button:hover .bc-tag,
        .breadcrumb .crumb-static .bc-tag { color: var(--roxo-claro, #a78bfa); }
      `}</style>
    </nav>
  );
}
