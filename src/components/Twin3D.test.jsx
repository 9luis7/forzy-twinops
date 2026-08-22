import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Twin3D, { createTwin3DComponent } from "./Twin3D.jsx";
import { normalSnapshot } from "./twin3d/testFixtures.js";


const fallback = <div data-testid="static-fallback">Prévia estática real</div>;

beforeEach(() => {
  cleanup();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("uses the supplied real fallback when WebGL is unavailable", () => {
  render(<Twin3D snapshot={normalSnapshot} fallback={fallback} />);

  expect(screen.getByTestId("static-fallback")).toBeVisible();
  expect(screen.queryByLabelText("Modelo 3D do conjunto motor-bomba")).not.toBeInTheDocument();
});

it("uses the fallback when the snapshot has no 3D capability", () => {
  render(
    <Twin3D
      snapshot={{ ...normalSnapshot, capabilities: { ...normalSnapshot.capabilities, twin3d: false } }}
      fallback={fallback}
    />,
  );

  expect(screen.getByTestId("static-fallback")).toBeVisible();
});

it("keeps the interactive twin available for reduced motion", async () => {
  window.matchMedia.mockReturnValue({ matches: true });
  HTMLCanvasElement.prototype.getContext.mockReturnValue({});
  const CanvasStub = () => <section aria-label="Modelo 3D do conjunto motor-bomba" />;
  const TestTwin3D = createTwin3DComponent(() => Promise.resolve({ default: CanvasStub }));

  render(<TestTwin3D snapshot={normalSnapshot} fallback={fallback} />);

  expect(await screen.findByLabelText("Modelo 3D do conjunto motor-bomba")).toBeVisible();
  expect(screen.queryByTestId("static-fallback")).not.toBeInTheDocument();
});

it("shows a dedicated loading state while the lazy 3D chunk is pending", async () => {
  HTMLCanvasElement.prototype.getContext.mockReturnValue({});
  let resolveCanvas;
  const pendingCanvas = new Promise((resolve) => {
    resolveCanvas = resolve;
  });
  const PendingTwin3D = createTwin3DComponent(() => pendingCanvas);

  render(<PendingTwin3D snapshot={normalSnapshot} fallback={fallback} />);

  expect(
    screen.getByRole("status", { name: "Carregando o gêmeo 3D real…" }),
  ).toHaveAttribute("aria-live", "polite");
  expect(screen.queryByTestId("static-fallback")).not.toBeInTheDocument();

  await act(async () => {
    resolveCanvas({ default: () => <section aria-label="Modelo 3D do conjunto motor-bomba" /> });
    await pendingCanvas;
  });
});

it("passes only the canonical snapshot to the lazy canvas", async () => {
  HTMLCanvasElement.prototype.getContext.mockReturnValue({});
  const CanvasStub = vi.fn(() => <section aria-label="Modelo 3D do conjunto motor-bomba" />);
  const TestTwin3D = createTwin3DComponent(() => Promise.resolve({ default: CanvasStub }));

  render(<TestTwin3D snapshot={normalSnapshot} fallback={fallback} />);

  expect(await screen.findByLabelText("Modelo 3D do conjunto motor-bomba")).toBeVisible();
  expect(Object.keys(CanvasStub.mock.calls.at(-1)[0])).toEqual(["snapshot"]);
});

it("falls back and warns exactly once when the lazy chunk rejects", async () => {
  HTMLCanvasElement.prototype.getContext.mockReturnValue({});
  const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
  const RejectingTwin3D = createTwin3DComponent(() => Promise.reject(new Error("chunk unavailable")));

  render(<RejectingTwin3D snapshot={normalSnapshot} fallback={fallback} />);

  expect(await screen.findByTestId("static-fallback")).toBeVisible();
  await waitFor(() => expect(warning).toHaveBeenCalledTimes(1));
  expect(warning).toHaveBeenCalledWith("Twin3D fallback", expect.objectContaining({ message: "chunk unavailable" }));
});

it("retries a transient canvas failure when a fresh snapshot arrives", async () => {
  HTMLCanvasElement.prototype.getContext.mockReturnValue({});
  const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
  const RecoveringCanvas = ({ snapshot }) => {
    if (snapshot.generatedAt === normalSnapshot.generatedAt) {
      throw new Error("transient model failure");
    }
    return <section aria-label="Modelo 3D recuperado" />;
  };
  const RecoveringTwin3D = createTwin3DComponent(() => Promise.resolve({ default: RecoveringCanvas }));
  const { rerender } = render(
    <RecoveringTwin3D snapshot={normalSnapshot} fallback={fallback} />,
  );

  expect(await screen.findByTestId("static-fallback")).toBeVisible();

  rerender(
    <RecoveringTwin3D
      snapshot={{ ...normalSnapshot, generatedAt: "2026-08-12T15:00:02.000Z" }}
      fallback={fallback}
    />,
  );

  expect(await screen.findByLabelText("Modelo 3D recuperado")).toBeVisible();
  expect(screen.queryByTestId("static-fallback")).not.toBeInTheDocument();
  expect(warning).toHaveBeenCalledTimes(1);
});
