// TwinOpsContext.jsx — orquestra o único ativo real (forzy-motor-01):
//
// - No mount, faz um GET de snapshot.
// - Se a agenda Forzy estiver aberta (seg/ter/qua, [12:00,14:00) em
//   America/Sao_Paulo) e a página estiver visível, dispara um POST de
//   refresh e agenda o próximo ciclo somente no `finally` — assim um
//   refresh lento nunca se sobrepõe ao próximo agendamento.
// - Fora da agenda ou com a página oculta (`document.visibilityState !==
//   "visible"`), o polling automático pausa: nenhum POST é agendado.
// - `refreshNow` (ação manual) respeita a agenda: dentro dela dispara um
//   POST; fora dela apenas relê o GET.
// - Toda requisição em voo é cancelada (`AbortController`) ao ocultar a
//   página e ao desmontar o provider.

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

const ASSET_ID = "forzy-motor-01";

const FORZY_TIMEZONE = "America/Sao_Paulo";
const FORZY_WINDOW_DAYS = new Set(["Mon", "Tue", "Wed"]);
const FORZY_WINDOW_START_MINUTES = 12 * 60;
const FORZY_WINDOW_END_MINUTES = 14 * 60;

const forzyWindowFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: FORZY_TIMEZONE,
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/**
 * Pure helper: is the Forzy collection window open at `date`?
 * Window: Monday, Tuesday, Wednesday, [12:00, 14:00) America/Sao_Paulo,
 * closed at the start, open at the end. Uses Intl.DateTimeFormat against
 * the fixed IANA zone so it never depends on the host/browser timezone.
 */
export function isForzyWindowOpen(date) {
  const parts = forzyWindowFormatter.formatToParts(date);
  const lookup = {};
  for (const part of parts) lookup[part.type] = part.value;
  if (!FORZY_WINDOW_DAYS.has(lookup.weekday)) return false;
  const minutes = Number(lookup.hour) * 60 + Number(lookup.minute);
  return minutes >= FORZY_WINDOW_START_MINUTES && minutes < FORZY_WINDOW_END_MINUTES;
}

const TwinOpsCtx = createContext(null);

// Module-level (not an inline default-parameter literal) so its reference
// stays stable across every re-render where the caller omits `clock`. An
// inline `() => new Date()` default is re-evaluated by the JS engine on
// every call to TwinOpsProvider, which would hand the effect below a brand
// new function identity each time — and because that effect's own
// `setSnapshot`/`setError`/`setRefreshing`/`setLastRefreshAttemptAt` calls
// trigger exactly those re-renders, the effect would tear down and remount
// itself after every state update, forever: an unbounded GET/POST loop
// instead of the pollMs-cadenced schedule.
const DEFAULT_CLOCK = () => new Date();

