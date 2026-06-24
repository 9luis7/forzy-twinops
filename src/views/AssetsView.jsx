// AssetsView.jsx — Cena 2: navegação por TAG. Árvore à esquerda, perfil do ativo
// à direita. Sem TAG selecionada, mostra a lista de motores da área (drill).

import {
  getArea,
  getAsset,
  assetsByArea,
  assets as allAssets,
  assetStatus,
  assetRisk,
  latestReading,
} from "../data/mock.js";
import Breadcrumb from "../components/Breadcrumb.jsx";
import TagTree from "../components/TagTree.jsx";
import AssetProfile from "../components/AssetProfile.jsx";
import { StatusBadge, RiskTag } from "../components/ui.jsx";

function AssetCard({ asset, nav }) {
  const r = latestReading(asset.tag);
  const risk = assetRisk(asset.tag);
  return (
    <button
      className="area-card"
      style={{ width: "100%" }}
      onClick={() => nav.goAsset(asset.tag)}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <div>
          <div className="tag-mono" style={{ fontSize: 14 }}>{asset.tag}</div>
          <div style={{ fontWeight: 600, marginTop: 2 }}>{asset.name}</div>
        </div>
        <StatusBadge status={assetStatus(asset.tag)} />
      </div>
      <div className="area-meta" style={{ marginTop: 12 }}>
        <div>Temp.<b style={{ fontSize: 15 }}>{r?.temperature} °C</b></div>
        <div>Vibração<b style={{ fontSize: 15 }}>{r?.vibration} m/s²</b></div>
        <div>Risco<b style={{ fontSize: 14, fontWeight: 700 }}><RiskTag level={risk.level} /></b></div>
      </div>
    </button>
  );
}

function AreaSummary({ areaTag, nav }) {
  const area = getArea(areaTag);
  const motors = assetsByArea(areaTag);
  return (
    <div className="card">
      <h3>{area.icon} Área {area.letter} — {area.name}</h3>
      <p className="muted small" style={{ marginTop: -6 }}>
        {area.assetsCount} ativos na área · {motors.length} conectados ao monitoramento. Escolha um motor.
      </p>
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 12 }}>
        {motors.map((m) => (
          <AssetCard key={m.tag} asset={m} nav={nav} />
        ))}
      </div>
    </div>
  );
}

function PlantPrompt({ nav }) {
  return (
    <div className="card">
      <h3>Selecione um ativo</h3>
      <p className="muted small">
        Use a árvore TAG ao lado para navegar Planta → Área → Motor, ou comece pelo ativo de referência.
      </p>
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 12 }}>
        {allAssets.map((m) => (
          <AssetCard key={m.tag} asset={m} nav={nav} />
        ))}
      </div>
    </div>
  );
}

export default function AssetsView({ selectedTag, selectedArea, nav }) {
  const asset = selectedTag ? getAsset(selectedTag) : null;

  return (
    <div>
      <div className="topbar">
        <div>
          <h1 className="page-title">Ativos</h1>
          <p className="page-sub">Drill-down por TAG — do macro da planta ao micro do motor.</p>
        </div>
      </div>

      <Breadcrumb areaTag={asset ? asset.area : selectedArea} assetTag={selectedTag} nav={nav} />

      <div className="split">
        <TagTree
          selectedTag={selectedTag}
          selectedArea={selectedArea}
          onSelectAsset={nav.goAsset}
        />
        <div>
          {asset ? (
            <AssetProfile asset={asset} nav={nav} />
          ) : selectedArea ? (
            <AreaSummary areaTag={selectedArea} nav={nav} />
          ) : (
            <PlantPrompt nav={nav} />
          )}
        </div>
      </div>
    </div>
  );
}
