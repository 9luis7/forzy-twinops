import { describe, expect, it } from "vitest";
import {
  committedTimelineContext,
  initialTimelineNavigationState,
  timelineNavigationReducer,
} from "./timelineNavigation.js";

const nowSnapshot = Object.freeze({ marker: "now-1" });
const newerSnapshot = Object.freeze({ marker: "now-2" });
const historicalContext = Object.freeze({ marker: "history-1" });
const newerHistoricalContext = Object.freeze({ marker: "history-2" });

const reduce = (...actions) => actions.reduce(
  (state, action) => timelineNavigationReducer(state, action),
  initialTimelineNavigationState
);

describe("timelineNavigationReducer", () => {
  it("keeps the now display while history has no committed context", () => {
    const state = reduce({ type: "SHOW_HISTORY" });

    expect(state.viewMode).toBe("historical");
    expect(state.historicalContext).toBeNull();
    expect(committedTimelineContext(state, nowSnapshot)).toBe(nowSnapshot);
  });

  it("keeps the prior committed context while another selection is pending", () => {
    const committed = reduce(
      { type: "CONTEXT_REQUESTED", selection: { pointId: "point-1" } },
      { type: "CONTEXT_RESOLVED", context: historicalContext },
    );
    const pending = timelineNavigationReducer(committed, {
      type: "CONTEXT_REQUESTED",
      selection: { pointId: "point-2" },
    });

    expect(pending.pendingSelection).toEqual({ pointId: "point-2" });
    expect(pending.loading.context).toBe(true);
    expect(pending.historicalContext).toBe(historicalContext);
    expect(committedTimelineContext(pending, newerSnapshot)).toBe(historicalContext);
  });

  it("commits a complete historical context in one reducer result", () => {
    const pending = reduce({
      type: "CONTEXT_REQUESTED",
      selection: { pointId: "point-2" },
    });
    const committed = timelineNavigationReducer(pending, {
      type: "CONTEXT_RESOLVED",
      context: newerHistoricalContext,
    });

    expect(committed).toMatchObject({
      viewMode: "historical",
      pendingSelection: null,
      historicalContext: newerHistoricalContext,
      loading: { context: false },
      errors: { context: null },
    });
    expect(committedTimelineContext(committed, nowSnapshot)).toBe(newerHistoricalContext);
  });

  it("preserves the exact committed context when selection fails", () => {
    const failure = new Error("context unavailable");
    const committed = reduce(
      { type: "CONTEXT_REQUESTED", selection: { pointId: "point-1" } },
      { type: "CONTEXT_RESOLVED", context: historicalContext },
      { type: "CONTEXT_REQUESTED", selection: { pointId: "point-2" } },
    );
    const failed = timelineNavigationReducer(committed, {
      type: "CONTEXT_FAILED",
      error: failure,
    });

    expect(failed.historicalContext).toBe(historicalContext);
    expect(failed.pendingSelection).toBeNull();
    expect(failed.loading.context).toBe(false);
    expect(failed.errors.context).toBe(failure);
    expect(committedTimelineContext(failed, newerSnapshot)).toBe(historicalContext);
  });

  it("returns to the latest now snapshot without discarding historical context", () => {
    const historical = reduce(
      { type: "CONTEXT_REQUESTED", selection: { pointId: "point-1" } },
      { type: "CONTEXT_RESOLVED", context: historicalContext },
    );
    const now = timelineNavigationReducer(historical, { type: "SHOW_NOW" });

    expect(now.viewMode).toBe("now");
    expect(now.historicalContext).toBe(historicalContext);
    expect(committedTimelineContext(now, newerSnapshot)).toBe(newerSnapshot);
  });

  it("tracks overview and page loading and errors independently", () => {
    const overviewError = new Error("overview failed");
    const page = Object.freeze({ items: [] });
    const state = reduce(
      { type: "OVERVIEW_REQUESTED" },
      { type: "PAGE_REQUESTED" },
      { type: "OVERVIEW_FAILED", error: overviewError },
      { type: "PAGE_RESOLVED", page },
    );

    expect(state.timelineOverview).toBeNull();
    expect(state.timelinePage).toBe(page);
    expect(state.loading).toEqual({ overview: false, page: false, context: false });
    expect(state.errors).toEqual({ overview: overviewError, page: null, context: null });
  });

  it("rejects unknown actions", () => {
    expect(() => timelineNavigationReducer(initialTimelineNavigationState, {
      type: "UNKNOWN",
    })).toThrow(/UNKNOWN/);
  });

  it("resets source-owned timeline state without retaining prior evidence", () => {
    const historical = reduce(
      { type: "OVERVIEW_RESOLVED", overview: { marker: "overview" } },
      { type: "CONTEXT_REQUESTED", selection: { pointId: "point-1" } },
      { type: "CONTEXT_RESOLVED", context: historicalContext },
    );

    const reset = timelineNavigationReducer(historical, { type: "RESET" });

    expect(reset).toBe(initialTimelineNavigationState);
  });
});
