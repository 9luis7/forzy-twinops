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
  assertTimelineAssessmentOverviewV1,
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
const TIMELINE_CACHE_SCHEMA_VERSION = 1;
const TIMELINE_CACHE_STORAGE_KEY = "twinops:timeline-bundles:v1";
const DEFAULT_TIMELINE_CACHE_TTL_MS = 600_000;
const TIMELINE_RANGE_DAYS = Object.freeze({
  "24h": 1,
  "7d": 7,
  "14d": 14,
  "30d": 30,
});
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

const historicalArchiveRangeQuery = (overview) => {
  const segments = overview?.segments?.filter(
    (segment) => segment.sourceKind === "historical_archive",
  ) ?? [];
  if (segments.length === 0) {
    throw new TypeError("TwinOps historical archive range is unavailable");
  }
  const starts = segments.map((segment) => Date.parse(segment.startAt));
  const ends = segments.map((segment) => Date.parse(segment.endAt));
  if ([...starts, ...ends].some((value) => !Number.isFinite(value))) {
    throw new TypeError("TwinOps historical archive range is invalid");
  }
  return Object.freeze({
    from: new Date(Math.min(...starts)).toISOString(),
    to: new Date(Math.max(...ends) + 1).toISOString(),
  });
};

const timelineRangeQuery = (preset, now, overview = null) => {
  if (preset === "all") return Object.freeze({});
  if (preset === "historical") return historicalArchiveRangeQuery(overview);
  const days = TIMELINE_RANGE_DAYS[preset];
  if (days === undefined) throw new TypeError("TwinOps timeline range preset is invalid");
  if (!(now instanceof Date) || Number.isNaN(now.getTime())) {
    throw new TypeError("TwinOps timeline range clock must return a valid Date");
  }
  return Object.freeze({
    from: new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString(),
    to: now.toISOString(),
  });
};

const timelineRangeCacheKey = (rangeQuery) => JSON.stringify({
  schemaVersion: "1.0",
  assetId: ASSET_ID,
  sensorId: "all",
  metric: INITIAL_TIMELINE_METRIC,
  overviewMaxPoints: 1200,
  pageLimit: 200,
  assessmentsMaxPoints: 800,
  from: rangeQuery.from ?? null,
  to: rangeQuery.to ?? null,
});

const isPlainObject = (value) => (
  value !== null && typeof value === "object" && !Array.isArray(value)
);

const safeRemoveStoredTimelineCache = (storage) => {
  try {
    storage?.removeItem?.(TIMELINE_CACHE_STORAGE_KEY);
  } catch {
    // sessionStorage is an optional optimization and may be unavailable.
  }
};

const readStoredTimelineCache = (storage) => {
  if (storage === null) return { entries: {} };
  try {
    const raw = storage.getItem(TIMELINE_CACHE_STORAGE_KEY);
    if (raw === null) return { entries: {} };
    const parsed = JSON.parse(raw);
    if (
      !isPlainObject(parsed)
      || parsed.schemaVersion !== TIMELINE_CACHE_SCHEMA_VERSION
      || !isPlainObject(parsed.entries)
    ) throw new TypeError("TwinOps timeline cache document is invalid");
    return parsed;
  } catch {
    safeRemoveStoredTimelineCache(storage);
    return { entries: {} };
  }
};

const writeStoredTimelineCache = (storage, document) => {
  if (storage === null) return;
  try {
    if (Object.keys(document.entries).length === 0) {
      storage.removeItem(TIMELINE_CACHE_STORAGE_KEY);
      return;
    }
    storage.setItem(TIMELINE_CACHE_STORAGE_KEY, JSON.stringify({
      schemaVersion: TIMELINE_CACHE_SCHEMA_VERSION,
      entries: document.entries,
    }));
  } catch {
    // Quota, privacy, and serialization failures must not break navigation.
  }
};

const defaultTimelineCacheStorage = () => {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
};

