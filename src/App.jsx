import React from "react";
import RagAdminPanel from "./components/admin/RagAdminPanel.jsx";
import OperationsDashboard from "./components/operations/OperationsDashboard.jsx";
import Twin3D from "./components/Twin3D.jsx";
import { createGatewayRagDataSource } from "./dataSources/GatewayRagDataSource.js";
import { TwinOpsProvider } from "./TwinOpsContext.jsx";

const ASSET_ID = "forzy-motor-01";
const defaultRagDataSource = createGatewayRagDataSource();

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
  Twin3DComponent = Twin3D,
  pathname = globalThis.location?.pathname ?? "/",
  ragAdminEnabled = defaultAdminEnabled(),
}) {
  if (ragAdminEnabled === true && isRagAdminPath(pathname)) {
    return <RagAdminPanel dataSource={ragDataSource} assetId={ASSET_ID} />;
  }

  return (
    <TwinOpsProvider dataSource={dataSource}>
      <OperationsDashboard
        Twin3DComponent={Twin3DComponent}
        ragDataSource={ragDataSource}
      />
    </TwinOpsProvider>
  );
}
