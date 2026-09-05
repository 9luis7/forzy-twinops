import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import DemoDashboard from "./DemoDashboard.jsx";
import { buildTrendPoints } from "./DemoTrends.jsx";
import { context, dataset, deferred, frame } from "./testFixtures.js";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); sessionStorage.clear(); });
it("prepares the real gateway session and offers keyboard controls with static 3D fallback", async () => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const source = { datasets: vi.fn(async () => [dataset]), create: vi.fn(async () => ({ runId: "test-run", token: "test", context: context() })), control: vi.fn(async () => context(1)) };
  render(<DemoDashboard dataSource={source} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Preparar replay" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Preparar replay" }));
  await screen.findByRole("button", { name: "Avançar 1 par" });
  expect(screen.getByLabelText("Sensores na prévia estática")).toBeVisible();
  fireEvent.keyDown(screen.getByRole("main"), { code: "ArrowRight" });
  await waitFor(() => expect(source.control).toHaveBeenCalled()); expect(source.control.mock.calls[0][1].action).toBe("step");
  await waitFor(() => expect(screen.getByRole("button", { name: "Avançar 1 par" })).toBeEnabled());
  fireEvent.keyDown(screen.getByRole("main"), { code: "Space" });
  await waitFor(() => expect(source.control).toHaveBeenCalledTimes(2)); expect(source.control.mock.calls[1][1].action).toBe("play");
});
it("preserves source order and repetitions, inserting null at a gap without interpolation", () => {
  const rows = [frame(), frame("s2"), frame("s1", 142), frame("s2", 142), frame("s1", 143, { gapBefore: true }), frame("s2", 143, { gapBefore: true })];
  const points = buildTrendPoints(rows, "temperature");
  expect(points.map((p) => p.row)).toEqual([141, 142, "gap-143", 143]);
  expect(points[2]).toMatchObject({ s1: null, s2: null, break: true }); expect(points[1].s1).toBe(points[0].s1);
});
it("keeps pause/restart clickable during advance and acknowledges the queued pause", async () => {
  vi.useFakeTimers(); vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const pending = deferred();
  const running = context(1, { replay: { ...context().replay, state: "running" } });
  const source = { datasets: vi.fn(async () => [dataset]), create: vi.fn(async () => ({ runId: "test-run", token: "test", context: running })), advance: vi.fn(() => pending.promise), control: vi.fn(async () => context(3)) };
  await act(async () => { render(<DemoDashboard dataSource={source} />); });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Preparar replay" })); });
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(source.advance).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Ⅱ Pausar" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Reiniciar" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Ⅱ Pausar" }));
  expect(screen.getByRole("button", { name: "Pausa solicitada…" })).toBeDisabled();
  expect(screen.getByText(/Aguardando a confirmação do avanço em curso/)).toBeVisible();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); }); expect(source.advance).toHaveBeenCalledTimes(1);
  await act(async () => { pending.resolve(context(2)); await pending.promise; });
  expect(source.control.mock.calls[0][1]).toMatchObject({ action: "pause", expectedRevision: 2 });
});
