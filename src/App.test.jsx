import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import receivedSnapshot from "../contracts/v2/fixtures/snapshot-received-now.valid.json";
import lastKnownSnapshot from "../contracts/v2/fixtures/snapshot-last-known.valid.json";
import overviewFixture from "../contracts/timeline/v1/fixtures/overview-unified.valid.json";
import pageFixture from "../contracts/timeline/v1/fixtures/page.valid.json";
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

const pageWithOriginalPoints = () => ({
  ...structuredClone(pageFixture),
  activeHistoricalBatchId: historicalContextFixture.provenance.activeHistoricalBatchId,
  items: [
    structuredClone(historicalContextFixture.channels.s1),
    structuredClone(historicalContextFixture.channels.s2),
  ],
  limit: 200,
});

const sourceWithTimeline = () => ({
  ...sourceWithSnapshot(),
  getTimelineOverview: vi.fn().mockResolvedValue(structuredClone(overviewFixture)),
  getTimelineSamples: vi.fn().mockResolvedValue(pageWithOriginalPoints()),
  getTimelineContext: vi.fn().mockResolvedValue(structuredClone(historicalContextFixture)),
});

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
  expect(within(workspace).getAllByRole("button", { name: /inspecionar ponto/i })).toHaveLength(2);
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

  expect(within(screen.getByTestId("sensor-card-s1")).getByText("34,00")).toBeVisible();
  expect(within(screen.getByTestId("sensor-card-s2")).getByText("35,00")).toBeVisible();
  expect(screen.getByTestId("twin-presentation-probe")).toHaveAttribute("data-view-mode", "now");

  const workspace = screen.getByTestId("timeline-workspace");
  fireEvent.click(within(workspace).getAllByRole("button", { name: /inspecionar ponto/i })[0]);
  await flush();

  expect(within(screen.getByTestId("sensor-card-s1")).getByText("34,00")).toBeVisible();
  expect(within(screen.getByTestId("sensor-card-s2")).getByText("35,00")).toBeVisible();
  expect(screen.queryByTestId("historical-context-evidence")).not.toBeInTheDocument();
  expect(screen.getByTestId("twin-presentation-probe")).toHaveAttribute("data-view-mode", "now");

  await act(async () => {
    contextRequest.resolve(structuredClone(historicalContextFixture));
    await contextRequest.promise;
  });
  await flush();

  expect(within(screen.getByTestId("sensor-card-s1")).getByText("30,00")).toBeVisible();
  expect(within(screen.getByTestId("sensor-card-s2")).getByText("30,20")).toBeVisible();
  expect(screen.getByText("Atenção")).toBeVisible();
  expect(screen.getByTestId("historical-context-evidence")).toHaveTextContent("forzy-csv");
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
  expect(within(screen.getByTestId("sensor-card-s1")).getByText("30,00")).toBeVisible();
  expect(screen.getByTestId("twin-presentation-probe")).toHaveAttribute(
    "data-context-at",
    historicalContextFixture.selectedAt,
  );
});

it("never carries a missing historical channel or absent assessment forward", async () => {
  const source = sourceWithTimeline();
  source.getTimelineContext.mockResolvedValue(structuredClone(missingChannelContextFixture));
  render(<App dataSource={source} />);
  await flush();

  fireEvent.click(screen.getByRole("radio", { name: "Histórico" }));
  await flush();
  const workspace = screen.getByTestId("timeline-workspace");
  fireEvent.click(within(workspace).getAllByRole("button", { name: /inspecionar ponto/i })[0]);
  await flush();

  expect(within(screen.getByTestId("sensor-card-s1")).getByText("30,00")).toBeVisible();
  const s2 = within(screen.getByTestId("sensor-card-s2"));
  expect(s2.getAllByText("Indisponível")).toHaveLength(3);
  expect(s2.queryByText("35,00")).not.toBeInTheDocument();

  const assessment = within(screen.getByTestId("assessment-panel"));
  expect(assessment.getByText("Avaliação causal indisponível para este ponto")).toBeVisible();
  expect(assessment.queryByText(/score|diagnóstico|probabilidade|\bRUL\b|\bcausa\b|checklist|recomendação/i)).not.toBeInTheDocument();
  expect(screen.getByTestId("historical-context-evidence")).toHaveTextContent("forzy-api");
  expect(screen.getByTestId("historical-context-evidence")).toHaveTextContent("forzy-live-window-v1");
});
