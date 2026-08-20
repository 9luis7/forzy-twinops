import React from "react";
import { act, cleanup, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TwinOpsProvider, isForzyWindowOpen, useTwinOps } from "./TwinOpsContext.jsx";

const snapshot = {
  schemaVersion: "2.0",
  asset: {
    assetId: "forzy-motor-01",
    displayName: "Conjunto motor-bomba monitorado",
    officialTag: null,
  },
};

const flush = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
};

const visibleDocument = () => {
  const target = new EventTarget();
  let visibilityState = "visible";
  Object.defineProperty(target, "visibilityState", { get: () => visibilityState });
  return {
    target,
    setVisibility(value) {
      visibilityState = value;
      target.dispatchEvent(new Event("visibilitychange"));
    },
  };
};

const sourceStub = () => ({
  getSnapshot: vi.fn().mockResolvedValue(snapshot),
  refresh: vi.fn().mockResolvedValue({ refreshAttempted: true, snapshot }),
});

const wrapperFor = (props) =>
  function Wrapper({ children }) {
    return <TwinOpsProvider {...props}>{children}</TwinOpsProvider>;
  };

function TwinOpsStateProbe() {
  const { refreshing, snapshot: currentSnapshot } = useTwinOps();
  return (
    <output
      data-testid="twin-ops-state"
      data-refreshing={String(refreshing)}
    >
      {currentSnapshot?.marker ?? "none"}
    </output>
  );
}

