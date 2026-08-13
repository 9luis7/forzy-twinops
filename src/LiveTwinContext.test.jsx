import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
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

it("can replace replay with a canonical gateway snapshot", async () => {
  const gatewaySnapshot = {
    schemaVersion: "1.0",
    assetTag: "MTR-BMB-042",
    mode: "live",
    generatedAt: "2026-08-12T15:00:01.000Z",
    status: "insufficient_data",
    freshness: "fresh",
    channels: [],
    history: [],
    assessment: null,
    capabilities: { replayControls: false, liveUpdates: true, copilot: false, twin3d: true },
  };
  const dataSource = {
    subscribe: (_assetTag, listener) => {
      listener(null, gatewaySnapshot);
      return () => {};
    },
  };
  const wrapper = ({ children }) => (
    <LiveTwinProvider dataSource={dataSource}>{children}</LiveTwinProvider>
  );

  const { result } = renderHook(() => useLiveTwin(), { wrapper });

  await waitFor(() => expect(result.current.dataMode).toBe("live"));
  expect(result.current.snapshot).toBe(gatewaySnapshot);
  expect(result.current.statusOf("MTR-BMB-042")).toBe("desconhecido");
  expect(result.current.readingOf("MTR-BMB-042")).toBeNull();
  expect(result.current.riskOf("MTR-BMB-042")).toEqual(
    expect.objectContaining({ level: "Indeterminado", score: null })
  );
  expect(result.current.componentsOf("MTR-BMB-042")).toEqual([]);
});
