import React from "react";

const stateLabels = {
  received_now: "Coleta recebida neste ciclo",
  last_known: "Último dado real conhecido",
  expected_idle: "Fora da janela de atualização",
  unavailable: "Dados indisponíveis",
};

export default function AssetHeader({ asset, operationalState }) {
  return (
    <header className="asset-header">
      <div>
        <p className="eyebrow">Equipamento monitorado</p>
        <h1>{asset.displayName}</h1>
        {asset.officialTag && <p className="asset-tag">{asset.officialTag}</p>}
      </div>
      <p className={`operational-state operational-state--${operationalState}`}>
        {stateLabels[operationalState] ?? "Atualização dos dados indisponível"}
      </p>
    </header>
  );
}
