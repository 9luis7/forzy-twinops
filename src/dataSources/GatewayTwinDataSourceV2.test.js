import { readFileSync } from "node:fs";
import { expect, it, vi } from "vitest";
import { createGatewayTwinDataSourceV2 } from "./GatewayTwinDataSourceV2.js";

const snapshot = JSON.parse(
  readFileSync(
    new URL("../../contracts/v2/fixtures/snapshot-received-now.valid.json", import.meta.url),
    "utf8"
  )
);
const overview = JSON.parse(
  readFileSync(
    new URL("../../contracts/timeline/v1/fixtures/overview-unified.valid.json", import.meta.url),
    "utf8"
  )
);
const timelinePage = JSON.parse(
  readFileSync(
    new URL("../../contracts/timeline/v1/fixtures/page.valid.json", import.meta.url),
    "utf8"
  )
);
const timelineContext = JSON.parse(
  readFileSync(
    new URL(
      "../../contracts/timeline/v1/fixtures/context-historical-candidate.valid.json",
      import.meta.url
    ),
    "utf8"
  )
);
const canonicalCursor = "AQIDBA";

it("requests a validated overview through the fixed same-origin route", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => overview });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getTimelineOverview("forzy-motor-01", {
    from: "2026-05-19T14:46:10.921Z",
    to: "2026-08-13T00:00:00.000Z",
    sensorId: "all",
    metric: "temperature",
    maxPoints: 1200,
  })).resolves.toBe(overview);

  expect(fetchImpl).toHaveBeenCalledWith(
    "/api/v2/assets/forzy-motor-01/timeline?from=2026-05-19T14%3A46%3A10.921Z&to=2026-08-13T00%3A00%3A00.000Z&metric=temperature&maxPoints=1200",
    { method: "GET", signal: undefined }
  );
});

it("requests original samples through the fixed same-origin route", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => timelinePage });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getTimelineSamples("motor/01", {
    from: "2026-05-19T14:46:10.921Z",
    to: "2026-08-13T00:00:00.000Z",
    sensorId: "s2",
    metric: "vibrationAcceleration",
    limit: 200,
    cursor: canonicalCursor,
  })).resolves.toBe(timelinePage);

  expect(fetchImpl).toHaveBeenCalledWith(
    `/api/v2/assets/motor%2F01/timeline/samples?from=2026-05-19T14%3A46%3A10.921Z&to=2026-08-13T00%3A00%3A00.000Z&sensorId=s2&metric=vibrationAcceleration&limit=200&cursor=${canonicalCursor}`,
    { method: "GET", signal: undefined }
  );
});

it("accepts a canonical cursor at the 4096-character boundary", async () => {
  const maxCursor = "A".repeat(4096);
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => timelinePage });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getTimelineSamples("forzy-motor-01", {
    cursor: maxCursor,
  })).resolves.toBe(timelinePage);

  expect(fetchImpl).toHaveBeenCalledTimes(1);
  expect(fetchImpl.mock.calls[0][0].endsWith(`cursor=${maxCursor}`)).toBe(true);
});

it("requests an exact original-point context through the fixed same-origin route", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => timelineContext });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });
  const controller = new AbortController();

  await expect(source.getTimelineContext("forzy-motor-01", {
    pointId: timelineContext.anchor.pointId,
    signal: controller.signal,
  })).resolves.toBe(timelineContext);

  expect(fetchImpl).toHaveBeenCalledWith(
    `/api/v2/assets/forzy-motor-01/timeline/context?pointId=${timelineContext.anchor.pointId}`,
    { method: "GET", signal: controller.signal }
  );
});

it("builds the canonical at plus segment context selector", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => timelineContext });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await source.getTimelineContext("forzy-motor-01", {
    at: timelineContext.selectedAt,
    segmentId: timelineContext.segmentId,
  });

  expect(fetchImpl).toHaveBeenCalledWith(
    `/api/v2/assets/forzy-motor-01/timeline/context?at=2026-08-22T12%3A00%3A00.000Z&segmentId=${timelineContext.segmentId}`,
    { method: "GET", signal: undefined }
  );
});