export function TwinOpsProvider({
  children,
  dataSource,
  clock = DEFAULT_CLOCK,
  pollMs = 5000,
  documentRef = document,
}) {
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshAttemptAt, setLastRefreshAttemptAt] = useState(null);

  // Indirection so the externally-exposed `refreshNow` identity stays
  // stable across renders while always invoking the latest effect's logic.
  const refreshNowRef = useRef(() => Promise.resolve());

  useEffect(() => {
    let mounted = true;
    let timerId = null;
    let abortController = null;

    const isVisible = () => documentRef.visibilityState === "visible";

    const clearTimer = () => {
      if (timerId !== null) {
        clearTimeout(timerId);
        timerId = null;
      }
    };

    const abortInFlight = () => {
      if (abortController) {
        abortController.abort();
        abortController = null;
      }
    };

    // Every automatic cycle — the first one included — goes through this
    // single timer indirection, so there is always at most one pending
    // timer representing "the next tick", scheduled fresh only once the
    // previous cycle's `finally` has run (never overlapping).
    //
    // The timer itself is a plain visibility-gated heartbeat: it keeps
    // ticking every `pollMs` regardless of whether the Forzy window is open,
    // and only the POST call is gated on `isForzyWindowOpen`. If the window
    // is closed when the heartbeat fires, it simply reschedules itself
    // instead of stopping — otherwise a provider that mounts (or resumes
    // visibility) while the window is closed and then stays visible across
    // the window opening (no `visibilitychange` event fires) would never
    // pick the polling back up.
    const scheduleCycle = (delay) => {
      if (!mounted || !isVisible()) return;
      timerId = setTimeout(() => {
        timerId = null;
        if (!isVisible()) return;
        if (isForzyWindowOpen(clock())) {
          runRefreshCycle();
        } else {
          scheduleCycle(pollMs);
        }
      }, delay);
    };

    async function runRefreshCycle() {
      if (!mounted) return;
      const controller = new AbortController();
      abortController = controller;
      setRefreshing(true);
      setLastRefreshAttemptAt(clock());
      try {
        const result = await dataSource.refresh(ASSET_ID, { signal: controller.signal });
        if (!mounted || controller.signal.aborted) return;
        setSnapshot(result.snapshot);
        setError(null);
      } catch (err) {
        if (!mounted || controller.signal.aborted) return;
        setError(err);
      } finally {
        if (abortController === controller) abortController = null;
        if (mounted) setRefreshing(false);
        scheduleCycle(pollMs);
      }
    }

    async function readSnapshot() {
      const controller = new AbortController();
      abortController = controller;
      try {
        const snap = await dataSource.getSnapshot(ASSET_ID, { signal: controller.signal });
        if (!mounted || controller.signal.aborted) return;
        setSnapshot(snap);
        setError(null);
      } catch (err) {
        if (!mounted || controller.signal.aborted) return;
        setError(err);
      } finally {
        if (abortController === controller) abortController = null;
      }
    }

    async function mountCycle() {
      await readSnapshot();
      if (!mounted || !isVisible()) return;
      // Start the heartbeat immediately if the window is already open (first
      // cycle fires right away, as before); otherwise start it on the normal
      // pollMs cadence so it keeps checking until the window opens.
      scheduleCycle(isForzyWindowOpen(clock()) ? 0 : pollMs);
    }

    mountCycle();

    const handleVisibilityChange = () => {
      if (!isVisible()) {
        abortInFlight();
        clearTimer();
        if (mounted) setRefreshing(false);
        return;
      }
      if (timerId !== null || abortController !== null) return;
      if (isForzyWindowOpen(clock())) {
        runRefreshCycle();
      } else {
        // Window is closed right now, but resume the heartbeat so a page
        // that stays visible across the window opening keeps polling.
        scheduleCycle(pollMs);
      }
    };
    documentRef.addEventListener("visibilitychange", handleVisibilityChange);

    refreshNowRef.current = async () => {
      clearTimer();
      abortInFlight();
      if (isForzyWindowOpen(clock())) {
        await runRefreshCycle();
      } else {
        await readSnapshot();
        // The line above didn't go through runRefreshCycle's `finally`, so
        // the heartbeat that clearTimer() just stopped needs restarting
        // here too, or a manual refresh outside the window would silently
        // end automatic polling for the rest of the mount.
        if (mounted && isVisible()) scheduleCycle(pollMs);
      }
    };

    return () => {
      mounted = false;
      documentRef.removeEventListener("visibilitychange", handleVisibilityChange);
      abortInFlight();
      clearTimer();
    };
  }, [dataSource, clock, pollMs, documentRef]);

  const refreshNow = useCallback(() => refreshNowRef.current(), []);

  const value = useMemo(
    () => ({ assetId: ASSET_ID, snapshot, error, refreshing, lastRefreshAttemptAt, refreshNow }),
    [snapshot, error, refreshing, lastRefreshAttemptAt, refreshNow]
  );

  return <TwinOpsCtx.Provider value={value}>{children}</TwinOpsCtx.Provider>;
}

export function useTwinOps() {
  const ctx = useContext(TwinOpsCtx);
  if (!ctx) throw new Error("useTwinOps must be used within a TwinOpsProvider");
  return ctx;
}
