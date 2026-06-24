// Breadcrumb.jsx — trilha de navegação PLT → AREA → MTR (drill-down macro→micro).
import { PLANT, getArea, getAsset } from "../data/mock.js";

export default function Breadcrumb({ areaTag, assetTag, nav }) {
  const area = areaTag ? getArea(areaTag) : null;
  const asset = assetTag ? getAsset(assetTag) : null;

  return (
    <nav className="breadcrumb">
      <button onClick={() => nav.goPlant()}>🏭 {PLANT.tag}</button>
      {area && (
        <>
          <span className="sep">/</span>
          <button onClick={() => nav.goArea(area.tag)}>{area.tag}</button>
        </>
      )}
      {asset && (
        <>
          <span className="sep">/</span>
          <span className="crumb-static">{asset.tag}</span>
        </>
      )}
    </nav>
  );
}
