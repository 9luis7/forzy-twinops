import React from "react";
import OperationsDashboard from "./components/operations/OperationsDashboard.jsx";
import Twin3D from "./components/Twin3D.jsx";
import { TwinOpsProvider } from "./TwinOpsContext.jsx";

export default function App({ dataSource, Twin3DComponent = Twin3D }) {
  return (
    <TwinOpsProvider dataSource={dataSource}>
      <OperationsDashboard Twin3DComponent={Twin3DComponent} />
    </TwinOpsProvider>
  );
}
