import DataPipeline from "./components/DataPipeline.jsx";
import TagTree from "./components/TagTree.jsx";
import AssetPanel from "./components/AssetPanel.jsx";
import TimeChart from "./components/TimeChart.jsx";
import Provenance from "./components/Provenance.jsx";

export default function App() {
  return (
    <div style={{ minHeight: "100vh", padding: "24px" }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, color: "var(--laranja)" }}>Forzy TwinOps</h1>
        <p style={{ color: "var(--texto-fraco)", margin: "4px 0 0" }}>
          Camada de inteligência operacional para plantas industriais — protótipo navegável
        </p>
      </header>

      {/* Esqueleto de layout. Cada componente é um stub a ser construído. */}
      <DataPipeline />
      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 16, marginTop: 16 }}>
        <TagTree />
        <div>
          <AssetPanel />
          <TimeChart />
          <Provenance />
        </div>
      </div>
    </div>
  );
}
