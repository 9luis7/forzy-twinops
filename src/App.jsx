import { useState } from "react";
import DataPipeline from "./components/DataPipeline.jsx";
import TagTree from "./components/TagTree.jsx";
import AssetPanel from "./components/AssetPanel.jsx";
import TimeChart from "./components/TimeChart.jsx";
import Provenance from "./components/Provenance.jsx";
import { assets } from "./data/mock.js";

export default function App() {
  // Estado de seleção compartilhado: a TAG escolhida na árvore alimenta
  // painel, gráfico e procedência. Default = primeiro ativo (MOT-001).
  const [selectedTag, setSelectedTag] = useState(assets[0]?.tag ?? null);

  return (
    <div style={{ minHeight: "100vh", padding: "24px" }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, color: "var(--laranja)" }}>Forzy TwinOps</h1>
        <p style={{ color: "var(--texto-fraco)", margin: "4px 0 0" }}>
          Camada de inteligência operacional para plantas industriais — protótipo navegável
        </p>
      </header>

      <DataPipeline tag={selectedTag} />
      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 16, marginTop: 16 }}>
        <TagTree selectedTag={selectedTag} onSelect={setSelectedTag} />
        <div>
          <AssetPanel tag={selectedTag} />
          <TimeChart tag={selectedTag} />
          <Provenance tag={selectedTag} />
        </div>
      </div>
    </div>
  );
}
