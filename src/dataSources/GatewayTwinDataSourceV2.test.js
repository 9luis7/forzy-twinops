import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { createGatewayTwinDataSourceV2 } from "./GatewayTwinDataSourceV2.js";

const snapshot = JSON.parse(
  readFileSync(new URL("../../contracts/v2/fixtures/snapshot-received-now.valid.json", import.meta.url), "utf8"),
);

describe("createGatewayTwinDataSourceV2", () => {
  it("separates read-only snapshot from refresh", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => snapshot })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ refreshAttempted: true, outcomes: { s1: "stored", s2: "stored" }, snapshot }) });
    const source = createGatewayTwinDataSourceV2({ fetchImpl });

    await source.getSnapshot("forzy-motor-01", {});
    await source.refresh("forzy-motor-01", {});

    expect(fetchImpl.mock.calls[0][1].method).toBe("GET");
    expect(fetchImpl.mock.calls[1][1].method).toBe("POST");
  });

  it("builds exact v2 asset paths for snapshot, refresh and history", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => snapshot })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ refreshAttempted: true, outcomes: {}, snapshot }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [], limit: 200 }) });
    const source = createGatewayTwinDataSourceV2({ fetchImpl });

    await source.getSnapshot("forzy-motor-01", {});
    await source.refresh("forzy-motor-01", {});
    await source.getHistory("forzy-motor-01", { sensorId: "s1", limit: 50 });

    expect(fetchImpl.mock.calls[0][0]).toBe("/api/v2/assets/forzy-motor-01/snapshot");
    expect(fetchImpl.mock.calls[1][0]).toBe("/api/v2/assets/forzy-motor-01/refresh");
    expect(fetchImpl.mock.calls[2][0]).toBe("/api/v2/assets/forzy-motor-01/history?sensorId=s1&limit=50");
  });

  it("rejects an external (cross-origin) base URL", () => {
    expect(() => createGatewayTwinDataSourceV2({ baseUrl: "https://forzy.example.com" })).toThrow(/baseUrl/);
    expect(() => createGatewayTwinDataSourceV2({ baseUrl: "//forzy.example.com" })).toThrow(/baseUrl/);
  });

  it("rejects assetId/sensorId containing newline or backslash control characters", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
    const source = createGatewayTwinDataSourceV2({ fetchImpl });

    await expect(source.getSnapshot("forzy-motor-01\n/../evil", {})).rejects.toThrow(/assetId/);
    await expect(source.getSnapshot("forzy-motor-01\\evil", {})).rejects.toThrow(/assetId/);
    await expect(source.getHistory("forzy-motor-01", { sensorId: "s1\n" })).rejects.toThrow(/sensorId/);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("rejects a response body that is not a valid v2 snapshot", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ not: "a snapshot" }) });
    const source = createGatewayTwinDataSourceV2({ fetchImpl });

    await expect(source.getSnapshot("forzy-motor-01", {})).rejects.toThrow();
  });

  it("rejects a non-ok HTTP status", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    const source = createGatewayTwinDataSourceV2({ fetchImpl });

    await expect(source.getSnapshot("forzy-motor-01", {})).rejects.toThrow(/500/);
  });

  it("forwards an AbortSignal to fetch and propagates AbortError", async () => {
    const controller = new AbortController();
    const abortError = Object.assign(new Error("aborted"), { name: "AbortError" });
    const fetchImpl = vi.fn().mockRejectedValue(abortError);
    const source = createGatewayTwinDataSourceV2({ fetchImpl });

    controller.abort();
    await expect(source.getSnapshot("forzy-motor-01", { signal: controller.signal })).rejects.toThrow(/aborted/);
    expect(fetchImpl.mock.calls[0][1].signal).toBe(controller.signal);
  });
});
