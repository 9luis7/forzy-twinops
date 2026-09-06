import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import DemoDashboard from "./DemoDashboard.jsx";
import { buildTrendPoints } from "./DemoTrends.jsx";
import { context, dataset, deferred, event, frame } from "./testFixtures.js";

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
it.each(["ready", "degraded"])("shows request feedback across advances and preserves a %s event before POST finishes", async (status) => {
  vi.useFakeTimers(); vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const pending = deferred();
  const events = [event(), event({ eventId: "waiting-event", kind: "recovery" })];
  const running = (revision, nextEvents = events) => context(revision, {
    events: nextEvents, replay: { ...context().replay, state: "running", cursor: revision },
  });
  const source = {
    datasets: vi.fn(async () => [dataset]), create: vi.fn(async () => ({ runId: "test-run", token: "test", context: running(1) })),
    advance: vi.fn().mockResolvedValueOnce(running(2)).mockResolvedValueOnce(running(3, [event({ status, attempts: 1 }), events[1]])),
    recommend: vi.fn(() => pending.promise),
  };
  const view = render(<DemoDashboard dataSource={source} />);
  await act(async () => {});
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Preparar replay" })); });
  expect(screen.getAllByText("Na fila")).toHaveLength(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(view.container.querySelector(".demo-twin-grid")).toHaveAttribute("data-revision", "2");
  expect(screen.getByText("Consultando manual")).toHaveAttribute("title", "Consulta enviada; aguardando resposta do serviço.");
  expect(screen.getAllByText("Na fila")).toHaveLength(1);
  expect(events[0].status).toBe("pending");
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(view.container.querySelector(".demo-twin-grid")).toHaveAttribute("data-revision", "3");
  expect(source.recommend).toHaveBeenCalledTimes(1); expect(source.advance).toHaveBeenCalledTimes(2);
  expect(screen.queryByText("Consultando manual")).not.toBeInTheDocument();
  expect(screen.getByText(status === "ready" ? "Recomendação disponível" : "Resposta limitada")).toBeVisible();
  await act(async () => { pending.resolve(event({ status: "processing" })); await pending.promise; });
  expect(screen.queryByText("Consultando manual")).not.toBeInTheDocument();
});
