import React from "react";
import { act, cleanup, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import overviewFixture from "../contracts/timeline/v1/fixtures/overview-unified.valid.json";
import pageFixture from "../contracts/timeline/v1/fixtures/page.valid.json";
import historicalContextFixture from "../contracts/timeline/v1/fixtures/context-historical-candidate.valid.json";
import missingChannelContextFixture from "../contracts/timeline/v1/fixtures/context-missing-channel.valid.json";
import assessmentOverviewFixture from "../contracts/timeline/v1/fixtures/assessment-overview-materialized.valid.json";
import { TwinOpsProvider, isForzyWindowOpen, useTwinOps } from "./TwinOpsContext.jsx";

const snapshot = {
  schemaVersion: "2.0",
  asset: {
    assetId: "forzy-motor-01",
    displayName: "Conjunto motor-bomba monitorado",
    officialTag: null,
  },
};
const overview = structuredClone(overviewFixture);
const timelinePage = structuredClone(pageFixture);
const historicalContext = structuredClone(historicalContextFixture);
const missingChannelContext = structuredClone(missingChannelContextFixture);
const assessmentOverview = structuredClone(assessmentOverviewFixture);

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
  getTimelineOverview: vi.fn().mockResolvedValue(overview),
  getTimelineSamples: vi.fn().mockResolvedValue(timelinePage),
  getTimelineAssessments: vi.fn().mockResolvedValue(assessmentOverview),
  getTimelineContext: vi.fn().mockResolvedValue(historicalContext),
});

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

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

