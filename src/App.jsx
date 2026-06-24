import { useEffect, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import PlantOverview from "./views/PlantOverview.jsx";
import AssetsView from "./views/AssetsView.jsx";
import AlertsView from "./views/AlertsView.jsx";
import OrdersView from "./views/OrdersView.jsx";
import DocumentsView from "./views/DocumentsView.jsx";
import AuditView from "./views/AuditView.jsx";
import { TourProvider, TourLauncher, TourOverlay } from "./components/GuidedTour.jsx";
import { LiveTwinProvider } from "./LiveTwinContext.jsx";
import { getAsset, assets, getComponent } from "./data/mock.js";

// Resolve uma TAG para o ativo dono — aceita TAG de sensor (ex.: SNS-VIB-042B).
function resolveAsset(tag) {
  return getAsset(tag) || assets.find((a) => a.sensors.some((s) => s.tag === tag)) || null;
}

export default function App() {
  const [view, setView] = useState("planta");
  const [selectedArea, setSelectedArea] = useState(null);
  const [selectedTag, setSelectedTag] = useState(null);
  const [selectedComponent, setSelectedComponent] = useState(null);

  // Rola para o topo a cada troca de view/ativo (caminho de demo mais limpo).
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [view, selectedTag]);

  // Helper de navegação compartilhado por todas as views.
  const nav = {
    view,
    goView: (v) => setView(v),
    goPlant: () => {
      setSelectedArea(null);
      setSelectedTag(null);
      setSelectedComponent(null);
      setView("planta");
    },
    goArea: (areaTag) => {
      setSelectedArea(areaTag);
      setSelectedTag(null);
      setSelectedComponent(null);
      setView("ativos");
    },
    goAsset: (tag, targetView = "ativos") => {
      const asset = resolveAsset(tag);
      if (!asset) return;
      setSelectedArea(asset.area);
      setSelectedTag(asset.tag);
      setSelectedComponent(null);
      setView(targetView);
    },
    goComponent: (componentTag) => {
      const c = getComponent(componentTag);
      if (!c) return;
      const asset = resolveAsset(c.asset);
      if (!asset) return;
      setSelectedArea(asset.area);
      setSelectedTag(asset.tag);
      setSelectedComponent(c.tag);
      setView("ativos");
    },
  };

  // Sidebar troca de view preservando a seleção atual (volta com contexto).
  const onNavigate = (key) => setView(key);

  return (
    <LiveTwinProvider>
      <TourProvider nav={nav}>
        <div className="app">
          <Sidebar view={view} onNavigate={onNavigate} />
          <main className="main">
            {view === "planta" && <PlantOverview nav={nav} />}
            {view === "ativos" && (
              <AssetsView
                selectedTag={selectedTag}
                selectedArea={selectedArea}
                selectedComponent={selectedComponent}
                nav={nav}
              />
            )}
            {view === "alertas" && <AlertsView nav={nav} />}
            {view === "ordens" && <OrdersView nav={nav} />}
            {view === "documentos" && <DocumentsView nav={nav} />}
            {view === "auditoria" && <AuditView selectedTag={selectedTag} nav={nav} />}
          </main>
        </div>
        <TourLauncher />
        <TourOverlay />
      </TourProvider>
    </LiveTwinProvider>
  );
}
