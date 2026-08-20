import React from "react";

const stateLabels = {
  received_now: "Resposta recebida neste ciclo",
  last_known: "Último dado real conhecido",
  expected_idle: "Fora da janela de atualização",
  unavailable: "Dados indisponíveis",
};

export default function AssetHeader({ asset, operationalState }) {
  return (
    <header className="asset-header">
      <div>
        <p className="eyebrow">Ativo único monitorado</p>
        <h1>{asset.displayName}</h1>
        <p className="asset-tag">{asset.officialTag ?? "TAG não fornecida"}</p>
      </div>
      <p className={`operational-state operational-state--${operationalState}`}>
        {stateLabels[operationalState] ?? "Estado operacional indisponível"}
      </p>
    </header>
  );
}
