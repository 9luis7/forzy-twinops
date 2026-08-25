import React, { useCallback, useId } from "react";

export default function ViewModeSwitch({
  viewMode,
  loading = false,
  onShowNow,
  onShowHistory,
}) {
  const controlName = useId();
  const handleModeChange = useCallback((event) => {
    if (event.target.value === "historical") {
      void onShowHistory();
      return;
    }
    onShowNow();
  }, [onShowHistory, onShowNow]);

  return (
    <fieldset className="view-mode-switch" aria-busy={loading}>
      <legend>Contexto temporal</legend>
      <div className="view-mode-switch__options">
        <label>
          <input
            checked={viewMode === "now"}
            name={controlName}
            onChange={handleModeChange}
            type="radio"
            value="now"
          />
          <span>Agora</span>
        </label>
        <label>
          <input
            checked={viewMode === "historical"}
            name={controlName}
            onChange={handleModeChange}
            type="radio"
            value="historical"
          />
          <span>Histórico</span>
        </label>
      </div>
    </fieldset>
  );
}
