import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import receivedSnapshot from "../contracts/v2/fixtures/snapshot-received-now.valid.json";
import lastKnownSnapshot from "../contracts/v2/fixtures/snapshot-last-known.valid.json";
import overviewFixture from "../contracts/timeline/v1/fixtures/overview-unified.valid.json";
import pageFixture from "../contracts/timeline/v1/fixtures/page.valid.json";
import assessmentOverviewFixture from "../contracts/timeline/v1/fixtures/assessment-overview-materialized.valid.json";
import historicalContextFixture from "../contracts/timeline/v1/fixtures/context-historical-candidate.valid.json";
import missingChannelContextFixture from "../contracts/timeline/v1/fixtures/context-missing-channel.valid.json";
import App from "./App.jsx";

vi.mock("./components/twin3d/Twin3DCanvas.jsx", () => ({
  default: ({ snapshot }) => `canvas-3d-real:${snapshot.asset.assetId}`,
}));

const flush = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
};

const sourceWithSnapshot = (snapshot = structuredClone(receivedSnapshot)) => ({
  getSnapshot: vi.fn().mockResolvedValue(snapshot),
  refresh: vi.fn().mockResolvedValue({ refreshAttempted: true, snapshot }),
});

const activeHistoricalBatchId = historicalContextFixture.provenance.activeHistoricalBatchId;

const overviewForTimeline = () => {
  const value = structuredClone(overviewFixture);
  value.activeHistoricalBatchId = activeHistoricalBatchId;
  value.aggregationSummary = {
    ...value.aggregationSummary,
    requestedMaxPoints: 1200,
    returnedPointCount: value.aggregationSummary.originalPointCount,
    omittedPointCount: 0,
    reducedSeriesCount: 0,
  };
  value.series.forEach((series, seriesIndex) => {
    const segment = value.segments.find(({ segmentId }) => segmentId === series.segmentId);
    series.points = Array.from({ length: series.aggregation.originalPointCount }, (_, pointIndex) => ({
      pointId: `00000000-0000-5000-8000-${String(300 + (seriesIndex * 20) + pointIndex).padStart(12, "0")}`,
      eventAt: new Date(Date.parse(segment.startAt) + (pointIndex * 900)).toISOString(),
      value: 30 + seriesIndex + (pointIndex / 10),
    }));
    series.aggregation = {
      ...series.aggregation,
      method: "none",
      requestedMaxPoints: 1200,
      returnedPointCount: series.aggregation.originalPointCount,
      omittedPointCount: 0,
    };
  });
  return value;
};

const pageWithOriginalPoints = () => ({
  ...structuredClone(pageFixture),
  activeHistoricalBatchId,
  items: [
    structuredClone(historicalContextFixture.channels.s1),
    structuredClone(historicalContextFixture.channels.s2),
  ],
  limit: 200,
});

const assessmentOverviewForTimeline = () => ({
  ...structuredClone(assessmentOverviewFixture),
  activeHistoricalBatchId,
  aggregationSummary: {
    ...assessmentOverviewFixture.aggregationSummary,
    requestedMaxPoints: 800,
  },
  series: assessmentOverviewFixture.series.map((series) => ({
    ...structuredClone(series),
    aggregation: { ...series.aggregation, requestedMaxPoints: 800 },
  })),
});

const sourceWithTimeline = () => ({
  ...sourceWithSnapshot(),
  getTimelineOverview: vi.fn().mockResolvedValue(overviewForTimeline()),
  getTimelineSamples: vi.fn().mockResolvedValue(pageWithOriginalPoints()),
  getTimelineAssessments: vi.fn().mockResolvedValue(assessmentOverviewForTimeline()),
  getTimelineContext: vi.fn().mockResolvedValue(structuredClone(historicalContextFixture)),
});

const originalPointActions = () => within(screen.getByRole("table", {
  name: "Pontos originais disponíveis para inspeção histórica",
})).getAllByRole("button", { name: /inspecionar ponto/i });

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
};

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
});

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-08-13T15:30:00.000Z"));
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
afterAll(() => vi.unstubAllGlobals());

