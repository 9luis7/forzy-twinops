import { afterEach, expect, it, vi } from "vitest";
import { createGatewayTwinDataSource } from "./GatewayTwinDataSource.js";

const snapshot = {
  schemaVersion: "1.0",
  assetTag: "MTR-BMB-042",
  mode: "live",
  generatedAt: "2026-08-12T15:00:00.000Z",
  status: "normal",
  freshness: "fresh",
  channels: [],
  history: [],
  assessment: null,
  capabilities: {
    replayControls: false,
    liveUpdates: true,
    copilot: false,
    twin3d: true,
  },
};

afterEach(() => vi.useRealTimers());

it("requests the asset snapshot from the same-origin gateway route", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  const source = createGatewayTwinDataSource({ fetchImpl });

  await expect(source.getSnapshot("MTR-BMB-042")).resolves.toBe(snapshot);

  expect(fetchImpl).toHaveBeenCalledWith("/api/v1/twin/assets/MTR-BMB-042/snapshot", {
    signal: expect.any(AbortSignal),
  });
});

it("rejects an invalid DigitalTwinSnapshot returned by the gateway", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ schemaVersion: "1.0", assetTag: "MTR-BMB-042" }),
  });
  const source = createGatewayTwinDataSource({ fetchImpl });

  await expect(source.getSnapshot("MTR-BMB-042")).rejects.toThrow(/DigitalTwinSnapshot mode/);
});

it("reports polling failures without substituting a normal snapshot", async () => {
  vi.useFakeTimers();
  const failure = new Error("gateway unavailable");
  const fetchImpl = vi.fn().mockRejectedValue(failure);
  const source = createGatewayTwinDataSource({ fetchImpl });
  const listener = vi.fn();

  const unsubscribe = source.subscribe("MTR-BMB-042", listener);
  await vi.advanceTimersByTimeAsync(0);
  unsubscribe();

  expect(listener).toHaveBeenCalledTimes(1);
  expect(listener).toHaveBeenCalledWith(failure);
  expect(listener).not.toHaveBeenCalledWith(null, expect.anything());
});

it("stops polling when the subscription is cancelled", async () => {
  vi.useFakeTimers();
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  const source = createGatewayTwinDataSource({ fetchImpl, pollMs: 5000 });
  const listener = vi.fn();

  const unsubscribe = source.subscribe("MTR-BMB-042", listener);
  await vi.advanceTimersByTimeAsync(0);
  expect(listener).toHaveBeenCalledWith(null, snapshot);

  unsubscribe();
  await vi.advanceTimersByTimeAsync(10_000);

  expect(fetchImpl).toHaveBeenCalledTimes(1);
});
