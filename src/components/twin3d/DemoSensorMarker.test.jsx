import "@testing-library/jest-dom/vitest";
import React from "react";
import { readFileSync } from "node:fs";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import DemoSensorMarker from "./DemoSensorMarker.jsx";
import { frame } from "../../demo/testFixtures.js";

afterEach(cleanup);
const sensor = { sensorId: "s1", label: "Motor; posição assumida" };
it("pulses repeated receipts independently of new information without restarting on selection/control rerender", () => {
  const first = { latest: frame("s1", 141), newInformation: false, assessment: null };
  const { rerender } = render(<DemoSensorMarker sensor={sensor} data={first} onSelect={vi.fn()} />);
  const firstButton = screen.getByRole("button");
  expect(firstButton).toHaveAttribute("data-arrival", "true"); expect(firstButton).toHaveAttribute("data-new", "false");
  rerender(<DemoSensorMarker sensor={sensor} data={{ ...first }} onSelect={vi.fn()} />);
  expect(screen.getByRole("button")).toBe(firstButton);
  const repeated = { ...first, latest: frame("s1", 142) };
  expect(repeated.latest.measurements).toEqual(first.latest.measurements);
  rerender(<DemoSensorMarker sensor={sensor} data={repeated} onSelect={vi.fn()} />);
  const secondButton = screen.getByRole("button");
  expect(secondButton).not.toBe(firstButton); expect(secondButton).toHaveAttribute("data-arrival", "true");
  expect(secondButton).toHaveAttribute("data-new", "false"); expect(secondButton.textContent).toBe(firstButton.textContent);
});
it("does not pulse absent or preloaded warmup frames", () => {
  const { rerender } = render(<DemoSensorMarker sensor={sensor} data={{ latest: null, newInformation: false }} onSelect={vi.fn()} />);
  expect(screen.getByRole("button")).toHaveAttribute("data-arrival", "false");
  rerender(<DemoSensorMarker sensor={sensor} data={{ latest: frame("s1", 140, { preloaded: true }), newInformation: true }} onSelect={vi.fn()} />);
  expect(screen.getByRole("button")).toHaveAttribute("data-arrival", "false");
});
it("retains the reduced-motion opt-out for receipt animations", () => {
  const css = readFileSync("src/demo/demo.css", "utf8");
  expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{\s*\.demo-marker\[data-arrival=true\]\s*\{animation:none\}/);
  expect(css).not.toContain(".demo-marker[data-new=true]");
});
