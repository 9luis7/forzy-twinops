import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { TwinOpsProvider, isForzyWindowOpen, useTwinOps } from "./TwinOpsContext.jsx";

function makeSnapshot(id) {
  return { schemaVersion: "2.0", asset: { assetId: "forzy-motor-01" }, marker: id };
}

function sourceStub({ snapshot = makeSnapshot("initial") } = {}) {
  return {
    getSnapshot: vi.fn(() => Promise.resolve(snapshot)),
    refresh: vi.fn(() => Promise.resolve({ refreshAttempted: true, outcomes: {}, snapshot: makeSnapshot("refreshed") })),
  };
}

function fakeDocument(initialVisibility = "visible") {
  const listeners = new Set();
  return {
    visibilityState: initialVisibility,
    addEventListener(type, handler) {
      if (type === "visibilitychange") listeners.add(handler);
    },
    removeEventListener(type, handler) {
      if (type === "visibilitychange") listeners.delete(handler);
    },
    dispatchVisibilityChange(nextVisibility) {
      this.visibilityState = nextVisibility;
      listeners.forEach((handler) => handler());
    },
  };
}

let captured;
function Probe() {
  captured = useTwinOps();
  return null;
}

const WEDNESDAY_1230_BRT = () => new Date("2026-08-12T15:30:00.000Z"); // quarta 12:30 BRT
const THURSDAY_1230_BRT = () => new Date("2026-08-13T15:30:00.000Z"); // quinta 12:30 BRT

