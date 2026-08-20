import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import receivedSnapshot from "../contracts/v2/fixtures/snapshot-received-now.valid.json";
import lastKnownSnapshot from "../contracts/v2/fixtures/snapshot-last-known.valid.json";
import App from "./App.jsx";

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
});

afterEach(() => {
  cleanup();
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
  expect(
    screen.getByRole("img", { name: "Representação do conjunto motor-bomba indisponível" })
  ).toBeInTheDocument();
  expect(Twin3DProbe).toHaveBeenCalled();
});