it("makes a manual GET visibly pending outside the window", async () => {
  const source = sourceStub();
  const pendingSnapshot = deferred();
  source.getSnapshot
    .mockResolvedValueOnce(snapshot)
    .mockImplementationOnce(() => pendingSnapshot.promise);
  const doc = visibleDocument();
  const { result } = renderHook(() => useTwinOps(), {
    wrapper: wrapperFor({
      dataSource: source,
      clock: () => new Date("2026-08-13T15:30:00.000Z"),
      documentRef: doc.target,
    }),
  });
  await flush();

  let requestPromise;
  act(() => {
    requestPromise = result.current.refreshNow();
  });

  expect(source.getSnapshot).toHaveBeenCalledTimes(2);
  expect(source.refresh).not.toHaveBeenCalled();
  expect(result.current.refreshing).toBe(true);
  expect(result.current.lastRefreshAttemptAt).toBe("2026-08-13T15:30:00.000Z");

  await act(async () => {
    pendingSnapshot.resolve(snapshot);
    await requestPromise;
  });

  expect(result.current.refreshing).toBe(false);
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

describe("historical navigation", () => {
  const outsideWindowClock = () => new Date("2026-08-13T15:30:00.000Z");

  it("starts overview and first original page in parallel without refresh", async () => {
    const source = sourceStub();
    const overviewRequest = deferred();
    const pageRequest = deferred();
    source.getTimelineOverview.mockReturnValue(overviewRequest.promise);
    source.getTimelineSamples.mockReturnValue(pageRequest.promise);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    let historyPromise;
    act(() => {
      historyPromise = result.current.showHistory();
    });
    await flush();

    expect(source.getTimelineOverview).toHaveBeenCalledTimes(1);
    expect(source.getTimelineSamples).toHaveBeenCalledTimes(1);
    expect(source.refresh).not.toHaveBeenCalled();
    expect(result.current.viewMode).toBe("historical");
    expect(result.current.timelineLoading).toEqual({
      overview: true,
      page: true,
      assessments: false,
      context: false,
    });

    await act(async () => {
      overviewRequest.resolve(overview);
      pageRequest.resolve(timelinePage);
      await historyPromise;
    });

    expect(result.current.timelineOverview).toBe(overview);
    expect(result.current.timelinePage).toBe(timelinePage);
    expect(result.current.timelineLoading).toEqual({
      overview: false,
      page: false,
      assessments: false,
      context: false,
    });
    expect(Object.keys(source.getTimelineOverview.mock.calls[0][1]).sort()).toEqual([
      "maxPoints",
      "metric",
      "sensorId",
      "signal",
    ]);
    expect(Object.keys(source.getTimelineSamples.mock.calls[0][1]).sort()).toEqual([
      "limit",
      "metric",
      "sensorId",
      "signal",
    ]);
  });

  it("reuses a loaded historical range without another network roundtrip", async () => {
    const source = sourceStub();
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.showHistory();
    });
    await act(async () => {
      await result.current.selectTimelineRange("historical");
    });

    expect(source.getTimelineOverview).toHaveBeenCalledTimes(2);
    expect(source.getTimelineSamples).toHaveBeenCalledTimes(2);
    expect(source.getTimelineAssessments).toHaveBeenCalledTimes(2);

    await act(async () => {
      await result.current.selectTimelineRange("all");
      await result.current.selectTimelineRange("historical");
    });

    expect(result.current.timelineRangePreset).toBe("historical");
    expect(source.getTimelineOverview).toHaveBeenCalledTimes(2);
    expect(source.getTimelineSamples).toHaveBeenCalledTimes(2);
    expect(source.getTimelineAssessments).toHaveBeenCalledTimes(2);
  });

  it("queries the dense immutable archive when Lote histórico is selected", async () => {
    const source = sourceStub();
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.showHistory();
    });
    await act(async () => {
      await result.current.selectTimelineRange("historical");
    });

    expect(result.current.timelineRangePreset).toBe("historical");
    for (const request of [
      source.getTimelineOverview.mock.calls[1][1],
      source.getTimelineSamples.mock.calls[1][1],
      source.getTimelineAssessments.mock.calls[1][1],
    ]) {
      expect(request).toMatchObject({
        from: "2026-08-22T12:00:00.000Z",
        to: "2026-08-22T12:03:09.001Z",
      });
    }
  });

  it("keeps the current display until a selected point validates and commits", async () => {
    const source = sourceStub();
    const contextRequest = deferred();
    source.getTimelineContext.mockReturnValue(contextRequest.promise);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    let selectionPromise;
    act(() => {
      selectionPromise = result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });
    await flush();

    expect(result.current.pendingSelection).toEqual({
      pointId: historicalContext.anchor.pointId,
    });
    expect(result.current.historicalContext).toBeNull();
    expect(result.current.displayContext).toBe(snapshot);
    expect(result.current.timelineLoading.context).toBe(true);
    expect(source.refresh).not.toHaveBeenCalled();
    expect(Object.keys(source.getTimelineContext.mock.calls[0][1]).sort()).toEqual([
      "pointId",
      "signal",
    ]);

    await act(async () => {
      contextRequest.resolve(historicalContext);
      await selectionPromise;
    });

    expect(result.current.viewMode).toBe("historical");
    expect(result.current.historicalContext).toBe(historicalContext);
    expect(result.current.displayContext).toBe(historicalContext);
    expect(result.current.pendingSelection).toBeNull();
    expect(result.current.timelineLoading.context).toBe(false);
  });

  it("lets only the latest validated selection token commit", async () => {
    const source = sourceStub();
    const first = deferred();
    const second = deferred();
    const signals = [];
    source.getTimelineContext
      .mockImplementationOnce((_, { signal }) => {
        signals.push(signal);
        return first.promise;
      })
      .mockImplementationOnce((_, { signal }) => {
        signals.push(signal);
        return second.promise;
      });
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    let firstPromise;
    act(() => {
      firstPromise = result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });
    await flush();
    let secondPromise;
    act(() => {
      secondPromise = result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });
    await flush();

    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);

    await act(async () => {
      second.resolve(missingChannelContext);
      await secondPromise;
    });
    expect(result.current.historicalContext).toBe(missingChannelContext);

    await act(async () => {
      first.resolve(historicalContext);
      await firstPromise;
    });
    expect(result.current.historicalContext).toBe(missingChannelContext);
  });

  it("preserves the committed context and exposes a retryable selection error", async () => {
    const source = sourceStub();
    const failure = new Error("timeline context unavailable");
    source.getTimelineContext
      .mockResolvedValueOnce(historicalContext)
      .mockRejectedValueOnce(failure);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });
    const committed = result.current.displayContext;

    await act(async () => {
      await result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });

    expect(result.current.displayContext).toBe(committed);
    expect(result.current.historicalContext).toBe(committed);
    expect(result.current.timelineErrors.context).toBe(failure);
    expect(result.current.timelineLoading.context).toBe(false);
  });

  it("keeps overview and page outcomes independent", async () => {
    const source = sourceStub();
    const overviewFailure = new Error("overview unavailable");
    source.getTimelineOverview.mockRejectedValue(overviewFailure);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.showHistory();
    });

    expect(result.current.timelineOverview).toBeNull();
    expect(result.current.timelinePage).toBe(timelinePage);
    expect(result.current.timelineErrors).toEqual({
      overview: overviewFailure,
      page: null,
      assessments: null,
      context: null,
    });
    expect(result.current.displayContext).toBe(snapshot);
  });

  it("surfaces an active overview AbortError as retryable failure", async () => {
    const source = sourceStub();
    const abortFailure = new DOMException("upstream mislabeled failure", "AbortError");
    source.getTimelineOverview.mockRejectedValue(abortFailure);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.showHistory();
    });

    expect(result.current.timelineErrors.overview).toBe(abortFailure);
    expect(result.current.timelineLoading.overview).toBe(false);
    expect(result.current.displayContext).toBe(snapshot);
  });

  it("surfaces an active page AbortError as retryable failure", async () => {
    const source = sourceStub();
    const abortFailure = new DOMException("upstream mislabeled failure", "AbortError");
    source.getTimelineSamples.mockRejectedValue(abortFailure);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.showHistory();
    });

    expect(result.current.timelineErrors.page).toBe(abortFailure);
    expect(result.current.timelineLoading.page).toBe(false);
    expect(result.current.timelineOverview).toBe(overview);
    expect(result.current.displayContext).toBe(snapshot);
  });

  it("surfaces an active context AbortError without replacing the committed context", async () => {
    const source = sourceStub();
    const abortFailure = new DOMException("upstream mislabeled failure", "AbortError");
    source.getTimelineContext
      .mockResolvedValueOnce(historicalContext)
      .mockRejectedValueOnce(abortFailure);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });
    const committed = result.current.historicalContext;

    await act(async () => {
      await result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });

    expect(result.current.timelineErrors.context).toBe(abortFailure);
    expect(result.current.timelineLoading.context).toBe(false);
    expect(result.current.pendingSelection).toBeNull();
    expect(result.current.historicalContext).toBe(committed);
    expect(result.current.displayContext).toBe(committed);
  });

  it("surfaces an active non-abort page error independently", async () => {
    const source = sourceStub();
    const pageFailure = new Error("samples unavailable");
    source.getTimelineSamples.mockRejectedValue(pageFailure);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.showHistory();
    });

    expect(result.current.timelineErrors.page).toBe(pageFailure);
    expect(result.current.timelineLoading.page).toBe(false);
    expect(result.current.timelineOverview).toBe(overview);
  });

  it.each([
    ["overview", "getTimelineOverview", "timelineOverview", overview],
    ["page", "getTimelineSamples", "timelinePage", timelinePage],
  ])("ignores any failure from an obsolete %s owner", async (
    errorKey,
    method,
    valueKey,
    expectedValue,
  ) => {
    const source = sourceStub();
    const obsolete = deferred();
    let obsoleteSignal;
    source[method].mockImplementationOnce((_, { signal }) => {
      obsoleteSignal = signal;
      return obsolete.promise;
    });
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    let obsoleteHistoryPromise;
    act(() => {
      obsoleteHistoryPromise = result.current.showHistory();
    });
    await flush();
    await act(async () => {
      await result.current.showHistory();
    });

    expect(obsoleteSignal.aborted).toBe(true);
    const committedValue = result.current[valueKey];

    await act(async () => {
      obsolete.reject(new Error("obsolete transport failure"));
      await obsoleteHistoryPromise;
    });

    expect(result.current.timelineErrors[errorKey]).toBeNull();
    expect(result.current[valueKey]).toBe(committedValue);
    expect(result.current[valueKey]).toBe(expectedValue);
  });

  it("ignores any failure from an obsolete context owner", async () => {
    const source = sourceStub();
    const obsolete = deferred();
    let obsoleteSignal;
    source.getTimelineContext
      .mockImplementationOnce((_, { signal }) => {
        obsoleteSignal = signal;
        return obsolete.promise;
      })
      .mockResolvedValueOnce(historicalContext);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    let obsoleteSelectionPromise;
    act(() => {
      obsoleteSelectionPromise = result.current.selectTimelinePoint(
        historicalContext.anchor.pointId
      );
    });
    await flush();
    await act(async () => {
      await result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });

    expect(obsoleteSignal.aborted).toBe(true);
    const committed = result.current.historicalContext;

    await act(async () => {
      obsolete.reject(new Error("obsolete context failure"));
      await obsoleteSelectionPromise;
    });

    expect(result.current.timelineErrors.context).toBeNull();
    expect(result.current.pendingSelection).toBeNull();
    expect(result.current.historicalContext).toBe(committed);
    expect(result.current.displayContext).toBe(committed);
  });

  it("ignores aborted overview and page AbortErrors after showNow", async () => {
    const source = sourceStub();
    const signals = [];
    const rejectWhenAborted = (_, { signal }) => {
      signals.push(signal);
      return new Promise((_, reject) => {
        signal.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      });
    };
    source.getTimelineOverview.mockImplementation(rejectWhenAborted);
    source.getTimelineSamples.mockImplementation(rejectWhenAborted);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    let historyPromise;
    act(() => {
      historyPromise = result.current.showHistory();
    });
    await flush();
    act(() => result.current.showNow());
    await act(async () => {
      await historyPromise;
    });

    expect(signals).toHaveLength(2);
    expect(signals.every((signal) => signal.aborted)).toBe(true);
    expect(result.current.timelineErrors).toEqual({
      overview: null,
      page: null,
      assessments: null,
      context: null,
    });
    expect(result.current.timelineLoading).toEqual({
      overview: false,
      page: false,
      assessments: false,
      context: false,
    });
    expect(result.current.viewMode).toBe("now");
  });

  it("rejects an invalid context response without replacing the prior commit", async () => {
    const source = sourceStub();
    const invalidContext = {
      ...historicalContext,
      selectedAt: "2026-08-22T12:00:00Z",
    };
    source.getTimelineContext
      .mockResolvedValueOnce(historicalContext)
      .mockResolvedValueOnce(invalidContext);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });
    const committed = result.current.historicalContext;

    await act(async () => {
      await result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });

    expect(result.current.historicalContext).toBe(committed);
    expect(result.current.displayContext).toBe(committed);
    expect(result.current.timelineErrors.context).toBeInstanceOf(TypeError);
  });

  it("showNow aborts a pending selection and ignores its late response", async () => {
    const source = sourceStub();
    const pending = deferred();
    let pendingSignal;
    source.getTimelineContext
      .mockResolvedValueOnce(historicalContext)
      .mockImplementationOnce((_, { signal }) => {
        pendingSignal = signal;
        return pending.promise;
      });
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });
    let pendingPromise;
    act(() => {
      pendingPromise = result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });
    await flush();

    act(() => result.current.showNow());

    expect(pendingSignal.aborted).toBe(true);
    expect(result.current.viewMode).toBe("now");
    expect(result.current.displayContext).toBe(snapshot);
    expect(result.current.timelineLoading.context).toBe(false);

    await act(async () => {
      pending.reject(new DOMException("aborted", "AbortError"));
      await pendingPromise;
    });

    expect(result.current.viewMode).toBe("now");
    expect(result.current.historicalContext).toBe(historicalContext);
    expect(result.current.displayContext).toBe(snapshot);
    expect(result.current.timelineErrors.context).toBeNull();
  });

  it("updates stored now independently and reveals it only on showNow", async () => {
    const newerSnapshot = Object.freeze({ ...snapshot, marker: "newer-now" });
    const source = sourceStub();
    source.getSnapshot
      .mockResolvedValueOnce(snapshot)
      .mockResolvedValueOnce(newerSnapshot);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    await act(async () => {
      await result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });
    expect(result.current.displayContext).toBe(historicalContext);

    await act(async () => {
      await result.current.refreshNow();
    });

    expect(result.current.snapshot).toBe(newerSnapshot);
    expect(result.current.viewMode).toBe("historical");
    expect(result.current.displayContext).toBe(historicalContext);
    expect(result.current.historicalContext).toBe(historicalContext);

    act(() => result.current.showNow());

    expect(result.current.viewMode).toBe("now");
    expect(result.current.displayContext).toBe(newerSnapshot);
    expect(result.current.historicalContext).toBe(historicalContext);
  });

  it("aborts every active timeline request on unmount", async () => {
    const source = sourceStub();
    const signals = [];
    const untilAbort = (_, { signal }) => {
      signals.push(signal);
      return new Promise((_, reject) => {
        signal.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      });
    };
    source.getTimelineOverview.mockImplementation(untilAbort);
    source.getTimelineSamples.mockImplementation(untilAbort);
    source.getTimelineAssessments.mockImplementation((_, __, { signal }) => (
      untilAbort(null, { signal })
    ));
    source.getTimelineContext.mockImplementation(untilAbort);
    const doc = visibleDocument();
    const { result, unmount } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({
        dataSource: source,
        clock: outsideWindowClock,
        documentRef: doc.target,
      }),
    });
    await flush();

    act(() => {
      void result.current.showHistory();
      void result.current.selectTimelinePoint(historicalContext.anchor.pointId);
    });
    await flush();
    expect(signals).toHaveLength(3);

    unmount();
    await flush();

    expect(signals.every((signal) => signal.aborted)).toBe(true);
  });
});

