import React from "react";
import OperationsDashboard from "./components/operations/OperationsDashboard.jsx";
import { TwinOpsProvider } from "./TwinOpsContext.jsx";

export default function App({ dataSource, Twin3DComponent = null }) {
  return (
    <TwinOpsProvider dataSource={dataSource}>
      <OperationsDashboard Twin3DComponent={Twin3DComponent} />
    </TwinOpsProvider>
  );
}