function TwinOpsHarness({ dataSource, clock, documentRef, pollMs = 5000 }) {
  return (
    <TwinOpsProvider
      dataSource={dataSource}
      clock={clock}
      documentRef={documentRef}
      pollMs={pollMs}
    >
      <TwinOpsStateProbe />
    </TwinOpsProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("Forzy refresh window", () => {
  it.each([
    ["2026-08-10T15:00:00.000Z", true],
    ["2026-08-11T16:59:59.000Z", true],
    ["2026-08-12T15:30:00.000Z", true],
    ["2026-08-12T14:59:59.000Z", false],
    ["2026-08-12T17:00:00.000Z", false],
    ["2026-08-13T15:30:00.000Z", false],
  ])("evaluates %s in America/Sao_Paulo", (iso, expected) => {
    expect(isForzyWindowOpen(new Date(iso))).toBe(expected);
  });
});

it("refreshes only while visible and inside the Forzy window", async () => {
  vi.useFakeTimers();
  const source = sourceStub();
  const doc = visibleDocument();
  const clock = () => new Date("2026-08-12T15:30:00.000Z");

  renderHook(() => useTwinOps(), {
    wrapper: wrapperFor({ dataSource: source, clock, documentRef: doc.target }),
  });
  await flush();

  expect(source.getSnapshot).toHaveBeenCalledTimes(1);
  expect(source.refresh).toHaveBeenCalledTimes(1);
});

it("uses GET only on Thursday", async () => {
  vi.useFakeTimers();
  const source = sourceStub();
  const doc = visibleDocument();

  renderHook(() => useTwinOps(), {
    wrapper: wrapperFor({
      dataSource: source,
      clock: () => new Date("2026-08-13T15:30:00.000Z"),
      documentRef: doc.target,
    }),
  });
  await flush();
  await act(async () => vi.advanceTimersByTimeAsync(20_000));

  expect(source.getSnapshot).toHaveBeenCalledTimes(1);
  expect(source.refresh).not.toHaveBeenCalled();
});

it("aborts an in-flight refresh and clears polling when hidden", async () => {
  vi.useFakeTimers();
  const doc = visibleDocument();
  let refreshSignal;
  const source = {
    getSnapshot: vi.fn().mockResolvedValue(snapshot),
    refresh: vi.fn((_, { signal }) => {
      refreshSignal = signal;
      return new Promise((_, reject) => {
        signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    }),
  };
  renderHook(() => useTwinOps(), {
    wrapper: wrapperFor({
      dataSource: source,
      clock: () => new Date("2026-08-12T15:30:00.000Z"),
      documentRef: doc.target,
    }),
  });
  await flush();

  act(() => doc.setVisibility("hidden"));
  await flush();
  await act(async () => vi.advanceTimersByTimeAsync(20_000));

  expect(refreshSignal.aborted).toBe(true);
  expect(source.refresh).toHaveBeenCalledTimes(1);
});

it("never overlaps a slow refresh", async () => {
  vi.useFakeTimers();
  const doc = visibleDocument();
  let resolveRefresh;
  const source = {
    getSnapshot: vi.fn().mockResolvedValue(snapshot),
    refresh: vi.fn(() => new Promise((resolve) => {
      resolveRefresh = () => resolve({ refreshAttempted: true, snapshot });
    })),
  };
  renderHook(() => useTwinOps(), {
    wrapper: wrapperFor({
      dataSource: source,
      clock: () => new Date("2026-08-12T15:30:00.000Z"),
      documentRef: doc.target,
      pollMs: 5000,
    }),
  });
  await flush();

  await act(async () => vi.advanceTimersByTimeAsync(20_000));
  expect(source.refresh).toHaveBeenCalledTimes(1);

  await act(async () => {
    resolveRefresh();
    await Promise.resolve();
  });
  await act(async () => vi.advanceTimersByTimeAsync(4_999));
  expect(source.refresh).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTimeAsync(1));
  expect(source.refresh).toHaveBeenCalledTimes(2);
});

it("keeps refresh and timer ownership when dependencies change during a late refresh", async () => {
  vi.useFakeTimers();
  const doc = visibleDocument();
  const clock = () => new Date("2026-08-12T15:30:00.000Z");
  const markedSnapshot = (marker) => ({ ...snapshot, marker });
  let oldRefreshSignal;
  let resolveOldRefresh;
  const oldSource = {
    getSnapshot: vi.fn().mockResolvedValue(markedSnapshot("old-bootstrap")),
    refresh: vi.fn((_, { signal }) => {
      oldRefreshSignal = signal;
      return new Promise((resolve) => {
        resolveOldRefresh = () => resolve({
          refreshAttempted: true,
          snapshot: markedSnapshot("old-late"),
        });
      });
    }),
  };

  let resolveNewSnapshot;
  let resolveNewRefresh;
  const newSource = {
    getSnapshot: vi.fn(() => new Promise((resolve) => {
      resolveNewSnapshot = () => resolve(markedSnapshot("new-bootstrap"));
    })),
    refresh: vi.fn()
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveNewRefresh = () => resolve({
          refreshAttempted: true,
          snapshot: markedSnapshot("new-refreshed"),
        });
      }))
      .mockResolvedValue({
        refreshAttempted: true,
        snapshot: markedSnapshot("new-polled"),
      }),
  };

  const { rerender } = render(
    <TwinOpsHarness
      dataSource={oldSource}
      clock={clock}
      documentRef={doc.target}
    />
  );
  await flush();
  expect(oldSource.refresh).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId("twin-ops-state").dataset.refreshing).toBe("true");

  rerender(
    <TwinOpsHarness
      dataSource={newSource}
      clock={clock}
      documentRef={doc.target}
    />
  );
  await flush();

  expect(oldRefreshSignal.aborted).toBe(true);
  expect(newSource.getSnapshot).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId("twin-ops-state").dataset.refreshing).toBe("false");

  await act(async () => {
    resolveNewSnapshot();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(newSource.refresh).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId("twin-ops-state").dataset.refreshing).toBe("true");

  await act(async () => vi.advanceTimersByTimeAsync(20_000));
  expect(newSource.refresh).toHaveBeenCalledTimes(1);

  await act(async () => {
    resolveNewRefresh();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(screen.getByTestId("twin-ops-state").textContent).toBe("new-refreshed");
  expect(screen.getByTestId("twin-ops-state").dataset.refreshing).toBe("false");

  await act(async () => {
    resolveOldRefresh();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(screen.getByTestId("twin-ops-state").textContent).toBe("new-refreshed");
  expect(screen.getByTestId("twin-ops-state").dataset.refreshing).toBe("false");

  await act(async () => vi.advanceTimersByTimeAsync(4_999));
  expect(newSource.refresh).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTimeAsync(1));
  expect(newSource.refresh).toHaveBeenCalledTimes(2);
  expect(screen.getByTestId("twin-ops-state").textContent).toBe("new-polled");
});

it("keeps the last real snapshot when refresh fails", async () => {
  vi.useFakeTimers();
  const failure = new Error("gateway unavailable");
  const source = {
    getSnapshot: vi.fn().mockResolvedValue(snapshot),
    refresh: vi.fn().mockRejectedValue(failure),
  };
  const doc = visibleDocument();
  const { result } = renderHook(() => useTwinOps(), {
    wrapper: wrapperFor({
      dataSource: source,
      clock: () => new Date("2026-08-12T15:30:00.000Z"),
      documentRef: doc.target,
    }),
  });
  await flush();

  expect(result.current.snapshot).toBe(snapshot);
  expect(result.current.error).toBe(failure);
  expect(result.current.refreshing).toBe(false);
});

it("uses GET for manual refresh outside the window", async () => {
  const source = sourceStub();
  const doc = visibleDocument();
  const { result } = renderHook(() => useTwinOps(), {
    wrapper: wrapperFor({
      dataSource: source,
      clock: () => new Date("2026-08-13T15:30:00.000Z"),
      documentRef: doc.target,
    }),
  });
  await flush();

  await act(async () => result.current.refreshNow());

  expect(source.getSnapshot).toHaveBeenCalledTimes(2);
  expect(source.refresh).not.toHaveBeenCalled();
  expect(result.current.lastRefreshAttemptAt).toBeNull();
});

it("aborts the active request on unmount", async () => {
  let requestSignal;
  const source = {
    getSnapshot: vi.fn((_, { signal }) => {
      requestSignal = signal;
      return new Promise(() => {});
    }),
    refresh: vi.fn(),
  };
  const doc = visibleDocument();
  const { unmount } = renderHook(() => useTwinOps(), {
    wrapper: wrapperFor({ dataSource: source, documentRef: doc.target }),
  });
  await flush();

  unmount();

  expect(requestSignal.aborted).toBe(true);
});