it("renders one real asset and no fictional navigation", async () => {
  render(<App dataSource={sourceWithSnapshot()} />);
  await flush();

  expect(screen.getByText("Conjunto motor-bomba monitorado")).toBeInTheDocument();
  for (const label of ["Planta", "Ordens", "Documentos", "MTR-BMB-042", "Copiloto"]) {
    expect(screen.queryByText(label)).not.toBeInTheDocument();
  }
});

it("shows an honest loading state before the first real snapshot", () => {
  const source = {
    getSnapshot: vi.fn(() => new Promise(() => {})),
    refresh: vi.fn(),
  };

  render(<App dataSource={source} />);

  const loading = screen.getByRole("status", {
    name: "Carregando o último snapshot real…",
  });
  expect(loading).toHaveAttribute("aria-live", "polite");
  expect(loading).toHaveTextContent(
    /Conectando ao snapshot operacional|Validando telemetria S1 e S2|Preparando o painel operacional|Sincronizando o gêmeo digital/,
  );
});

it("starts a fresh bootstrap after StrictMode aborts the first setup outside the window", async () => {
  const source = {
    getSnapshot: vi.fn((_, { signal }) => {
      if (source.getSnapshot.mock.calls.length === 1) {
        return new Promise((_, reject) => {
          signal.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          });
        });
      }
      return Promise.resolve(structuredClone(receivedSnapshot));
    }),
    refresh: vi.fn(),
  };

  render(
    <React.StrictMode>
      <App dataSource={source} />
    </React.StrictMode>
  );
  await flush();

  expect(source.getSnapshot).toHaveBeenCalledTimes(2);
  expect(screen.getByText("Conjunto motor-bomba monitorado")).toBeInTheDocument();
  expect(screen.queryByText("Carregando o último snapshot real…")).not.toBeInTheDocument();
  expect(source.refresh).not.toHaveBeenCalled();
});

it("shows backend unavailability without creating a normal snapshot", async () => {
  const source = {
    getSnapshot: vi.fn().mockRejectedValue(new Error("database unavailable")),
    refresh: vi.fn(),
  };

  render(<App dataSource={source} />);
  await flush();

  expect(screen.getByText("Dados reais indisponíveis")).toBeInTheDocument();
  expect(screen.queryByText("Conjunto motor-bomba monitorado")).not.toBeInTheDocument();
});

it("presents Agora in the compact decision console and keeps 3D optional", async () => {
  render(<App dataSource={sourceWithSnapshot()} />);
  await flush();

  const main = screen.getByRole("main");
  const nowConsole = screen.getByTestId("now-decision-console");
  expect(main).toHaveClass("operations-shell--decision");
  expect(within(nowConsole).getByText("Estado operacional agora")).toBeVisible();
  expect(within(nowConsole).getByRole("button", { name: "Atualizar agora" })).toBeVisible();
  expect(within(nowConsole).getByTestId("telemetry-trend")).toBeVisible();
  expect(within(nowConsole).getByTestId("sensor-card-s1")).toBeVisible();
  expect(within(nowConsole).getByTestId("sensor-card-s2")).toBeVisible();

  const twinSummary = screen.getByText("Modelo 3D (opcional)");
  expect(twinSummary.closest("details")).not.toHaveAttribute("open");
});