const assertTimelineBundle = (candidate, rangeQuery = null) => {
  if (!isPlainObject(candidate)) {
    throw new TypeError("TwinOps timeline bundle must be an object");
  }
  const overview = assertTimelineOverviewV1(candidate.overview);
  const page = assertTimelinePageV1(candidate.page);
  const assessmentOverview = assertTimelineAssessmentOverviewV1(candidate.assessmentOverview);
  if (
    overview.assetId !== ASSET_ID
    || page.assetId !== ASSET_ID
    || assessmentOverview.assetId !== ASSET_ID
  ) throw new TypeError("TwinOps timeline bundle assetId is inconsistent");
  if (
    overview.activeHistoricalBatchId !== page.activeHistoricalBatchId
    || overview.activeHistoricalBatchId !== assessmentOverview.activeHistoricalBatchId
  ) throw new TypeError("TwinOps timeline bundle activeHistoricalBatchId is inconsistent");
  if (
    overview.aggregationSummary.requestedMaxPoints !== 1200
    || page.limit !== 200
    || assessmentOverview.aggregationSummary.requestedMaxPoints !== 800
  ) throw new TypeError("TwinOps timeline bundle query budget is inconsistent");
  if (rangeQuery !== null) {
    const expectedFrom = rangeQuery.from ?? null;
    const expectedTo = rangeQuery.to ?? null;
    for (const payload of [overview, assessmentOverview]) {
      if (
        payload.requestedRange.from !== expectedFrom
        || payload.requestedRange.to !== expectedTo
      ) throw new TypeError("TwinOps timeline bundle requestedRange does not match its cache key");
    }
    const fromTime = expectedFrom === null ? null : Date.parse(expectedFrom);
    const toTime = expectedTo === null ? null : Date.parse(expectedTo);
    for (const item of page.items) {
      const eventTime = Date.parse(item.eventAt);
      if (
        (fromTime !== null && eventTime < fromTime)
        || (toTime !== null && eventTime >= toTime)
      ) throw new TypeError("TwinOps timeline page item is outside the requested range");
    }
  }
  return Object.freeze({ overview, page, assessmentOverview });
};

