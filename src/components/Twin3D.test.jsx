import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import Twin3D from "./Twin3D.jsx";
import { normalSnapshot } from "./twin3d/testFixtures.js";

beforeEach(() => {
  cleanup();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
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