it.each([
  ["microseconds", { from: "2026-08-22T12:00:00.000000Z" }, /from/],
  ["offset timestamp", { from: "2026-08-22T09:00:00.000-03:00" }, /from/],
  ["impossible date", { from: "2026-02-30T12:00:00.000Z" }, /from/],
  ["year zero", { from: "0000-01-01T00:00:00.000Z" }, /from/],
  ["equal range", {
    from: "2026-08-22T12:00:00.000Z",
    to: "2026-08-22T12:00:00.000Z",
  }, /precede/],
  ["inverted range", {
    from: "2026-08-22T12:00:00.001Z",
    to: "2026-08-22T12:00:00.000Z",
  }, /precede/],
  ["unknown sensor", { sensorId: "s3" }, /sensorId/],
  ["unknown metric", { metric: "torque" }, /metric/],
  ["too few overview points", { maxPoints: 39 }, /maxPoints/],
  ["too many overview points", { maxPoints: 4001 }, /maxPoints/],
  ["non-integer overview points", { maxPoints: 40.5 }, /maxPoints/],
  ["string overview points", { maxPoints: "1200" }, /maxPoints/],
])("rejects invalid overview input: %s", async (_, options, expectedError) => {
  const fetchImpl = vi.fn();
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getTimelineOverview("forzy-motor-01", options)).rejects.toThrow(expectedError);

  expect(fetchImpl).not.toHaveBeenCalled();
});

it.each([
  ["zero limit", { limit: 0 }, /limit/],
  ["limit above 500", { limit: 501 }, /limit/],
  ["decimal limit", { limit: 1.5 }, /limit/],
  ["blank cursor", { cursor: "" }, /cursor/],
  ["non-base64url cursor", { cursor: "abc+def" }, /cursor/],
  ["modulo-one cursor", { cursor: "A" }, /cursor/],
  ["non-canonical residual bits", { cursor: "abc_DEF-123" }, /cursor/],
  ["oversized cursor", { cursor: "a".repeat(4097) }, /cursor/],
  ["null cursor", { cursor: null }, /cursor/],
])("rejects invalid samples input: %s", async (_, options, expectedError) => {
  const fetchImpl = vi.fn();
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getTimelineSamples("forzy-motor-01", options)).rejects.toThrow(expectedError);

  expect(fetchImpl).not.toHaveBeenCalled();
});

it.each([
  ["empty selector", {}, /exactly pointId or at with segmentId/],
  ["all selector fields", {
    pointId: timelineContext.anchor.pointId,
    at: timelineContext.selectedAt,
    segmentId: timelineContext.segmentId,
  }, /exactly pointId or at with segmentId/],
  ["at without segment", { at: timelineContext.selectedAt }, /exactly pointId or at with segmentId/],
  ["segment without at", { segmentId: timelineContext.segmentId }, /exactly pointId or at with segmentId/],
  ["non-UUID point", { pointId: "point-1" }, /pointId/],
  ["uppercase UUID point", { pointId: "AAAAAAAA-AAAA-5AAA-8AAA-AAAAAAAAAAAA" }, /pointId/],
  ["non-v5 point", { pointId: "00000000-0000-4000-8000-000000000004" }, /pointId/],
  ["invalid at", { at: "2026-08-22T12:00:00Z", segmentId: timelineContext.segmentId }, /at/],
  ["non-UUID segment", { at: timelineContext.selectedAt, segmentId: "segment-1" }, /segmentId/],
])("rejects invalid context input: %s", async (_, options, expectedError) => {
  const fetchImpl = vi.fn();
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getTimelineContext("forzy-motor-01", options)).rejects.toThrow(expectedError);

  expect(fetchImpl).not.toHaveBeenCalled();
});

it.each([
  ["getTimelineOverview", { metric: "temperature", target: "https://evil.example/timeline" }],
  ["getTimelineSamples", { limit: 25, url: "//evil.example/timeline" }],
  ["getTimelineContext", { pointId: timelineContext.anchor.pointId, endpoint: "/other" }],
])("rejects caller-controlled targets for %s", async (method, options) => {
  const fetchImpl = vi.fn();
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source[method]("forzy-motor-01", options)).rejects.toThrow(/options/);

  expect(fetchImpl).not.toHaveBeenCalled();
});

it("rejects an absolute URL disguised as a timeline asset", async () => {
  const fetchImpl = vi.fn();
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getTimelineOverview("https://evil.example/asset", {})).rejects.toThrow(/assetId/);

  expect(fetchImpl).not.toHaveBeenCalled();
});