describe("historical assessment overview ownership", () => {
  const outsideWindowClock = () => new Date("2026-08-13T15:30:00.000Z");

  it("starts assessment evidence after overview and samples release the backend", async () => {
    const source = sourceStub();
    const overviewRequest = deferred();
    const pageRequest = deferred();
    const assessmentsRequest = deferred();
    source.getTimelineOverview.mockReturnValue(overviewRequest.promise);
    source.getTimelineSamples.mockReturnValue(pageRequest.promise);
    source.getTimelineAssessments.mockReturnValue(assessmentsRequest.promise);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({ dataSource: source, clock: outsideWindowClock, documentRef: doc.target }),
    });
    await flush();

    let historyPromise;
    act(() => { historyPromise = result.current.showHistory(); });
    await flush();

    expect(source.getTimelineOverview).toHaveBeenCalledTimes(1);
    expect(source.getTimelineSamples).toHaveBeenCalledTimes(1);
    expect(source.getTimelineAssessments).not.toHaveBeenCalled();
    expect(result.current.timelineLoading).toMatchObject({
      overview: true,
      page: true,
      assessments: false,
      context: false,
    });

    await act(async () => {
      overviewRequest.resolve(overview);
      pageRequest.resolve(timelinePage);
      await Promise.all([overviewRequest.promise, pageRequest.promise]);
    });
    await flush();

    expect(source.getTimelineAssessments).toHaveBeenCalledTimes(1);
    expect(result.current.timelineLoading.assessments).toBe(true);
    const assessmentCall = source.getTimelineAssessments.mock.calls[0];
    expect(assessmentCall[0]).toBe("forzy-motor-01");
    expect(assessmentCall[1]).toEqual({ sensorId: "all", maxPoints: 800 });
    expect(assessmentCall[2].signal).toBeInstanceOf(AbortSignal);

    await act(async () => {
      assessmentsRequest.resolve(assessmentOverview);
      await historyPromise;
    });

    expect(result.current.timelineAssessmentOverview).toBe(assessmentOverview);
    expect(result.current.viewMode).toBe("historical");
    expect(result.current.displayContext).toBe(snapshot);
  });

  it("preserves the last valid assessment evidence after an active failure", async () => {
    const source = sourceStub();
    const failure = new Error("assessment evidence unavailable");
    source.getTimelineAssessments
      .mockResolvedValueOnce(assessmentOverview)
      .mockRejectedValueOnce(failure);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({ dataSource: source, clock: outsideWindowClock, documentRef: doc.target }),
    });
    await flush();

    await act(async () => { await result.current.showHistory(); });
    const committed = result.current.timelineAssessmentOverview;
    act(() => result.current.showNow());
    await act(async () => { await result.current.showHistory(); });

    expect(result.current.timelineAssessmentOverview).toBe(committed);
    expect(result.current.timelineErrors.assessments).toBe(failure);
    expect(result.current.snapshot).toBe(snapshot);
    expect(result.current.displayContext).toBe(snapshot);
  });

  it("lets only the latest validated assessment request commit", async () => {
    const source = sourceStub();
    const obsolete = deferred();
    let obsoleteSignal;
    source.getTimelineAssessments
      .mockImplementationOnce((_, __, { signal }) => {
        obsoleteSignal = signal;
        return obsolete.promise;
      })
      .mockResolvedValueOnce(assessmentOverview);
    const doc = visibleDocument();
    const { result } = renderHook(() => useTwinOps(), {
      wrapper: wrapperFor({ dataSource: source, clock: outsideWindowClock, documentRef: doc.target }),
    });
    await flush();

    let obsoleteHistory;
    act(() => { obsoleteHistory = result.current.showHistory(); });
    await flush();
    await act(async () => { await result.current.showHistory(); });
    expect(obsoleteSignal.aborted).toBe(true);

    const committed = result.current.timelineAssessmentOverview;
    await act(async () => {
      obsolete.resolve({ ...assessmentOverview, schemaVersion: "2.0" });
      await obsoleteHistory;
    });
    expect(result.current.timelineAssessmentOverview).toBe(committed);
    expect(result.current.timelineErrors.assessments).toBeNull();
  });
});
