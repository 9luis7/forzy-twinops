import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import receivedSnapshot from "../contracts/v2/fixtures/snapshot-received-now.valid.json";
import lastKnownSnapshot from "../contracts/v2/fixtures/snapshot-last-known.valid.json";
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

const ragSource = () => ({
  query: vi.fn(),
  createDraft: vi.fn(),
  uploadDocument: vi.fn(),
  getCorpus: vi.fn(),
  testRetrieval: vi.fn(),
  publish: vi.fn(),
  reactivate: vi.fn(),
});

const historySource = () => {
  const time = "2026-05-19T17:40:14.229Z";
  const dataset = { datasetId: "history-test", label: "Histórico de teste", pairCount: 1, readingCount: 2, startAt: time, endAt: time, sourceFormat: "OOXML" };
  const frames = ["s1", "s2"].map((sensorId) => ({
    sensorId, frameId: sensorId, sourceRow: 1, observedAt: time, receivedAt: null, preloaded: false, qualityFlags: [], gapBefore: false,
    measurements: { vibrationVelocityRms: { value: 1.2, unit: "mm/s" }, temperature: { value: 30, unit: "degC" }, vibrationAcceleration: { value: 0.1, unit: "g" } },
  }));
  return {
    datasets: vi.fn().mockResolvedValue([dataset]),
    context: vi.fn().mockResolvedValue({
      schemaVersion: "historical-1.0", mode: "historical", revision: "a".repeat(64), dataset, assetId: "forzy-motor-01",
      selection: { from: null, to: null, endRow: 1, limit: 300, observedAt: time, totalPairs: 1, returnedPairs: 1, hasPrevious: false, hasNext: false, previousEndRow: null, nextEndRow: null },
      sensors: Object.fromEntries(frames.map((frame) => [frame.sensorId, { latest: frame, assessment: null, assessmentState: "unavailable", newInformation: false }])),
      history: frames, status: "insufficient_data", generatedAt: time, capabilities: { twin3d: true, copilot: false, replayControls: false },
    }),
    query: vi.fn(), create: vi.fn(), advance: vi.fn(),
  };
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

it("renders one real asset with working product navigation and an optional demonstration", async () => {
  render(<App dataSource={sourceWithSnapshot()} />);
  await flush();

  expect(screen.getByText("Conjunto motor-bomba monitorado")).toBeInTheDocument();
  for (const label of ["Planta", "Ordens", "Documentos", "MTR-BMB-042"]) {
    expect(screen.queryByText(label)).not.toBeInTheDocument();
  }
  expect(screen.getByRole("link", { name: "Visão geral" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Histórico", exact: true })).toHaveAttribute("href", "/history");
  expect(screen.getByRole("link", { name: "Demonstração" })).toHaveAttribute("href", "/demo");
  expect(screen.getByRole("button", { name: "Copiloto", exact: true })).toHaveAttribute("aria-expanded", "false");
});

it("shows an honest loading state before the first real snapshot", () => {
  const source = {
    getSnapshot: vi.fn(() => new Promise(() => {})),
    refresh: vi.fn(),
  };

  render(<App dataSource={source} />);

  const loading = screen.getByRole("status", {
    name: "Consultando os dados do equipamento…",
  });
  expect(loading).toHaveAttribute("aria-live", "polite");
  expect(loading).toHaveTextContent(
    /Conectando à fonte de dados|Validando telemetria S1 e S2|Preparando o painel operacional|Sincronizando o gêmeo digital/,
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
  expect(screen.queryByText("Consultando os dados do equipamento…")).not.toBeInTheDocument();
  expect(source.refresh).not.toHaveBeenCalled();
});

it("shows backend unavailability without creating a normal snapshot", async () => {
  const source = {
    getSnapshot: vi.fn().mockRejectedValue(new Error("database unavailable")),
    refresh: vi.fn(),
  };

  render(<App dataSource={source} historyDataSource={null} />);
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
  const Twin3DProbe = vi.fn(({ snapshot, fallback }) => (
    <div data-testid="twin3d-probe">
      {snapshot.asset.assetId}
      {fallback}
    </div>
  ));

  render(<App dataSource={sourceWithSnapshot()} Twin3DComponent={Twin3DProbe} />);
  await flush();

  expect(screen.getByTestId("twin3d-probe")).toHaveTextContent("forzy-motor-01");
  expect(Object.keys(Twin3DProbe.mock.calls.at(-1)[0]).sort()).toEqual([
    "fallback",
    "snapshot",
  ]);
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

it("integrates the public assistant only from the backend copilot capability", async () => {
  const snapshot = structuredClone(receivedSnapshot);
  snapshot.capabilities.copilot = true;
  const ragDataSource = ragSource();

  render(<App dataSource={sourceWithSnapshot(snapshot)} ragDataSource={ragDataSource} />);
  await flush();

  expect(screen.queryByRole("heading", { name: "Assistente técnico" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Copiloto", exact: true }));
  expect(screen.getByRole("heading", { name: "Assistente técnico" })).toBeInTheDocument();
  expect(screen.getByRole("form", { name: "Consultar o assistente técnico" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /admin/i })).not.toBeInTheDocument();
  expect(ragDataSource.query).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Pergunta técnica"), { target: { value: "Como interpretar esta vibração?" } });
  fireEvent.click(screen.getByRole("button", { name: "Fechar copiloto" }));
  fireEvent.click(screen.getByRole("button", { name: "Copiloto", exact: true }));
  expect(screen.getByLabelText("Pergunta técnica")).toHaveValue("Como interpretar esta vibração?");
  expect(ragDataSource.query).not.toHaveBeenCalled();
});

it("keeps real historical records usable on the overview when current collection fails", async () => {
  vi.useRealTimers();
  const source = { getSnapshot: vi.fn().mockRejectedValue(new Error("live unavailable")), refresh: vi.fn() };
  const historyDataSource = historySource();
  const TwinProbe = ({ snapshot }) => <div data-testid="historical-main-twin" data-mode={snapshot.mode} data-revision={snapshot.revision} />;
  render(<App dataSource={source} historyDataSource={historyDataSource} Twin3DComponent={TwinProbe} />);
  expect(await screen.findByTestId("historical-main-twin")).toHaveAttribute("data-mode", "historical");
  expect(screen.getByRole("heading", { name: "Visão geral" })).toBeVisible();
  expect(screen.getByText(/A coleta atual está indisponível/)).toBeVisible();
  expect(screen.getByText(/Análise retrospectiva · score relativo, não probabilidade de falha/)).toBeVisible();
  expect(screen.queryByRole("form", { name: "Filtros do histórico" })).not.toBeInTheDocument();
  expect(historyDataSource.create).not.toHaveBeenCalled();
  expect(historyDataSource.advance).not.toHaveBeenCalled();
  expect(historyDataSource.query).not.toHaveBeenCalled();
  expect(source.refresh).not.toHaveBeenCalled();
});

it("opens the full history route without bootstrapping current collection or replay", async () => {
  vi.useRealTimers();
  const source = sourceWithSnapshot(), historyDataSource = historySource();
  render(<App pathname="/history" dataSource={source} historyDataSource={historyDataSource} Twin3DComponent={() => null} />);
  expect(await screen.findByRole("form", { name: "Filtros do histórico" })).toBeVisible();
  expect(await screen.findByRole("table")).toBeVisible();
  expect(screen.getByRole("link", { name: "Histórico", exact: true })).toHaveAttribute("aria-current", "page");
  expect(source.getSnapshot).not.toHaveBeenCalled();
  expect(source.refresh).not.toHaveBeenCalled();
  expect(historyDataSource.create).not.toHaveBeenCalled();
  expect(historyDataSource.query).not.toHaveBeenCalled();
});

it.each(["/rag-admin", "/rag-admin/"])(
  "renders the protected admin surface only for the exact enabled pathname %s",
  (pathname) => {
    const dataSource = sourceWithSnapshot();
    const ragDataSource = ragSource();

    render(
      <App
        dataSource={dataSource}
        ragDataSource={ragDataSource}
        pathname={pathname}
        ragAdminEnabled
      />
    );

    expect(screen.getByRole("heading", { name: "Administração do RAG" })).toBeInTheDocument();
    expect(screen.queryByText("Conjunto motor-bomba monitorado")).not.toBeInTheDocument();
    expect(dataSource.getSnapshot).not.toHaveBeenCalled();
  }
);

it.each([
  ["/rag-admin", false],
  ["/rag-admin/extra", true],
  ["/operations", true],
])("keeps the public operations app for pathname %s with admin flag %s", async (pathname, ragAdminEnabled) => {
  const dataSource = sourceWithSnapshot();

  render(
    <App
      dataSource={dataSource}
      ragDataSource={ragSource()}
      pathname={pathname}
      ragAdminEnabled={ragAdminEnabled}
    />
  );
  await flush();

  expect(screen.getByText("Conjunto motor-bomba monitorado")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Administração do RAG" })).not.toBeInTheDocument();
});