it.each([
  ["getTimelineOverview", ".", {}],
  ["getTimelineOverview", "..", {}],
  ["getTimelineSamples", ".", {}],
  ["getTimelineSamples", "..", {}],
  ["getTimelineContext", ".", { pointId: timelineContext.anchor.pointId }],
  ["getTimelineContext", "..", { pointId: timelineContext.anchor.pointId }],
])("rejects dot-segment assetId before fetch for %s: %s", async (method, assetId, options) => {
  const fetchImpl = vi.fn();
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source[method](assetId, options)).rejects.toThrow(/assetId/);

  expect(fetchImpl).not.toHaveBeenCalled();
});

it.each([
  ["getTimelineOverview", {}, overview, "timeline"],
  ["getTimelineSamples", {}, timelinePage, "timeline/samples"],
  ["getTimelineContext", { pointId: timelineContext.anchor.pointId }, timelineContext, "timeline/context"],
])("keeps encoded asset text inside the fixed allowlist for %s", async (
  method,
  options,
  response,
  operation,
) => {
  const assetId = "%2e%2e/../motor";
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => response });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await source[method](assetId, options);

  const requestTarget = fetchImpl.mock.calls[0][0];
  const resolved = new URL(requestTarget, "https://twinops.example/");
  expect(resolved.origin).toBe("https://twinops.example");
  expect(resolved.pathname).toBe(
    `/api/v2/assets/${encodeURIComponent(assetId)}/${operation}`
  );
});

it.each([
  ["overview", "getTimelineOverview", { ...overview, schemaVersion: "2.0" }, {}],
  ["page", "getTimelineSamples", { ...timelinePage, hasMore: !timelinePage.hasMore }, {}],
  ["context", "getTimelineContext", { ...timelineContext, selectedAt: "2026-08-22T12:00:00Z" }, {
    pointId: timelineContext.anchor.pointId,
  }],
])("rejects an invalid %s response before returning", async (_, method, invalid, options) => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => invalid });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source[method]("forzy-motor-01", options)).rejects.toThrow();
});

it("reports timeline conflict responses without substituting data", async () => {
  const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 409 });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getTimelineSamples("forzy-motor-01", {})).rejects.toThrow(/409/);
});

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
  "/api?target=https://api.example.com",
  "/api#https://api.example.com",
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

it.each([
  ["unknown sensor", { sensorId: "s3", limit: 25 }, /sensorId/],
  ["zero limit", { sensorId: "s1", limit: 0 }, /limit/],
  ["limit above 500", { sensorId: "s1", limit: 501 }, /limit/],
  ["decimal limit", { sensorId: "s1", limit: 1.5 }, /limit/],
  ["string limit", { sensorId: "s1", limit: "10" }, /limit/],
  ["NaN limit", { sensorId: "s1", limit: Number.NaN }, /limit/],
])("rejects %s before issuing a history request", async (_, options, expectedError) => {
  const fetchImpl = vi.fn();
  const source = createGatewayTwinDataSourceV2({ fetchImpl });

  await expect(source.getHistory("forzy-motor-01", options)).rejects.toThrow(expectedError);

  expect(fetchImpl).not.toHaveBeenCalled();
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
    .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) })
    .mockResolvedValueOnce({ ok: true, json: async () => overview })
    .mockResolvedValueOnce({ ok: true, json: async () => timelinePage })
    .mockResolvedValueOnce({ ok: true, json: async () => timelineContext });
  const source = createGatewayTwinDataSourceV2({ fetchImpl });
  const controller = new AbortController();

  await source.getSnapshot("forzy-motor-01", { signal: controller.signal });
  await source.refresh("forzy-motor-01", { signal: controller.signal });
  await source.getHistory("forzy-motor-01", {
    sensorId: "s1",
    limit: 10,
    signal: controller.signal,
  });
  await source.getTimelineOverview("forzy-motor-01", {
    metric: "temperature",
    signal: controller.signal,
  });
  await source.getTimelineSamples("forzy-motor-01", {
    limit: 50,
    signal: controller.signal,
  });
  await source.getTimelineContext("forzy-motor-01", {
    pointId: timelineContext.anchor.pointId,
    signal: controller.signal,
  });

  for (const [, options] of fetchImpl.mock.calls) {
    expect(options.signal).toBe(controller.signal);
  }
});
