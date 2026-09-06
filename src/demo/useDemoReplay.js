import { useEffect, useMemo, useSyncExternalStore } from "react";
import { createGatewayDemoDataSource } from "../dataSources/GatewayDemoDataSource.js";
import { ReplayController } from "./ReplayController.js";

export function useDemoReplay(source) {
  const controller = useMemo(() => {
    let storage;
    try { storage = window.sessionStorage; } catch { /* browser denies storage */ }
    return new ReplayController(source ?? createGatewayDemoDataSource(), { storage, document });
  }, [source]);
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  useEffect(() => { controller.start(); return () => controller.dispose(); }, [controller]);
  return { ...state, controller };
}
