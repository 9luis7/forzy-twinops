import { readFileSync } from "node:fs";
import { expect, it, vi } from "vitest";
import { createGatewayTwinDataSourceV2 } from "./GatewayTwinDataSourceV2.js";

const snapshot = JSON.parse(
  readFileSync(
    new URL("../../contracts/v2/fixtures/snapshot-received-now.valid.json", import.meta.url),
    "utf8"
  )
);

it("separates read-only snapshot from refresh", async () => {
  const fetchImpl = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => snapshot })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        refreshAttempted: true,
        outcomes: { s1: "stored", s2: "stored" },
        snapshot,
      }),
    });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await source.getSnapshot("forzy-motor-01", {});
  await source.refresh("forzy-motor-01", {});

  expect(fetchImpl.mock.calls[0][1].method).toBe("GET");
  expect(fetchImpl.mock.calls[1][1].method).toBe("POST");
});

it.each([
  "https://api.example.com",
  "//api.example.com",
  "relative/path",
  "/api\\escape",
  "/api\n/escape",
  "/api\r/escape",
])("rejects unsafe or external base URL %j", (baseUrl) => {
  expect(() => createGatewayTwinDataSourceV2({ baseUrl, fetchImpl: vi.fn() })).toThrow(/baseUrl/);
});

it.each([
  ["", "/api/v2/assets/forzy-motor-01/snapshot"],
  ["/gateway/", "/gateway/api/v2/assets/forzy-motor-01/snapshot"],
])("uses an optional same-origin base URL %j", async (baseUrl, expectedUrl) => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
  const source = createGatewayTwinDataSourceV2({ baseUrl, fetchImpl });

  await source.getSnapshot("forzy-motor-01", {});

  expect(fetchImpl).toHaveBeenCalledWith(expectedUrl, expect.objectContaining({ method: "GET" }));
});

it("encodes the asset id and builds the bounded history query", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(
    source.getHistory("motor/01", { sensorId: "s2", limit: 25 })
  ).resolves.toEqual({ items: [] });

  expect(fetchImpl).toHaveBeenCalledWith(
    "/api/v2/assets/motor%2F01/history?sensorId=s2&limit=25",
    expect.objectContaining({ method: "GET" })
  );
});

it("rejects an invalid v2 snapshot and refresh envelope", async () => {
  const invalid = { ...snapshot, schemaVersion: "1.0" };
  const fetchImpl = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => invalid })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ refreshAttempted: true, outcomes: {}, snapshot: invalid }),
    });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getSnapshot("forzy-motor-01", {})).rejects.toThrow(/schemaVersion/);
  await expect(source.refresh("forzy-motor-01", {})).rejects.toThrow(/schemaVersion/);
});

it("reports a non-ok response without substituting data", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 503 });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getSnapshot("forzy-motor-01", {})).rejects.toThrow(/503/);
});

it("passes the caller AbortSignal to every request", async () => {
  const fetchImpl = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => snapshot })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ refreshAttempted: false, outcomes: {}, snapshot }),
    })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });
  const controller = new AbortController();

  await source.getSnapshot("forzy-motor-01", { signal: controller.signal });
  await source.refresh("forzy-motor-01", { signal: controller.signal });
  await source.getHistory("forzy-motor-01", {
    sensorId: "s1",
    limit: 10,
    signal: controller.signal,
  });

  for (const [, options] of fetchImpl.mock.calls) {
    expect(options.signal).toBe(controller.signal);
  }
});
