import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Twin3D, { createTwin3DComponent } from "./Twin3D.jsx";
import { normalSnapshot } from "./twin3d/testFixtures.js";

beforeEach(() => {
  cleanup();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("renders the supplied SVG fallback when WebGL is unavailable", () => {
  render(<Twin3D snapshot={normalSnapshot} asset={{ tag: "MTR-BMB-042" }} activeComponent={null} onSelectComponent={() => {}} fallback={<div data-testid="svg-fallback">SVG fallback</div>} />);
  expect(screen.getByTestId("svg-fallback")).toBeVisible();
  expect(screen.queryByTestId("twin3d-canvas")).not.toBeInTheDocument();
});

it("uses the fallback when 3D is not enabled by the canonical snapshot", () => {
  render(<Twin3D snapshot={{ ...normalSnapshot, capabilities: { ...normalSnapshot.capabilities, twin3d: false } }} asset={{ tag: "MTR-BMB-042" }} activeComponent={null} onSelectComponent={() => {}} fallback={<div data-testid="svg-fallback">SVG fallback</div>} />);
  expect(screen.getByTestId("svg-fallback")).toBeVisible();
});

it("falls back and warns exactly once when the lazy chunk rejects", async () => {
  HTMLCanvasElement.prototype.getContext.mockReturnValue({});
  const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
  const RejectingTwin3D = createTwin3DComponent(() => Promise.reject(new Error("chunk unavailable")));

  render(<RejectingTwin3D snapshot={normalSnapshot} asset={{ tag: "MTR-BMB-042" }} activeComponent={null} onSelectComponent={() => {}} fallback={<div data-testid="svg-fallback">SVG fallback</div>} />);

  expect(await screen.findByTestId("svg-fallback")).toBeVisible();
  await waitFor(() => expect(warning).toHaveBeenCalledTimes(1));
  expect(warning).toHaveBeenCalledWith("Twin3D fallback", expect.objectContaining({ message: "chunk unavailable" }));
});