it("shows pending and completion feedback for a failed manual retry", async () => {
  const retry = deferred();
  const source = {
    getSnapshot: vi.fn()
      .mockRejectedValueOnce(new Error("database unavailable"))
      .mockImplementationOnce(() => retry.promise),
    refresh: vi.fn(),
  };

  render(<App dataSource={source} />);
  await flush();

  const button = screen.getByRole("button", { name: "Atualizar agora" });
  button.focus();
  fireEvent.click(button);

  expect(source.getSnapshot).toHaveBeenCalledTimes(2);
  expect(source.refresh).not.toHaveBeenCalled();
  expect(button).toHaveFocus();
  expect(button).not.toBeDisabled();
  expect(button).toHaveAttribute("aria-busy", "true");
  expect(button).toHaveAttribute("aria-disabled", "true");
  expect(button).toHaveAccessibleName("Consultando dados reais…");
  expect(screen.getByRole("status")).toHaveTextContent(
    "Consultando o backend por um snapshot real…",
  );

  fireEvent.click(button);
  expect(source.getSnapshot).toHaveBeenCalledTimes(2);

  await act(async () => {
    retry.reject(new Error("still unavailable"));
    await retry.promise.catch(() => null);
  });
  await flush();

  expect(button).toHaveFocus();
  expect(button).toHaveAttribute("aria-busy", "false");
  expect(button).toHaveAttribute("aria-disabled", "false");
  expect(button).toHaveAccessibleName("Atualizar agora");
  expect(screen.getByRole("status")).toHaveTextContent(
    "A nova tentativa falhou. O backend continua indisponível.",
  );
});

it("keeps last-known data visible after a later read fails", async () => {
  const source = {
    getSnapshot: vi.fn()
      .mockResolvedValueOnce(structuredClone(lastKnownSnapshot))
      .mockRejectedValueOnce(new Error("gateway unavailable")),
    refresh: vi.fn(),
  };
  render(<App dataSource={source} />);
  await flush();

  fireEvent.click(screen.getByRole("button", { name: "Atualizar agora" }));
  await flush();

  expect(screen.getByText("Último dado real conhecido")).toBeInTheDocument();
  expect(
    screen.getByText("A atualização falhou. O último dado real conhecido continua visível.")
  ).toBeInTheDocument();
});

it("uses read-only refresh outside the Forzy window", async () => {
  const source = sourceWithSnapshot();
  render(<App dataSource={source} />);
  await flush();

  fireEvent.click(screen.getByRole("button", { name: "Atualizar agora" }));
  await flush();

  expect(source.getSnapshot).toHaveBeenCalledTimes(2);
  expect(source.refresh).not.toHaveBeenCalled();
});

it("exposes a testable Twin3D component seam with an honest fallback", async () => {
  const Twin3DProbe = vi.fn(({ snapshot, fallback, viewMode, displayContext }) => (
    <div
      data-testid="twin3d-probe"
      data-view-mode={viewMode}
      data-context-at={displayContext.generatedAt ?? displayContext.selectedAt}
    >
      {snapshot.asset.assetId}
      {fallback}
    </div>
  ));

  render(<App dataSource={sourceWithSnapshot()} Twin3DComponent={Twin3DProbe} />);
  await flush();

  expect(screen.getByTestId("twin3d-probe")).toHaveTextContent("forzy-motor-01");
  expect(Object.keys(Twin3DProbe.mock.calls.at(-1)[0]).sort()).toEqual([
    "displayContext",
    "fallback",
    "snapshot",
    "viewMode",
  ]);
  expect(screen.getByTestId("twin3d-probe")).toHaveAttribute("data-view-mode", "now");
  expect(screen.getByTestId("twin3d-probe")).toHaveAttribute(
    "data-context-at",
    receivedSnapshot.generatedAt,
  );
  expect(
    screen.getByAltText(/derivada do STEP fornecido/i)
  ).toBeInTheDocument();
});

it("mounts the real Twin3D shell by default", async () => {
  vi.useRealTimers();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({});

  render(<App dataSource={sourceWithSnapshot()} />);
  await flush();

  expect(await screen.findByText("canvas-3d-real:forzy-motor-01")).toBeInTheDocument();
});

it("exposes the visible historical workspace beside the asset identity", async () => {
  render(<App dataSource={sourceWithSnapshot()} />);
  await flush();

  expect(screen.getByRole("radio", { name: "Agora" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "Histórico" })).not.toBeChecked();
});

