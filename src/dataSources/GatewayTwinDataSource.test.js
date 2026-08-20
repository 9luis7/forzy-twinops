import { afterEach, expect, it, vi } from "vitest";
import { createGatewayTwinDataSource } from "./GatewayTwinDataSource.js";
import snapshotFixture from "../../contracts/v1/fixtures/digital-twin-snapshot-live.valid.json";

const snapshot = structuredClone(snapshotFixture);

afterEach(() => vi.useRealTimers());

it("requests the asset snapshot from the same-origin gateway route", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  const source = createGatewayTwinDataSource({ fetchImpl });

  await expect(source.getSnapshot("MTR-BMB-042")).resolves.toBe(snapshot);

  expect(fetchImpl).toHaveBeenCalledWith("/api/v1/twin/assets/MTR-BMB-042/snapshot", {
    signal: expect.any(AbortSignal),
  });
});

it.each([
  "https://example.com",
  "//example.com",
  "\\\\example.com",
  "/api\\escape",
  "relative/path",
  "/\n/evil.example",
  "/\r/evil.example",
  "/\t/evil.example",
  "/\0/evil.example",
  `/\x7f/evil.example`,
])("rejects unsafe gateway baseUrl %s", (baseUrl) => {
  expect(() => createGatewayTwinDataSource({ baseUrl, fetchImpl: vi.fn() })).toThrow(/baseUrl/);
});

it.each([
  ["", "/api/v1/twin/assets/MTR-BMB-042/snapshot"],
  ["/api-root", "/api-root/api/v1/twin/assets/MTR-BMB-042/snapshot"],
])("accepts same-origin baseUrl %j", async (baseUrl, expectedUrl) => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  const source = createGatewayTwinDataSource({ baseUrl, fetchImpl });

  await source.getSnapshot("MTR-BMB-042");

  expect(fetchImpl).toHaveBeenCalledWith(expectedUrl, expect.anything());
});

it("rejects a full-contract-invalid DigitalTwinSnapshot returned by the gateway", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ...snapshot, mode: "live", channels: [] }),
  });
  const source = createGatewayTwinDataSource({ fetchImpl });

  await expect(source.getSnapshot("MTR-BMB-042")).rejects.toThrow(/DigitalTwinSnapshot channels/);
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

it("waits for a slow snapshot before scheduling the next poll", async () => {
  vi.useFakeTimers();
  let resolveRequest;
  const fetchImpl = vi.fn(
    () =>
      new Promise((resolve) => {
        resolveRequest = () => resolve({ ok: true, json: async () => snapshot });
      })
  );
  const source = createGatewayTwinDataSource({ fetchImpl, pollMs: 5000 });
  const listener = vi.fn();

  const unsubscribe = source.subscribe("MTR-BMB-042", listener);
  await vi.advanceTimersByTimeAsync(15_000);

  expect(fetchImpl).toHaveBeenCalledTimes(1);
  expect(fetchImpl.mock.calls[0][1].signal.aborted).toBe(false);

  resolveRequest();
  await vi.advanceTimersByTimeAsync(0);
  expect(listener).toHaveBeenCalledWith(null, snapshot);

  await vi.advanceTimersByTimeAsync(4_999);
  expect(fetchImpl).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(fetchImpl).toHaveBeenCalledTimes(2);
  unsubscribe();
});

it("does not start a request for a subscription cancelled in the same turn", () => {
  vi.useFakeTimers();
  const fetchImpl = vi.fn();
  const source = createGatewayTwinDataSource({ fetchImpl });

  const unsubscribe = source.subscribe("MTR-BMB-042", vi.fn());
  unsubscribe();

  expect(fetchImpl).not.toHaveBeenCalled();
});

it("aborts an in-flight gateway request when the subscription is cancelled", async () => {
  vi.useFakeTimers();
  let requestSignal;
  const fetchImpl = vi.fn((_, { signal }) => {
    requestSignal = signal;
    return new Promise(() => {});
  });
  const source = createGatewayTwinDataSource({ fetchImpl });

  const unsubscribe = source.subscribe("MTR-BMB-042", vi.fn());
  await vi.advanceTimersByTimeAsync(0);
  unsubscribe();

  expect(requestSignal.aborted).toBe(true);
});
