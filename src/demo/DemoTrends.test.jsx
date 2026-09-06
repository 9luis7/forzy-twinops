import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import DemoTrends from "./DemoTrends.jsx";
import { context, frame } from "./testFixtures.js";

beforeEach(() => vi.stubGlobal("ResizeObserver", class {
  constructor(callback) { this.callback = callback; }
  observe(target) { this.callback([{ target, contentRect: { width: 640, height: 190 } }]); }
  unobserve() {}
  disconnect() {}
}));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows São Paulo graph clock labels while retaining the canonical history instants", () => {
  const snapshot = context(1, { history: [frame("s1", 141), frame("s2", 141), frame("s1", 142), frame("s2", 142)] });
  const original = structuredClone(snapshot.history);
  const { container } = render(<DemoTrends context={snapshot} selected="all" onSelect={() => {}} />);
  expect(screen.getByText(/horário de São Paulo/)).toBeVisible();
  const ticks = [...container.querySelectorAll(".recharts-xAxis .recharts-cartesian-axis-tick-value")];
  expect(ticks.length).toBeGreaterThan(0);
  expect(ticks.every((tick) => tick.textContent === "12:00:00")).toBe(true);
  expect(container).not.toHaveTextContent("UTC");
  expect(snapshot.history).toEqual(original);
});