export function TwinOpsProvider({
  children,
  dataSource = defaultDataSource,
  clock = defaultClock,
  pollMs = 5000,
  documentRef = document,
  timelineCacheStorage,
  timelineCacheTtlMs = DEFAULT_TIMELINE_CACHE_TTL_MS,
}) {
  if (!dataSource || typeof dataSource.getSnapshot !== "function" || typeof dataSource.refresh !== "function") {
    throw new TypeError("TwinOpsProvider dataSource must implement getSnapshot and refresh");
  }
  if (typeof clock !== "function") throw new TypeError("TwinOpsProvider clock must be a function");
  if (!Number.isFinite(pollMs) || pollMs <= 0) {
    throw new TypeError("TwinOpsProvider pollMs must be a positive number");
  }
  if (!Number.isFinite(timelineCacheTtlMs) || timelineCacheTtlMs <= 0) {
    throw new TypeError("TwinOpsProvider timelineCacheTtlMs must be a positive number");
  }
  const resolvedTimelineCacheStorage = timelineCacheStorage === undefined
    ? defaultTimelineCacheStorage()
    : timelineCacheStorage;

  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshAttemptAt, setLastRefreshAttemptAt] = useState(null);
  const [timelineRangePreset, setTimelineRangePreset] = useState("all");
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
  const assessmentsRequestRef = useRef(null);
  const contextRequestRef = useRef(null);
  const timelineDataSourceRef = useRef(dataSource);
  const timelineRangeCacheRef = useRef(new Map());
  const timelineCacheEpochRef = useRef(0);
  const latestTimelineAvailableToRef = useRef(null);
  const historicalArchiveRangeRef = useRef(null);
  const timelineBundleOwnerRef = useRef(null);
  const timelineBundleInFlightRef = useRef(new Map());

  const readTimelineBundleCache = useCallback((cacheKey, rangeQuery) => {
    const now = Date.now();
    const validateEntry = (entry) => {
      if (
        !isPlainObject(entry)
        || entry.cacheKey !== cacheKey
        || !Number.isFinite(entry.createdAt)
        || !Number.isFinite(entry.expiresAt)
        || entry.createdAt > now
        || entry.expiresAt <= now
        || entry.expiresAt - entry.createdAt !== timelineCacheTtlMs
      ) throw new TypeError("TwinOps timeline cache entry is expired or invalid");
      return assertTimelineBundle(entry.bundle, rangeQuery);
    };

    const memoryEntry = timelineRangeCacheRef.current.get(cacheKey);
    if (memoryEntry !== undefined) {
      try {
        return validateEntry(memoryEntry);
      } catch {
        timelineRangeCacheRef.current.delete(cacheKey);
      }
    }

    const document = readStoredTimelineCache(resolvedTimelineCacheStorage);
    const storedEntry = document.entries[cacheKey];
    if (storedEntry === undefined) return null;
    try {
      const bundle = validateEntry(storedEntry);
      timelineRangeCacheRef.current.set(cacheKey, storedEntry);
      return bundle;
    } catch {
      delete document.entries[cacheKey];
      writeStoredTimelineCache(resolvedTimelineCacheStorage, document);
      return null;
    }
  }, [resolvedTimelineCacheStorage, timelineCacheTtlMs]);

  const writeTimelineBundleCache = useCallback((cacheKey, rangeQuery, candidate) => {
    const bundle = assertTimelineBundle(candidate, rangeQuery);
    const createdAt = Date.now();
    const entry = Object.freeze({
      cacheKey,
      createdAt,
      expiresAt: createdAt + timelineCacheTtlMs,
      bundle,
    });
    timelineRangeCacheRef.current.set(cacheKey, entry);
    const document = readStoredTimelineCache(resolvedTimelineCacheStorage);
    document.entries[cacheKey] = entry;
    writeStoredTimelineCache(resolvedTimelineCacheStorage, document);
    return bundle;
  }, [resolvedTimelineCacheStorage, timelineCacheTtlMs]);

  const clearTimelineBundleCache = useCallback(() => {
    timelineCacheEpochRef.current += 1;
    timelineRangeCacheRef.current.clear();
    timelineBundleInFlightRef.current.clear();
    safeRemoveStoredTimelineCache(resolvedTimelineCacheStorage);
  }, [resolvedTimelineCacheStorage]);

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
    timelineBundleOwnerRef.current = null;
    timelineBundleInFlightRef.current.clear();
    abortTimelineRequest(overviewRequestRef);
    abortTimelineRequest(pageRequestRef);
    abortTimelineRequest(assessmentsRequestRef);
    abortTimelineRequest(contextRequestRef);
  }, [abortTimelineRequest]);

  const beginTimelineRequest = useCallback((requestRef) => {
    abortTimelineRequest(requestRef);
    const owner = { controller: new AbortController() };
    requestRef.current = owner;
    return owner;
  }, [abortTimelineRequest]);

  const loadTimelineOverview = useCallback((rangeQuery = {}) => {
    const owner = beginTimelineRequest(overviewRequestRef);
    dispatchTimeline({ type: "OVERVIEW_REQUESTED" });
    let operation;
    try {
      if (typeof dataSource.getTimelineOverview !== "function") {
        throw new TypeError("TwinOpsProvider dataSource must implement getTimelineOverview");
      }
      operation = dataSource.getTimelineOverview(ASSET_ID, {
        ...rangeQuery,
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

  const loadTimelinePage = useCallback((rangeQuery = {}) => {
    const owner = beginTimelineRequest(pageRequestRef);
    dispatchTimeline({ type: "PAGE_REQUESTED" });
    let operation;
    try {
      if (typeof dataSource.getTimelineSamples !== "function") {
        throw new TypeError("TwinOpsProvider dataSource must implement getTimelineSamples");
      }
      operation = dataSource.getTimelineSamples(ASSET_ID, {
        ...rangeQuery,
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

  const loadTimelineAssessments = useCallback((rangeQuery = {}) => {
    const owner = beginTimelineRequest(assessmentsRequestRef);
    dispatchTimeline({ type: "ASSESSMENTS_REQUESTED" });
    let operation;
    try {
      if (typeof dataSource.getTimelineAssessments !== "function") {
        throw new TypeError("TwinOpsProvider dataSource must implement getTimelineAssessments");
      }
      operation = dataSource.getTimelineAssessments(ASSET_ID, {
        ...rangeQuery,
        sensorId: "all",
        maxPoints: 800,
      }, {
        signal: owner.controller.signal,
      });
    } catch (requestError) {
      operation = Promise.reject(requestError);
    }
    return Promise.resolve(operation)
      .then((value) => assertTimelineAssessmentOverviewV1(value))
      .then((value) => {
        if (assessmentsRequestRef.current !== owner || owner.controller.signal.aborted) return null;
        return value;
      })
      .catch((requestError) => {
        if (assessmentsRequestRef.current === owner && !owner.controller.signal.aborted) {
          dispatchTimeline({ type: "ASSESSMENTS_FAILED", error: requestError });
        }
        return null;
      })
      .finally(() => {
        if (assessmentsRequestRef.current === owner) assessmentsRequestRef.current = null;
      });
  }, [beginTimelineRequest, dataSource]);

  const observeTimelineOverview = useCallback((overview) => {
    const availableTo = Date.parse(overview.availableRange?.to ?? "");
    const latestAvailableTo = Date.parse(latestTimelineAvailableToRef.current ?? "");
    if (Number.isFinite(availableTo)
      && (!Number.isFinite(latestAvailableTo) || availableTo > latestAvailableTo)) {
      latestTimelineAvailableToRef.current = overview.availableRange.to;
    }
    if (overview.segments?.some((segment) => segment.sourceKind === "historical_archive")) {
      historicalArchiveRangeRef.current = historicalArchiveRangeQuery(overview);
    }
  }, []);

  const restoreTimelineBundle = useCallback((candidate, rangeQuery) => {
    const bundle = assertTimelineBundle(candidate, rangeQuery);
    observeTimelineOverview(bundle.overview);
    dispatchTimeline({ type: "BUNDLE_RESOLVED", bundle });
    return [bundle.overview, bundle.page, bundle.assessmentOverview];
  }, [observeTimelineOverview]);

  const loadTimelineBundle = useCallback((rangeQuery, { readCache = true } = {}) => {
    const cacheKey = timelineRangeCacheKey(rangeQuery);
    const cached = readCache ? readTimelineBundleCache(cacheKey, rangeQuery) : null;
    if (cached !== null) restoreTimelineBundle(cached, rangeQuery);
    const existingRequest = timelineBundleInFlightRef.current.get(cacheKey);
    if (existingRequest !== undefined) return existingRequest;
    timelineBundleInFlightRef.current.clear();

    const bundleOwner = {};
    const cacheEpoch = timelineCacheEpochRef.current;
    timelineBundleOwnerRef.current = bundleOwner;
    const overviewPromise = loadTimelineOverview(rangeQuery);
    const pagePromise = loadTimelinePage(rangeQuery);
    const assessmentPromise = loadTimelineAssessments(rangeQuery);
    const promise = Promise.all([overviewPromise, pagePromise, assessmentPromise])
      .then(([overview, page, assessmentOverview]) => {
        if (timelineBundleOwnerRef.current !== bundleOwner) {
          return [overview, page, assessmentOverview];
        }
        if (overview !== null && page !== null && assessmentOverview !== null) {
          let bundle;
          try {
            bundle = assertTimelineBundle({ overview, page, assessmentOverview }, rangeQuery);
          } catch (bundleError) {
            dispatchTimeline({ type: "OVERVIEW_FAILED", error: bundleError });
            dispatchTimeline({ type: "PAGE_FAILED", error: bundleError });
            dispatchTimeline({ type: "ASSESSMENTS_FAILED", error: bundleError });
            return [null, null, null];
          }
          restoreTimelineBundle(bundle, rangeQuery);
          if (timelineCacheEpochRef.current === cacheEpoch) {
            writeTimelineBundleCache(cacheKey, rangeQuery, bundle);
          }
          return [bundle.overview, bundle.page, bundle.assessmentOverview];
        }

        if (overview !== null) dispatchTimeline({ type: "OVERVIEW_FAILED", error: null });
        if (page !== null) dispatchTimeline({ type: "PAGE_FAILED", error: null });
        if (assessmentOverview !== null) {
          dispatchTimeline({ type: "ASSESSMENTS_FAILED", error: null });
        }
        return [overview, page, assessmentOverview];
      })
      .finally(() => {
        if (timelineBundleInFlightRef.current.get(cacheKey) === promise) {
          timelineBundleInFlightRef.current.delete(cacheKey);
        }
        if (timelineBundleOwnerRef.current === bundleOwner) {
          timelineBundleOwnerRef.current = null;
        }
      });
    timelineBundleInFlightRef.current.set(cacheKey, promise);
    return promise;
  }, [
    loadTimelineAssessments,
    loadTimelineOverview,
    loadTimelinePage,
    readTimelineBundleCache,
    restoreTimelineBundle,
    writeTimelineBundleCache,
  ]);

  const loadHistoricalRange = useCallback((preset) => {
    const rangeQuery = timelineRangeQuery(preset, clock(), timelineState.timelineOverview);
    return loadTimelineBundle(rangeQuery);
  }, [
    clock,
    loadTimelineBundle,
    timelineState.timelineOverview,
  ]);

  const showHistory = useCallback(() => {
    dispatchTimeline({ type: "SHOW_HISTORY" });
    return loadHistoricalRange(timelineRangePreset);
  }, [loadHistoricalRange, timelineRangePreset]);

  const selectTimelineRange = useCallback((preset) => {
    const availableTo = latestTimelineAvailableToRef.current
      ?? timelineState.timelineOverview?.availableRange?.to
      ?? null;
    const anchor = availableTo === null ? clock() : new Date(availableTo);
    const rangeQuery = preset === "historical" && historicalArchiveRangeRef.current !== null
      ? historicalArchiveRangeRef.current
      : timelineRangeQuery(preset, anchor, timelineState.timelineOverview);
    abortTimelineRequest(contextRequestRef);
    setTimelineRangePreset(preset);
    dispatchTimeline({ type: "SHOW_HISTORY" });
    return loadTimelineBundle(rangeQuery);
  }, [
    abortTimelineRequest,
    clock,
    loadTimelineBundle,
    timelineState.timelineOverview,
  ]);

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
      clearTimelineBundleCache();
      latestTimelineAvailableToRef.current = null;
      historicalArchiveRangeRef.current = null;
      dispatchTimeline({ type: "RESET" });
    }
    return abortAllTimelineRequests;
  }, [abortAllTimelineRequests, clearTimelineBundleCache, dataSource]);

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
    const isManualRequest = kind === "refresh" || kind === "manual-snapshot";
    if (kind === "refresh") timelineCacheEpochRef.current += 1;
    if (isManualRequest) {
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
        if (isManualRequest && refreshingOwnerRef.current === requestOwner) {
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
    return request("manual-snapshot");
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
    timelineAssessmentOverview: timelineState.timelineAssessmentOverview,
    pendingSelection: timelineState.pendingSelection,
    historicalContext: timelineState.historicalContext,
    displayContext,
    timelineLoading: timelineState.loading,
    timelineErrors: timelineState.errors,
    timelineState,
    timelineRangePreset,
    showNow,
    showHistory,
    selectTimelineRange,
    selectTimelinePoint,
  }), [
    displayContext,
    error,
    lastRefreshAttemptAt,
    refreshNow,
    refreshing,
    selectTimelinePoint,
    selectTimelineRange,
    showHistory,
    showNow,
    snapshot,
    timelineState,
    timelineRangePreset,
  ]);

  return <TwinOpsContext.Provider value={value}>{children}</TwinOpsContext.Provider>;
}

export function useTwinOps() {
  const value = useContext(TwinOpsContext);
  if (!value) throw new Error("useTwinOps must be used within TwinOpsProvider");
  return value;
}

export function useOptionalTwinOps() {
  return useContext(TwinOpsContext);
}
