import React, { lazy, Suspense } from "react";
import RagAdminPanel from "./components/admin/RagAdminPanel.jsx";
import OperationsDashboard from "./components/operations/OperationsDashboard.jsx";
import Twin3D from "./components/Twin3D.jsx";
import ProductShell from "./components/ProductShell.jsx";
import { createGatewayRagDataSource } from "./dataSources/GatewayRagDataSource.js";
import { createGatewayHistoryDataSource } from "./history/GatewayHistoryDataSource.js";
import { TwinOpsProvider } from "./TwinOpsContext.jsx";

const ASSET_ID = "forzy-motor-01";
const defaultRagDataSource = createGatewayRagDataSource();
const defaultHistoryDataSource = createGatewayHistoryDataSource();
const DemoDashboard = lazy(() => import("./demo/DemoDashboard.jsx"));
const HistoricalWorkspace = lazy(() => import("./history/HistoricalWorkspace.jsx"));

export function isRagAdminPath(pathname) {
  return pathname === "/rag-admin" || pathname === "/rag-admin/";
}

const defaultAdminEnabled = () => (
  import.meta.env.VITE_RAG_ADMIN_ENABLED === "true"
  || globalThis.__TWINOPS_CONFIG__?.ragAdminEnabled === true
);

export default function App({
  dataSource,
  ragDataSource = defaultRagDataSource,
  historyDataSource = defaultHistoryDataSource,
  Twin3DComponent = Twin3D,
  pathname = globalThis.location?.pathname ?? "/",
  ragAdminEnabled = defaultAdminEnabled(),
}) {
  if (pathname === "/demo" || pathname === "/demo/") {
    return (
      <ProductShell pathname={pathname}>
        <Suspense fallback={<div role="status">Preparando demonstração…</div>}>
          <DemoDashboard />
        </Suspense>
      </ProductShell>
    );
  }
  if (ragAdminEnabled === true && isRagAdminPath(pathname)) {
    return <RagAdminPanel dataSource={ragDataSource} assetId={ASSET_ID} />;
  }
  if (pathname === "/history" || pathname === "/history/") {
    return (
      <ProductShell pathname={pathname}>
        <main className="operations-shell history-shell">
          <h1>Histórico</h1>
          <Suspense fallback={<p role="status">Preparando histórico…</p>}>
            <HistoricalWorkspace dataSource={historyDataSource} Twin3DComponent={Twin3DComponent} />
          </Suspense>
        </main>
      </ProductShell>
    );
  }

  return (
    <ProductShell pathname={pathname}>
      <TwinOpsProvider dataSource={dataSource}>
        <OperationsDashboard
          Twin3DComponent={Twin3DComponent}
          ragDataSource={ragDataSource}
          historyDataSource={historyDataSource}
        />
      </TwinOpsProvider>
    </ProductShell>
  );
}