beforeEach(() => {
  captured = undefined;
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("isForzyWindowOpen", () => {
  it("is open on Wednesday at 12:30 BRT (verbatim scenario date)", () => {
    expect(isForzyWindowOpen(WEDNESDAY_1230_BRT())).toBe(true);
  });

  it("is closed on Thursday at the same time of day", () => {
    expect(isForzyWindowOpen(THURSDAY_1230_BRT())).toBe(false);
  });

  it("is closed on Sunday", () => {
    // 2026-08-16T15:00:00Z = domingo 12:00 BRT
    expect(isForzyWindowOpen(new Date("2026-08-16T15:00:00.000Z"))).toBe(false);
  });

  it("includes the closed start boundary at exactly 12:00 BRT", () => {
    // 2026-08-12T15:00:00Z = quarta 12:00 BRT
    expect(isForzyWindowOpen(new Date("2026-08-12T15:00:00.000Z"))).toBe(true);
  });

  it("excludes the open end boundary at exactly 14:00 BRT", () => {
    // 2026-08-12T17:00:00Z = quarta 14:00 BRT
    expect(isForzyWindowOpen(new Date("2026-08-12T17:00:00.000Z"))).toBe(false);
  });

  it("is closed just before the window opens", () => {
    // 2026-08-12T14:59:00Z = quarta 11:59 BRT
    expect(isForzyWindowOpen(new Date("2026-08-12T14:59:00.000Z"))).toBe(false);
  });
});

describe("TwinOpsProvider polling", () => {
  it("keeps the default clock identity stable across re-renders (regression: unbounded remount loop when `clock` is omitted)", async () => {
    // With no `clock` prop, the provider falls back to its default. If that
    // default were an inline `() => new Date()` literal in the parameter
    // list (instead of a stable module-level constant), it would be
    // re-evaluated to a brand new function reference on every render. That
    // reference sits in the polling effect's dependency array, and the
    // effect's own state setters (setSnapshot/setError/setRefreshing/
    // setLastRefreshAttemptAt) cause exactly those re-renders — so the
    // effect would tear down and remount after every GET/POST resolves,
    // firing a fresh GET each time, forever. This is driven purely by
    // promise resolution (no setTimeout involved for the very first GET),
    // so a handful of bounded microtask flushes is enough to reveal it
    // without ever risking an actual hang.
    vi.useFakeTimers();
    const source = sourceStub();
    render(
      <TwinOpsProvider dataSource={source}>
        <Probe />
      </TwinOpsProvider>
    );
    for (let i = 0; i < 5; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await act(async () => {
        await Promise.resolve();
      });
    }
    expect(source.getSnapshot).toHaveBeenCalledTimes(1);
  });

  it("resumes polling once the Forzy window opens even without a visibilitychange event", async () => {
    // Mount closed, stay visible throughout, and cross the window boundary
    // purely by advancing the (faked) clock — no visibilitychange event is
    // ever dispatched. The heartbeat must notice the window opening on its
    // own instead of staying parked on the initial GET for the rest of the
    // two-hour window.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-12T14:55:00.000Z")); // quarta 11:55 BRT (fechada)
    const doc = fakeDocument("visible");
    const source = sourceStub();
    render(
      <TwinOpsProvider dataSource={source} documentRef={doc} pollMs={5000}>
        <Probe />
      </TwinOpsProvider>
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(source.refresh).not.toHaveBeenCalled();

    // Advance 6 minutes of (faked) real time, crossing 12:00 BRT, with no
    // visibilitychange dispatched anywhere in between.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6 * 60 * 1000);
    });
    expect(source.refresh.mock.calls.length).toBeGreaterThan(0);
  });

  it("refreshes only while visible and inside the Forzy window", async () => {
    vi.useFakeTimers();
    const source = sourceStub();
    const clock = WEDNESDAY_1230_BRT;
    render(
      <TwinOpsProvider dataSource={source} clock={clock}>
        <Probe />
      </TwinOpsProvider>
    );
    await vi.runOnlyPendingTimersAsync();
    expect(source.refresh).toHaveBeenCalledTimes(1);
    expect(source.getSnapshot).toHaveBeenCalledTimes(1);
    expect(captured.snapshot).toEqual(makeSnapshot("refreshed"));
  });

  it("does not call refresh outside the window, but still reads the snapshot", async () => {
    vi.useFakeTimers();
    const source = sourceStub();
    const clock = THURSDAY_1230_BRT;
    render(
      <TwinOpsProvider dataSource={source} clock={clock}>
        <Probe />
      </TwinOpsProvider>
    );
    // No POST is ever scheduled outside the window, so there is no timer for
    // runOnlyPendingTimersAsync to chase; flush the plain GET microtask chain
    // explicitly instead, inside act() so the resulting state update is
    // applied before we inspect `captured`.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(source.getSnapshot).toHaveBeenCalledTimes(1);
    expect(source.refresh).not.toHaveBeenCalled();
    expect(captured.snapshot).toEqual(makeSnapshot("initial"));

    // advancing time should not spawn any refresh either: no timer was scheduled
    await vi.advanceTimersByTimeAsync(20000);
    expect(source.refresh).not.toHaveBeenCalled();
  });

  it("aborts the in-flight refresh and clears the pending timer when the page becomes hidden", async () => {
    vi.useFakeTimers();
    const doc = fakeDocument("visible");
    let capturedSignal;
    const source = {
      getSnapshot: vi.fn(() => Promise.resolve(makeSnapshot("initial"))),
      refresh: vi.fn(
        (_assetId, { signal }) =>
          new Promise(() => {
            capturedSignal = signal;
          }) // never settles on its own
      ),
    };
    render(
      <TwinOpsProvider dataSource={source} clock={WEDNESDAY_1230_BRT} documentRef={doc}>
        <Probe />
      </TwinOpsProvider>
    );
    await vi.advanceTimersByTimeAsync(0);
    expect(source.refresh).toHaveBeenCalledTimes(1);
    expect(capturedSignal.aborted).toBe(false);

    await act(async () => {
      doc.dispatchVisibilityChange("hidden");
    });
    expect(capturedSignal.aborted).toBe(true);

    // no timer should be pending: advancing far does not call refresh again
    await vi.advanceTimersByTimeAsync(60000);
    expect(source.refresh).toHaveBeenCalledTimes(1);
  });

  it("does not overlap a slow refresh with the next scheduled cycle", async () => {
    vi.useFakeTimers();
    let resolveRefresh;
    const source = {
      getSnapshot: vi.fn(() => Promise.resolve(makeSnapshot("initial"))),
      refresh: vi.fn(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve;
          })
      ),
    };
    render(
      <TwinOpsProvider dataSource={source} clock={WEDNESDAY_1230_BRT} pollMs={5000}>
        <Probe />
      </TwinOpsProvider>
    );
    await vi.advanceTimersByTimeAsync(0);
    expect(source.refresh).toHaveBeenCalledTimes(1);

    // time passes well beyond pollMs while the first refresh is still in flight
    await vi.advanceTimersByTimeAsync(20000);
    expect(source.refresh).toHaveBeenCalledTimes(1);

    // only after the slow refresh resolves does the next cycle get scheduled
    await act(async () => {
      resolveRefresh({ refreshAttempted: true, outcomes: {}, snapshot: makeSnapshot("refreshed") });
    });
    await vi.advanceTimersByTimeAsync(5000);
    expect(source.refresh).toHaveBeenCalledTimes(2);
  });

  it("keeps the last snapshot and surfaces the error when refresh fails", async () => {
    vi.useFakeTimers();
    const boom = new Error("boom");
    const source = {
      getSnapshot: vi.fn(() => Promise.resolve(makeSnapshot("initial"))),
      refresh: vi.fn(() => Promise.reject(boom)),
    };
    render(
      <TwinOpsProvider dataSource={source} clock={WEDNESDAY_1230_BRT}>
        <Probe />
      </TwinOpsProvider>
    );
    await vi.runOnlyPendingTimersAsync();
    expect(captured.snapshot).toEqual(makeSnapshot("initial"));
    expect(captured.error).toBe(boom);
  });

  it("aborts the in-flight request on unmount", async () => {
    vi.useFakeTimers();
    let capturedSignal;
    const source = {
      getSnapshot: vi.fn(
        (_assetId, { signal }) =>
          new Promise(() => {
            capturedSignal = signal;
          })
      ),
      refresh: vi.fn(() => Promise.resolve({ refreshAttempted: true, outcomes: {}, snapshot: makeSnapshot("refreshed") })),
    };
    const { unmount } = render(
      <TwinOpsProvider dataSource={source} clock={WEDNESDAY_1230_BRT}>
        <Probe />
      </TwinOpsProvider>
    );
    await vi.advanceTimersByTimeAsync(0);
    expect(capturedSignal.aborted).toBe(false);
    unmount();
    expect(capturedSignal.aborted).toBe(true);
  });

  it("refreshNow respects the window: inside it POSTs, outside it only re-reads the snapshot", async () => {
    vi.useFakeTimers();
    const insideSource = sourceStub();
    render(
      <TwinOpsProvider dataSource={insideSource} clock={WEDNESDAY_1230_BRT}>
        <Probe />
      </TwinOpsProvider>
    );
    await vi.runOnlyPendingTimersAsync();
    insideSource.refresh.mockClear();
    insideSource.getSnapshot.mockClear();

    await act(async () => {
      await captured.refreshNow();
    });
    expect(insideSource.refresh).toHaveBeenCalledTimes(1);

    cleanup();

    const outsideSource = sourceStub();
    render(
      <TwinOpsProvider dataSource={outsideSource} clock={THURSDAY_1230_BRT}>
        <Probe />
      </TwinOpsProvider>
    );
    await vi.runOnlyPendingTimersAsync();
    outsideSource.refresh.mockClear();
    outsideSource.getSnapshot.mockClear();

    await act(async () => {
      await captured.refreshNow();
    });
    expect(outsideSource.refresh).not.toHaveBeenCalled();
    expect(outsideSource.getSnapshot).toHaveBeenCalledTimes(1);
  });
});
