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

  expect(screen.getByText("Carregando o último snapshot real…")).toBeInTheDocument();
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
