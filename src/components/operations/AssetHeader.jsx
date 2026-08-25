import React from "react";
import ViewModeSwitch from "../timeline/ViewModeSwitch.jsx";

const stateLabels = {
  received_now: "Resposta recebida neste ciclo",
  last_known: "Último dado real conhecido",
  expected_idle: "Fora da janela de atualização",
  unavailable: "Dados indisponíveis",
  historical_context: "Ponto histórico selecionado",
  historical_gap: "Intervalo sem cobertura",
};

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  dateStyle: "short",
  timeStyle: "medium",
});

export default function AssetHeader({
  asset,
  operationalState,
  viewMode = "now",
  timelineLoading = false,
  displayViewMode = "now",
  selectedAt = null,
  onShowNow,
  onShowHistory,
}) {
  const hasViewModeActions = typeof onShowNow === "function" && typeof onShowHistory === "function";

  return (
    <header className="asset-header">
      <div>
        <p className="eyebrow">Ativo único monitorado</p>
        <h1>{asset.displayName}</h1>
        <p className="asset-tag">{asset.officialTag ?? "TAG não fornecida"}</p>
      </div>
      <div className="asset-header__context">
        <p className={`operational-state operational-state--${operationalState}`}>
          {stateLabels[operationalState] ?? "Estado operacional indisponível"}
        </p>
        {displayViewMode === "historical" && selectedAt ? (
          <p className="asset-header__selected-at">
            Contexto exibido · {" "}
            <time dateTime={selectedAt}>{dateTimeFormatter.format(new Date(selectedAt))}</time>
          </p>
        ) : null}
        {hasViewModeActions ? (
          <ViewModeSwitch
            loading={timelineLoading}
            onShowHistory={onShowHistory}
            onShowNow={onShowNow}
            viewMode={viewMode}
          />
        ) : null}
      </div>
    </header>
  );
}
