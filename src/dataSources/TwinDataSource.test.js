import { expect, it, vi } from "vitest";
import { createTwinDataSource } from "./TwinDataSource.js";

it("delegates getSnapshot without exposing mutable capabilities", async () => {
  const getSnapshot = vi.fn().mockResolvedValue({ schemaVersion: "1.0" });
  const source = createTwinDataSource({
    getSnapshot,
    subscribe: () => () => {},
    capabilities: { liveUpdates: true },
  });

  await source.getSnapshot("MTR-BMB-042");

  expect(getSnapshot).toHaveBeenCalledWith("MTR-BMB-042");
  expect(Object.isFrozen(source.capabilities)).toBe(true);
});

it("delegates subscriptions and returns their unsubscribe function", () => {
  const unsubscribe = vi.fn();
  const subscribe = vi.fn().mockReturnValue(unsubscribe);
  const listener = vi.fn();
  const source = createTwinDataSource({ getSnapshot: vi.fn(), subscribe, capabilities: {} });

  expect(source.subscribe("MTR-BMB-042", listener)).toBe(unsubscribe);
  expect(subscribe).toHaveBeenCalledWith("MTR-BMB-042", listener);
});

it("rejects an incomplete data source protocol", () => {
  expect(() => createTwinDataSource({ getSnapshot: () => {}, capabilities: {} })).toThrow(/subscribe/);
  expect(() => createTwinDataSource({ subscribe: () => () => {}, capabilities: {} })).toThrow(/getSnapshot/);
});