it("loads proportional coverage and original points only after Histórico is selected", async () => {
  const source = sourceWithTimeline();
  render(<App dataSource={source} />);
  await flush();

  fireEvent.click(screen.getByRole("radio", { name: "Histórico" }));
  await flush();

  expect(screen.getByRole("radio", { name: "Histórico" })).toBeChecked();
  const workspace = screen.getByTestId("timeline-workspace");
  expect(within(workspace).getAllByTestId("timeline-segment")).toHaveLength(4);
  expect(within(workspace).getAllByTestId("timeline-gap")).toHaveLength(3);
  expect(originalPointActions()).toHaveLength(2);
  expect(source.getTimelineOverview).toHaveBeenCalledTimes(1);
  expect(source.getTimelineSamples).toHaveBeenCalledTimes(1);
  expect(source.refresh).not.toHaveBeenCalled();
});

it("switches both channels and assessment only after one historical context commits", async () => {
  const source = sourceWithTimeline();
  const contextRequest = deferred();
  source.getTimelineContext.mockReturnValue(contextRequest.promise);
  const Twin3DProbe = ({ viewMode, displayContext }) => (
    <div
      data-testid="twin-presentation-probe"
      data-view-mode={viewMode}
      data-context-at={displayContext.generatedAt ?? displayContext.selectedAt}
    />
  );
  render(<App dataSource={source} Twin3DComponent={Twin3DProbe} />);
  await flush();

  fireEvent.click(screen.getByRole("radio", { name: "Histórico" }));
  await flush();

  expect(within(screen.getByRole("complementary", { name: "Ponto selecionado" })).getByText(
    "Selecione um ponto no gráfico",
  )).toBeVisible();
  expect(screen.getByTestId("twin-presentation-probe")).toHaveAttribute("data-view-mode", "now");

  fireEvent.click(originalPointActions()[0]);
  await flush();

  expect(within(screen.getByRole("complementary", { name: "Ponto selecionado" })).getByText(
    "Selecione um ponto no gráfico",
  )).toBeVisible();
  expect(screen.getByTestId("twin-presentation-probe")).toHaveAttribute("data-view-mode", "now");

  await act(async () => {
    contextRequest.resolve(structuredClone(historicalContextFixture));
    await contextRequest.promise;
  });
  await flush();

  const inspector = within(screen.getByRole("complementary", { name: "Ponto selecionado" }));
  expect(inspector.getByText("1,10 mm/s")).toBeVisible();
  expect(inspector.getByText("1,20 mm/s")).toBeVisible();
  expect(inspector.getByText("Candidato não confirmado")).toBeVisible();
  expect(inspector.getByText("Arquivo histórico")).toBeVisible();
  expect(screen.getByTestId("twin-presentation-probe")).toHaveAttribute(
    "data-context-at",
    historicalContextFixture.selectedAt,
  );
  expect(screen.getByTestId("twin-presentation-probe")).toHaveAttribute(
    "data-view-mode",
    "historical",
  );

  fireEvent.click(screen.getByRole("radio", { name: "Agora" }));
  expect(within(screen.getByTestId("sensor-card-s1")).getByText("34,00")).toBeVisible();
  expect(within(screen.getByTestId("sensor-card-s2")).getByText("35,00")).toBeVisible();
  expect(screen.getByTestId("twin-presentation-probe")).toHaveAttribute("data-view-mode", "now");

  fireEvent.click(screen.getByRole("radio", { name: "Histórico" }));
  await flush();
  expect(within(screen.getByRole("complementary", { name: "Ponto selecionado" })).getByText(
    "1,10 mm/s",
  )).toBeVisible();
  expect(screen.getByTestId("twin-presentation-probe")).toHaveAttribute(
    "data-context-at",
    historicalContextFixture.selectedAt,
  );
});

