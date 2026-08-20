import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createGatewayTwinDataSourceV2 } from "./dataSources/GatewayTwinDataSourceV2.js";

const ASSET_ID = "forzy-motor-01";
const TwinOpsContext = createContext(null);
const defaultDataSource = createGatewayTwinDataSourceV2();
const forzyTime = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Sao_Paulo",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function isForzyWindowOpen(value) {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return false;
  const parts = Object.fromEntries(
    forzyTime.formatToParts(value).map(({ type, value: partValue }) => [type, partValue])
  );
  const minutes = Number(parts.hour) * 60 + Number(parts.minute);
  return ["Mon", "Tue", "Wed"].includes(parts.weekday)
    && minutes >= 12 * 60
    && minutes < 14 * 60;
}

const isAbortError = (error) => error?.name === "AbortError";

export function TwinOpsProvider({
  children,
  dataSource = defaultDataSource,
  clock = () => new Date(),
  pollMs = 5000,
  documentRef = document,
}) {
  if (!dataSource || typeof dataSource.getSnapshot !== "function" || typeof dataSource.refresh !== "function") {
    throw new TypeError("TwinOpsProvider dataSource must implement getSnapshot and refresh");
  }
  if (typeof clock !== "function") throw new TypeError("TwinOpsProvider clock must be a function");
  if (!Number.isFinite(pollMs) || pollMs <= 0) {
    throw new TypeError("TwinOpsProvider pollMs must be a positive number");
  }

  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshAttemptAt, setLastRefreshAttemptAt] = useState(null);
  const mountedRef = useRef(false);
  const controllerRef = useRef(null);
  const timerRef = useRef(null);
  const inFlightRef = useRef(null);

  const isVisible = useCallback(
    () => documentRef?.visibilityState === "visible",
    [documentRef]
  );

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const request = useCallback((kind) => {
    const existing = inFlightRef.current;
    if (existing) {
      if (existing.kind === kind) return existing.promise;
      return existing.promise.then(() => {
        if (!mountedRef.current) return null;
        return request(kind);
      });
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    if (kind === "refresh") {
      setRefreshing(true);
      const attemptedAt = clock();
      setLastRefreshAttemptAt(
        attemptedAt instanceof Date && !Number.isNaN(attemptedAt.getTime())
          ? attemptedAt.toISOString()
          : null
      );
    }

    const operation = kind === "refresh"
      ? dataSource.refresh(ASSET_ID, { signal: controller.signal })
      : dataSource.getSnapshot(ASSET_ID, { signal: controller.signal });

    const promise = Promise.resolve(operation)
      .then((value) => {
        if (!mountedRef.current) return null;
        const nextSnapshot = kind === "refresh" ? value?.snapshot : value;
        if (nextSnapshot) setSnapshot(nextSnapshot);
        setError(null);
        return nextSnapshot ?? null;
      })
      .catch((requestError) => {
        if (mountedRef.current && !isAbortError(requestError)) setError(requestError);
        return null;
      })
      .finally(() => {
        if (controllerRef.current === controller) controllerRef.current = null;
        if (inFlightRef.current?.promise === promise) inFlightRef.current = null;
        if (mountedRef.current && kind === "refresh") setRefreshing(false);
      });

    inFlightRef.current = { kind, promise };
    return promise;
  }, [clock, dataSource]);

  const runAutomaticRefreshRef = useRef(null);
  const scheduleNext = useCallback(() => {
    clearTimer();
    if (!mountedRef.current || !isVisible() || !isForzyWindowOpen(clock())) return;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      void runAutomaticRefreshRef.current?.();
    }, pollMs);
  }, [clearTimer, clock, isVisible, pollMs]);

  const runAutomaticRefresh = useCallback(async () => {
    if (!mountedRef.current || !isVisible() || !isForzyWindowOpen(clock())) return;
    await request("refresh");
    scheduleNext();
  }, [clock, isVisible, request, scheduleNext]);
  runAutomaticRefreshRef.current = runAutomaticRefresh;

  const refreshNow = useCallback(async () => {
    if (!mountedRef.current) return null;
    if (isVisible() && isForzyWindowOpen(clock())) return request("refresh");
    return request("snapshot");
  }, [clock, isVisible, request]);

  useEffect(() => {
    mountedRef.current = true;
    let active = true;

    const bootstrap = async () => {
      await request("snapshot");
      if (active && mountedRef.current && isVisible() && isForzyWindowOpen(clock())) {
        await runAutomaticRefresh();
      }
    };
    void bootstrap();

    const onVisibilityChange = () => {
      clearTimer();
      if (!isVisible()) {
        controllerRef.current?.abort();
        return;
      }
      if (isForzyWindowOpen(clock())) void runAutomaticRefresh();
    };
    documentRef?.addEventListener?.("visibilitychange", onVisibilityChange);

    return () => {
      active = false;
      mountedRef.current = false;
      clearTimer();
      controllerRef.current?.abort();
      controllerRef.current = null;
      documentRef?.removeEventListener?.("visibilitychange", onVisibilityChange);
    };
  }, [clearTimer, clock, documentRef, isVisible, request, runAutomaticRefresh]);

  const value = useMemo(() => ({
    assetId: ASSET_ID,
    snapshot,
    error,
    refreshing,
    lastRefreshAttemptAt,
    refreshNow,
  }), [error, lastRefreshAttemptAt, refreshNow, refreshing, snapshot]);

  return <TwinOpsContext.Provider value={value}>{children}</TwinOpsContext.Provider>;
}

export function useTwinOps() {
  const value = useContext(TwinOpsContext);
  if (!value) throw new Error("useTwinOps must be used within TwinOpsProvider");
  return value;
}
