import { useEffect, useState } from "react";
import { parseModelManifest } from "./modelManifest.js";
import { buildTwinViewModel } from "./twinViewModel.js";

const MANIFEST_URL = "/models/conjunto-motor-bomba.manifest.json";

export default function Twin3DCanvas({ snapshot, activeComponent }) {
  const [manifest, setManifest] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(MANIFEST_URL, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Twin 3D manifest request failed: ${response.status}`);
        return response.json();
      })
      .then(parseModelManifest)
      .then(setManifest)
      .catch((reason) => {
        if (reason.name !== "AbortError") setError(reason);
      });
    return () => controller.abort();
  }, []);

  if (error) throw error;
  if (!manifest) return <section className="card" role="status">Carregando gêmeo 3D…</section>;

  const viewModel = buildTwinViewModel({ snapshot, manifest, activeComponent });
  return (
    <section className="card" data-testid="twin3d-canvas" data-status={viewModel.status} data-highlight-count={viewModel.highlightedNodeNames.length} aria-label="Gêmeo 3D do conjunto motor-bomba">
      {viewModel.warning && <p role="status">{viewModel.warning}</p>}
      <p className="muted small">
        Manifesto 3D validado; renderização do modelo físico ainda pendente.
      </p>
    </section>
  );
}