it("announces only transitions to a new committed historical context", async () => {
  const source = sourceWithTimeline();
  const firstCommit = deferred();
  const failedCommit = deferred();
  const secondCommit = deferred();
  const secondContext = structuredClone(missingChannelContextFixture);
  const secondSelectedAt = "2026-08-22T12:01:00.123Z";
  const secondScheduledAt = "2026-08-22T12:01:00.000Z";
  secondContext.selectedAt = secondSelectedAt;
  for (const point of [secondContext.anchor, secondContext.channels.s1]) {
    point.eventAt = secondSelectedAt;
    point.provenance.scheduledAt = secondScheduledAt;
    point.provenance.receivedAt = secondSelectedAt;
  }
  source.getTimelineContext
    .mockReturnValueOnce(firstCommit.promise)
    .mockReturnValueOnce(failedCommit.promise)
    .mockReturnValueOnce(secondCommit.promise);
  const commitAnnouncement = () => screen.queryByText(
    /Contexto hist\u00f3rico confirmado para/i,
  );

  render(<App dataSource={source} />);
  await flush();
  fireEvent.click(screen.getByRole("radio", { name: "Hist\u00f3rico" }));
  await flush();

  expect(commitAnnouncement()).not.toBeInTheDocument();
  const originalAction = originalPointActions()[0];
  fireEvent.click(originalAction);
  await flush();
  expect(commitAnnouncement()).not.toBeInTheDocument();

  await act(async () => {
    firstCommit.resolve(structuredClone(historicalContextFixture));
    await firstCommit.promise;
  });
  await flush();
  const firstAnnouncement = commitAnnouncement();
  expect(firstAnnouncement).toHaveAttribute("role", "status");
  const firstAnnouncementText = firstAnnouncement.textContent;

  fireEvent.click(screen.getByRole("radio", { name: "Agora" }));
  await flush();
  expect(commitAnnouncement()).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("radio", { name: "Hist\u00f3rico" }));
  await flush();
  expect(commitAnnouncement()).not.toBeInTheDocument();
  expect(within(screen.getByRole("complementary", { name: "Ponto selecionado" })).getByText(
    "1,10 mm/s",
  )).toBeVisible();

  fireEvent.click(originalPointActions()[0]);
  await flush();
  expect(commitAnnouncement()).not.toBeInTheDocument();
  expect(within(screen.getByRole("complementary", { name: "Ponto selecionado" })).getByText(
    "1,10 mm/s",
  )).toBeVisible();

  await act(async () => {
    failedCommit.reject(new Error("context unavailable"));
    await failedCommit.promise.catch(() => null);
  });
  await flush();
  expect(commitAnnouncement()).not.toBeInTheDocument();
  expect(screen.getByText("Não foi possível carregar este ponto.")).toBeInTheDocument();
  expect(within(screen.getByRole("complementary", { name: "Ponto selecionado" })).getByText(
    "1,10 mm/s",
  )).toBeVisible();

  fireEvent.click(originalPointActions()[0]);
  await flush();
  expect(commitAnnouncement()).not.toBeInTheDocument();

  await act(async () => {
    secondCommit.resolve(secondContext);
    await secondCommit.promise;
  });
  await flush();
  const secondAnnouncement = commitAnnouncement();
  expect(secondAnnouncement).toHaveAttribute("role", "status");
  expect(secondAnnouncement.textContent).not.toBe(firstAnnouncementText);
  expect(screen.getAllByText(/Contexto hist\u00f3rico confirmado para/i)).toHaveLength(1);
});

it("never carries a missing historical channel or absent assessment forward", async () => {
  const source = sourceWithTimeline();
  source.getTimelineContext.mockResolvedValue(structuredClone(missingChannelContextFixture));
  render(<App dataSource={source} />);
  await flush();

  fireEvent.click(screen.getByRole("radio", { name: "Histórico" }));
  await flush();
  fireEvent.click(originalPointActions()[0]);
  await flush();

  const inspector = within(screen.getByRole("complementary", { name: "Ponto selecionado" }));
  expect(inspector.getByText("1,10 mm/s")).toBeVisible();
  expect(inspector.getAllByText("Indisponível").length).toBeGreaterThanOrEqual(3);
  expect(inspector.queryByText("35,00 mm/s")).not.toBeInTheDocument();
  expect(inspector.getByText("Sem score materializado neste ponto")).toBeVisible();
  expect(inspector.getByText("Coleta ao vivo persistida")).toBeVisible();
});
