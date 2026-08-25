import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import {
  assertTimelineContextV1,
  assertTimelineOverviewV1,
  assertTimelinePageV1,
} from "./contracts/timelineV1.js";
import { createGatewayTwinDataSourceV2 } from "./dataSources/GatewayTwinDataSourceV2.js";
import {
  committedTimelineContext,
  initialTimelineNavigationState,
  timelineNavigationReducer,
} from "./state/timelineNavigation.js";

const ASSET_ID = "forzy-motor-01";
const TwinOpsContext = createContext(null);
const defaultDataSource = createGatewayTwinDataSourceV2();
const defaultClock = () => new Date();
const TIMELINE_POINT_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const INITIAL_TIMELINE_METRIC = "vibrationVelocityRms";
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
  clock = defaultClock,
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
  const [timelineState, dispatchTimeline] = useReducer(
    timelineNavigationReducer,
    initialTimelineNavigationState
  );
  const mountedRef = useRef(false);
  const effectGenerationRef = useRef(0);
  const timerRef = useRef(null);
  const inFlightRef = useRef(null);
  const refreshingOwnerRef = useRef(null);
  const overviewRequestRef = useRef(null);
  const pageRequestRef = useRef(null);
  const contextRequestRef = useRef(null);
  const timelineDataSourceRef = useRef(dataSource);

  const isVisible = useCallback(
    () => documentRef?.visibilityState === "visible",
    [documentRef]
  );

  const clearTimer = useCallback((generation) => {
    const timerOwner = timerRef.current;
    if (
      timerOwner === null
      || (generation !== undefined && timerOwner.generation !== generation)
    ) return;
    clearTimeout(timerOwner.id);
    if (timerRef.current === timerOwner) timerRef.current = null;
  }, []);

  const abortActiveRequest = useCallback((generation) => {
    const activeRequest = inFlightRef.current;
    if (activeRequest?.generation === generation) {
      inFlightRef.current = null;
      activeRequest.controller.abort();
    }

    const refreshingOwner = refreshingOwnerRef.current;
    if (refreshingOwner?.generation === generation) {
      refreshingOwnerRef.current = null;
      setRefreshing(false);
    }
  }, []);

  const abortTimelineRequest = useCallback((requestRef) => {
    const owner = requestRef.current;
    if (owner === null) return;
    requestRef.current = null;
    owner.controller.abort();
  }, []);

  const abortAllTimelineRequests = useCallback(() => {
    abortTimelineRequest(overviewRequestRef);
    abortTimelineRequest(pageRequestRef);
    abortTimelineRequest(contextRequestRef);
  }, [abortTimelineRequest]);

  const beginTimelineRequest = useCallback((requestRef) => {
    abortTimelineRequest(requestRef);
    const owner = { controller: new AbortController() };
    requestRef.current = owner;
    return owner;
  }, [abortTimelineRequest]);

  const loadTimelineOverview = useCallback(() => {
    const owner = beginTimelineRequest(overviewRequestRef);
    dispatchTimeline({ type: "OVERVIEW_REQUESTED" });
    let operation;
    try {
      if (typeof dataSource.getTimelineOverview !== "function") {
        throw new TypeError("TwinOpsProvider dataSource must implement getTimelineOverview");
      }
      operation = dataSource.getTimelineOverview(ASSET_ID, {
        sensorId: "all",
        metric: INITIAL_TIMELINE_METRIC,
        maxPoints: 1200,
        signal: owner.controller.signal,
      });
    } catch (requestError) {
      operation = Promise.reject(requestError);
    }
    return Promise.resolve(operation)
      .then((value) => assertTimelineOverviewV1(value))
      .then((value) => {
        if (overviewRequestRef.current !== owner || owner.controller.signal.aborted) return null;
        dispatchTimeline({ type: "OVERVIEW_RESOLVED", overview: value });
        return value;
      })
      .catch((requestError) => {
        if (
          overviewRequestRef.current === owner
          && !owner.controller.signal.aborted
        ) {
          dispatchTimeline({ type: "OVERVIEW_FAILED", error: requestError });
        }
        return null;
      })
      .finally(() => {
        if (overviewRequestRef.current === owner) overviewRequestRef.current = null;
      });
  }, [beginTimelineRequest, dataSource]);

  const loadTimelinePage = useCallback(() => {
    const owner = beginTimelineRequest(pageRequestRef);
    dispatchTimeline({ type: "PAGE_REQUESTED" });
    let operation;
    try {
      if (typeof dataSource.getTimelineSamples !== "function") {
        throw new TypeError("TwinOpsProvider dataSource must implement getTimelineSamples");
      }
      operation = dataSource.getTimelineSamples(ASSET_ID, {
        sensorId: "all",
        metric: INITIAL_TIMELINE_METRIC,
        limit: 200,
        signal: owner.controller.signal,
      });
    } catch (requestError) {
      operation = Promise.reject(requestError);
    }
    return Promise.resolve(operation)
      .then((value) => assertTimelinePageV1(value))
      .then((value) => {
        if (pageRequestRef.current !== owner || owner.controller.signal.aborted) return null;
        dispatchTimeline({ type: "PAGE_RESOLVED", page: value });
        return value;
      })
      .catch((requestError) => {
        if (
          pageRequestRef.current === owner
          && !owner.controller.signal.aborted
        ) {
          dispatchTimeline({ type: "PAGE_FAILED", error: requestError });
        }
        return null;
      })
      .finally(() => {
        if (pageRequestRef.current === owner) pageRequestRef.current = null;
      });
  }, [beginTimelineRequest, dataSource]);

  const showHistory = useCallback(() => {
    dispatchTimeline({ type: "SHOW_HISTORY" });
    const overviewPromise = loadTimelineOverview();
    const pagePromise = loadTimelinePage();
    return Promise.all([overviewPromise, pagePromise]);
  }, [loadTimelineOverview, loadTimelinePage]);

  const selectTimelinePoint = useCallback((pointId) => {
    if (typeof pointId !== "string" || !TIMELINE_POINT_ID_RE.test(pointId)) {
      throw new TypeError("TwinOps timeline pointId must be a canonical UUIDv5");
    }
    const owner = beginTimelineRequest(contextRequestRef);
    dispatchTimeline({ type: "CONTEXT_REQUESTED", selection: { pointId } });
    let operation;
    try {
      if (typeof dataSource.getTimelineContext !== "function") {
        throw new TypeError("TwinOpsProvider dataSource must implement getTimelineContext");
      }
      operation = dataSource.getTimelineContext(ASSET_ID, {
        pointId,
        signal: owner.controller.signal,
      });
    } catch (requestError) {
      operation = Promise.reject(requestError);
    }
    return Promise.resolve(operation)
      .then((value) => assertTimelineContextV1(value))
      .then((value) => {
        if (value.anchor?.pointId !== pointId) {
          throw new TypeError("TwinOps timeline context does not match the selected pointId");
        }
        if (contextRequestRef.current !== owner || owner.controller.signal.aborted) return null;
        dispatchTimeline({ type: "CONTEXT_RESOLVED", context: value });
        return value;
      })
      .catch((requestError) => {
        if (
          contextRequestRef.current === owner
          && !owner.controller.signal.aborted
        ) {
          dispatchTimeline({ type: "CONTEXT_FAILED", error: requestError });
        }
        return null;
      })
      .finally(() => {
        if (contextRequestRef.current === owner) contextRequestRef.current = null;
      });
  }, [beginTimelineRequest, dataSource]);

  const showNow = useCallback(() => {
    abortAllTimelineRequests();
    dispatchTimeline({ type: "SHOW_NOW" });
  }, [abortAllTimelineRequests]);

  useEffect(() => {
    if (timelineDataSourceRef.current !== dataSource) {
      timelineDataSourceRef.current = dataSource;
      dispatchTimeline({ type: "RESET" });
    }
    return abortAllTimelineRequests;
  }, [abortAllTimelineRequests, dataSource]);

  const request = useCallback((kind, generation = effectGenerationRef.current) => {
    if (!mountedRef.current || effectGenerationRef.current !== generation) {
      return Promise.resolve(null);
    }

    const existing = inFlightRef.current;
    if (existing && existing.generation === generation && !existing.controller.signal.aborted) {
      if (existing.kind === kind) return existing.promise;
      return existing.promise.then(() => {
        if (!mountedRef.current || effectGenerationRef.current !== generation) return null;
        return request(kind, generation);
      });
    }

    const controller = new AbortController();
    const requestOwner = { kind, controller, generation, promise: null };
    if (kind === "refresh") {
      refreshingOwnerRef.current = requestOwner;
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
        if (!mountedRef.current || effectGenerationRef.current !== generation) return null;
        const nextSnapshot = kind === "refresh" ? value?.snapshot : value;
        if (nextSnapshot) setSnapshot(nextSnapshot);
        setError(null);
        return nextSnapshot ?? null;
      })
      .catch((requestError) => {
        if (
          mountedRef.current
          && effectGenerationRef.current === generation
          && !isAbortError(requestError)
        ) setError(requestError);
        return null;
      })
      .finally(() => {
        if (inFlightRef.current === requestOwner) inFlightRef.current = null;
        if (kind === "refresh" && refreshingOwnerRef.current === requestOwner) {
          refreshingOwnerRef.current = null;
          setRefreshing(false);
        }
      });

    requestOwner.promise = promise;
    inFlightRef.current = requestOwner;
    return promise;
  }, [clock, dataSource]);

  const runAutomaticRefreshRef = useRef(null);
  const scheduleNext = useCallback((generation = effectGenerationRef.current) => {
    if (
      !mountedRef.current
      || effectGenerationRef.current !== generation
      || !isVisible()
      || !isForzyWindowOpen(clock())
    ) return;

    clearTimer(generation);
    const timerOwner = { generation, id: null };
    timerOwner.id = setTimeout(() => {
      if (
        timerRef.current !== timerOwner
        || !mountedRef.current
        || effectGenerationRef.current !== generation
      ) return;
      timerRef.current = null;
      void runAutomaticRefreshRef.current?.(generation);
    }, pollMs);
    timerRef.current = timerOwner;
  }, [clearTimer, clock, isVisible, pollMs]);

  const runAutomaticRefresh = useCallback(async (generation = effectGenerationRef.current) => {
    if (
      !mountedRef.current
      || effectGenerationRef.current !== generation
      || !isVisible()
      || !isForzyWindowOpen(clock())
    ) return;
    await request("refresh", generation);
    scheduleNext(generation);
  }, [clock, isVisible, request, scheduleNext]);
  runAutomaticRefreshRef.current = runAutomaticRefresh;

  const refreshNow = useCallback(async () => {
    if (!mountedRef.current) return null;
    if (isVisible() && isForzyWindowOpen(clock())) return request("refresh");
    return request("snapshot");
  }, [clock, isVisible, request]);

  useEffect(() => {
    const generation = effectGenerationRef.current + 1;
    effectGenerationRef.current = generation;
    mountedRef.current = true;
    let active = true;

    const bootstrap = async () => {
      await request("snapshot", generation);
      if (
        active
        && mountedRef.current
        && effectGenerationRef.current === generation
        && isVisible()
        && isForzyWindowOpen(clock())
      ) {
        await runAutomaticRefresh(generation);
      }
    };
    void bootstrap();

    const onVisibilityChange = () => {
      if (!mountedRef.current || effectGenerationRef.current !== generation) return;
      clearTimer(generation);
      if (!isVisible()) {
        abortActiveRequest(generation);
        return;
      }
      if (isForzyWindowOpen(clock())) void runAutomaticRefresh(generation);
    };
    documentRef?.addEventListener?.("visibilitychange", onVisibilityChange);

    return () => {
      active = false;
      clearTimer(generation);
      abortActiveRequest(generation);
      if (effectGenerationRef.current === generation) mountedRef.current = false;
      documentRef?.removeEventListener?.("visibilitychange", onVisibilityChange);
    };
  }, [abortActiveRequest, clearTimer, clock, documentRef, isVisible, request, runAutomaticRefresh]);

  const displayContext = committedTimelineContext(timelineState, snapshot);
  const value = useMemo(() => ({
    assetId: ASSET_ID,
    snapshot,
    error,
    refreshing,
    lastRefreshAttemptAt,
    refreshNow,
    viewMode: timelineState.viewMode,
    timelineOverview: timelineState.timelineOverview,
    timelinePage: timelineState.timelinePage,
    pendingSelection: timelineState.pendingSelection,
    historicalContext: timelineState.historicalContext,
    displayContext,
    timelineLoading: timelineState.loading,
    timelineErrors: timelineState.errors,
    timelineState,
    showNow,
    showHistory,
    selectTimelinePoint,
  }), [
    displayContext,
    error,
    lastRefreshAttemptAt,
    refreshNow,
    refreshing,
    selectTimelinePoint,
    showHistory,
    showNow,
    snapshot,
    timelineState,
  ]);

  return <TwinOpsContext.Provider value={value}>{children}</TwinOpsContext.Provider>;
}

export function useTwinOps() {
  const value = useContext(TwinOpsContext);
  if (!value) throw new Error("useTwinOps must be used within TwinOpsProvider");
  return value;
}
