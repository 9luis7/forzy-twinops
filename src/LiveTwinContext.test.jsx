import React from "react";
import { renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";

const telemetry = vi.hoisted(() => ({
  last: {
    ts: Date.parse("2026-08-12T15:00:00.000Z"),
    label: "12:00:00",
    temperature: 34,
    vibration: 2.1,
    current: 17,
    rotation: 1760,
  },
  points: [],
  running: true,
  status: "normal",
  scenario: null,
}));

vi.mock("./useLiveTelemetry.js", () => ({
  useLiveTelemetry: () => telemetry,
}));

import { LiveTwinProvider, useLiveTwin } from "./LiveTwinContext.jsx";

it("exposes the canonical replay snapshot while retaining the legacy selectors", () => {
  const wrapper = ({ children }) => <LiveTwinProvider>{children}</LiveTwinProvider>;
  const { result } = renderHook(() => useLiveTwin(), { wrapper });

  expect(result.current.dataMode).toBe("replay");
  expect(result.current.snapshot).toMatchObject({
    schemaVersion: "1.0",
    assetTag: "MTR-BMB-042",
    mode: "replay",
    status: "normal",
    freshness: "expected_idle",
  });
  expect(result.current.snapshot.channels[0].measurements.vibrationAcceleration.value).toBe(2.1);
  expect(result.current.statusOf("MTR-BMB-042")).toBe("normal");
  expect(result.current.readingOf("MTR-BMB-042")).toMatchObject({ temperature: 34 });
  expect(result.current.riskOf("MTR-BMB-042")).toMatchObject({ score: 12 });
  expect(result.current.alertOf).toBeTypeOf("function");
  expect(result.current.alertsList).toBeTypeOf("function");
});
