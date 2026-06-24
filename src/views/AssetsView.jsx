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
  const status = assetStatus(asset.tag);
  const ledCls = ["alerta", "critico"].includes(status) ? `${status} pulse` : status;
  const tempWarn = r?.temperature >= 90 ? "var(--critico)" : r?.temperature >= 70 ? "var(--alerta)" : "var(--texto)";
  const vibWarn = r?.vibration >= 7.5 ? "var(--critico)" : r?.vibration >= 4.5 ? "var(--alerta)" : "var(--texto)";
  return (
    <button
      className="area-card ascard"
      style={{ width: "100%" }}
      onClick={() => nav.goAsset(asset.tag)}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
          <span className={`led ${ledCls}`} style={{ flex: "0 0 auto" }} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 14.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {asset.name}
            </div>
            <div className="tag-mono muted" style={{ fontSize: 11, marginTop: 2 }}>{asset.tag}</div>
          </div>
        </div>
        <StatusBadge status={status} />
      </div>
      <div className="area-meta ascard-meta" style={{ marginTop: 12 }}>
        <div>Temperatura<b className="readout" style={{ fontSize: 16, color: tempWarn }}>{r?.temperature ?? "—"} <small>°C</small></b></div>
        <div>Vibração<b className="readout" style={{ fontSize: 16, color: vibWarn }}>{r?.vibration ?? "—"} <small>m/s²</small></b></div>
        <div>Risco<b style={{ fontSize: 14, fontWeight: 700 }}><RiskTag level={risk.level} /></b></div>
      </div>
    </button>
  );
}

function AreaSummary({ areaTag, nav }) {
  const area = getArea(areaTag);
  const motors = assetsByArea(areaTag);
  const worst = motors.reduce((acc, m) => {
    const s = assetStatus(m.tag);
    const rank = { critico: 3, alerta: 2, normal: 1, desconhecido: 0 };
    return (rank[s] ?? 0) > (rank[acc] ?? 0) ? s : acc;
  }, "normal");
  const ledCls = ["alerta", "critico"].includes(worst) ? `${worst} pulse` : worst;
  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 22 }}>{area.icon}</span>
        <h3 style={{ margin: 0 }}>Área {area.letter} — {area.name}</h3>
        <span className={`led ${ledCls}`} title="Pior estado da área" />
      </div>
      <p className="muted small" style={{ marginTop: 6 }}>
        {area.assetsCount} ativos na área · {motors.length} conectados ao monitoramento. Selecione um motor.
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
      <h3 style={{ marginTop: 0 }}>Selecione um ativo</h3>
      <p className="muted small">
        Use a árvore ao lado para navegar Planta → Área → Motor, ou comece por um dos motores monitorados abaixo.
      </p>
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 12 }}>
        {allAssets.map((m) => (
          <AssetCard key={m.tag} asset={m} nav={nav} />
        ))}
      </div>
    </div>
  );
}

export default function AssetsView({ selectedTag, selectedArea, selectedComponent, nav }) {
  const asset = selectedTag ? getAsset(selectedTag) : null;

  return (
    <div>
      {/* Estilos locais — sem tocar styles.css. */}
      <style>{`
        .ascard-meta b.readout { display: block; margin-top: 3px; line-height: 1.1; }
        .ascard-meta b.readout small { font-size: 11px; color: var(--texto-fraco); font-weight: 600; }
        .ascard:hover { border-color: var(--roxo-claro); }
      `}</style>

      <div className="topbar">
        <div>
          <h1 className="page-title">Ativos</h1>
          <p className="page-sub">Do macro da planta ao micro do motor — navegue e inspecione.</p>
        </div>
      </div>

      <Breadcrumb areaTag={asset ? asset.area : selectedArea} assetTag={selectedTag} nav={nav} />

      <div className="split">
        <TagTree
          selectedTag={selectedTag}
          selectedArea={selectedArea}
          selectedComponent={selectedComponent}
          onSelectAsset={nav.goAsset}
          onSelectComponent={nav.goComponent}
        />
        <div>
          {asset ? (
            <AssetProfile asset={asset} nav={nav} selectedComponent={selectedComponent} />
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
