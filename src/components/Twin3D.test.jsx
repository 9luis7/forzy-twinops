import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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

it("uses the fallback for reduced motion", () => {
  window.matchMedia.mockReturnValue({ matches: true });
  HTMLCanvasElement.prototype.getContext.mockReturnValue({});

  render(<Twin3D snapshot={normalSnapshot} fallback={fallback} />);

  expect(screen.getByTestId("static-fallback")).toBeVisible();
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
