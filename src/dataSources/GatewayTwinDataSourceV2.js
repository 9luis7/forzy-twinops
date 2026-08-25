import { assertDigitalTwinSnapshotV2 } from "../contracts/twinV2.js";
import {
  assertTimelineContextV1,
  assertTimelineOverviewV1,
  assertTimelinePageV1,
} from "../contracts/timelineV1.js";

const CANONICAL_UTC_MILLIS_RE = /^(?!0000)\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d\.\d{3}Z$/;
const TIMELINE_METRICS = Object.freeze([
  "vibrationVelocityRms",
  "vibrationAcceleration",
  "temperature",
]);
const UUID_V5_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const assertBaseUrl = (baseUrl) => {
  if (
    typeof baseUrl !== "string" ||
    /[\x00-\x1f\x7f]/.test(baseUrl) ||
    baseUrl.includes("\\") ||
    baseUrl.includes("?") ||
    baseUrl.includes("#") ||
    (baseUrl !== "" && !baseUrl.startsWith("/")) ||
    baseUrl.startsWith("//")
  ) {
    throw new TypeError("GatewayTwinDataSourceV2 baseUrl must be empty or a same-origin absolute path");
  }
};

const assertAssetId = (assetId) => {
  if (typeof assetId !== "string" || assetId.length === 0) {
    throw new TypeError("GatewayTwinDataSourceV2 assetId must be a non-empty string");
  }
};

const responseError = (response) =>
  new Error(`TwinOps gateway request failed with status ${response?.status ?? "unknown"}`);

const assetPath = (assetId, operation) =>
  `/api/v2/assets/${encodeURIComponent(assetId)}/${operation}`;

const assertCanonicalUtcMillis = (value, name) => {
  if (typeof value !== "string" || !CANONICAL_UTC_MILLIS_RE.test(value)) {
    throw new TypeError(`TwinOps timeline ${name} must be canonical UTC milliseconds`);
  }
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds) || new Date(milliseconds).toISOString() !== value) {
    throw new TypeError(`TwinOps timeline ${name} must be a real UTC instant`);
  }
};

const assertTimelineAssetId = (assetId) => {
  assertAssetId(assetId);
  if (/^[a-z][a-z0-9+.-]*:/i.test(assetId) || assetId.startsWith("//")) {
    throw new TypeError("GatewayTwinDataSourceV2 timeline assetId cannot be an absolute URL");
  }
};

const assertTimelineOptions = (options, allowedKeys, operation) => {
  if (
    options === null
    || typeof options !== "object"
    || Array.isArray(options)
    || ![Object.prototype, null].includes(Object.getPrototypeOf(options))
  ) {
    throw new TypeError(`TwinOps timeline ${operation} options must be a plain object`);
  }
  if (Object.keys(options).some((key) => !allowedKeys.includes(key))) {
    throw new TypeError(`TwinOps timeline ${operation} options contain an unsupported target`);
  }
  if (
    options.signal !== undefined
    && (
      options.signal === null
      || typeof options.signal !== "object"
      || typeof options.signal.aborted !== "boolean"
      || typeof options.signal.addEventListener !== "function"
    )
  ) {
    throw new TypeError(`TwinOps timeline ${operation} options signal must be an AbortSignal`);
  }
};

const assertTimelineRange = (from, to) => {
  if (from !== undefined) assertCanonicalUtcMillis(from, "from");
  if (to !== undefined) assertCanonicalUtcMillis(to, "to");
  if (from !== undefined && to !== undefined && Date.parse(from) >= Date.parse(to)) {
    throw new TypeError("TwinOps timeline from must precede to");
  }
};

const overviewQuery = ({ from, to, sensorId, metric, maxPoints }) => {
  assertTimelineRange(from, to);
  if (sensorId !== undefined && !["s1", "s2", "all"].includes(sensorId)) {
    throw new TypeError("TwinOps timeline sensorId must be s1, s2, or all");
  }
  if (metric !== undefined && !TIMELINE_METRICS.includes(metric)) {
    throw new TypeError("TwinOps timeline metric is invalid");
  }
  if (maxPoints !== undefined && (!Number.isInteger(maxPoints) || maxPoints < 40 || maxPoints > 4000)) {
    throw new TypeError("TwinOps timeline maxPoints must be an integer from 40 to 4000");
  }

  const query = new URLSearchParams();
  if (from !== undefined) query.set("from", from);
  if (to !== undefined) query.set("to", to);
  if (sensorId !== undefined && sensorId !== "all") query.set("sensorId", sensorId);
  if (metric !== undefined) query.set("metric", metric);
  if (maxPoints !== undefined) query.set("maxPoints", String(maxPoints));
  return query;
};

const samplesQuery = ({ from, to, sensorId, metric, limit, cursor }) => {
  assertTimelineRange(from, to);
  if (sensorId !== undefined && !["s1", "s2", "all"].includes(sensorId)) {
    throw new TypeError("TwinOps timeline sensorId must be s1, s2, or all");
  }
  if (metric !== undefined && !TIMELINE_METRICS.includes(metric)) {
    throw new TypeError("TwinOps timeline metric is invalid");
  }
  if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > 500)) {
    throw new TypeError("TwinOps timeline limit must be an integer from 1 to 500");
  }
  if (
    cursor !== undefined
    && (typeof cursor !== "string" || cursor.length === 0 || cursor.length > 4096 || !/^[A-Za-z0-9_-]+$/.test(cursor))
  ) {
    throw new TypeError("TwinOps timeline cursor must be a non-empty base64url token");
  }

  const query = new URLSearchParams();
  if (from !== undefined) query.set("from", from);
  if (to !== undefined) query.set("to", to);
  if (sensorId !== undefined && sensorId !== "all") query.set("sensorId", sensorId);
  if (metric !== undefined) query.set("metric", metric);
  if (limit !== undefined) query.set("limit", String(limit));
  if (cursor !== undefined) query.set("cursor", cursor);
  return query;
};

const contextQuery = ({ pointId, at, segmentId }) => {
  const pointForm = pointId !== undefined;
  const atForm = at !== undefined || segmentId !== undefined;
  if (pointForm === atForm) {
    throw new TypeError("TwinOps timeline context requires exactly pointId or at with segmentId");
  }

  const query = new URLSearchParams();
  if (pointForm) {
    if (typeof pointId !== "string" || !UUID_V5_RE.test(pointId)) {
      throw new TypeError("TwinOps timeline pointId must be a canonical UUIDv5");
    }
    query.set("pointId", pointId);
    return query;
  }
  if (at === undefined || segmentId === undefined) {
    throw new TypeError("TwinOps timeline context requires exactly pointId or at with segmentId");
  }
  assertCanonicalUtcMillis(at, "at");
  if (typeof segmentId !== "string" || !UUID_V5_RE.test(segmentId)) {
    throw new TypeError("TwinOps timeline segmentId must be a canonical UUIDv5");
  }
  query.set("at", at);
  query.set("segmentId", segmentId);
  return query;
};

export function createGatewayTwinDataSourceV2({ baseUrl = "", fetchImpl = fetch } = {}) {
  assertBaseUrl(baseUrl);
  if (typeof fetchImpl !== "function") {
    throw new TypeError("GatewayTwinDataSourceV2 fetchImpl must be a function");
  }

  const root = baseUrl.replace(/\/$/, "");
  const requestJson = async (path, { method, signal }) => {
    const response = await fetchImpl(`${root}${path}`, { method, signal });
    if (!response?.ok) throw responseError(response);
    return response.json();
  };

  return Object.freeze({
    async getTimelineOverview(assetId, options = {}) {
      assertTimelineAssetId(assetId);
      assertTimelineOptions(
        options,
        ["from", "to", "sensorId", "metric", "maxPoints", "signal"],
        "overview"
      );
      const query = overviewQuery(options);
      const suffix = query.size > 0 ? `?${query}` : "";
      const value = await requestJson(`${assetPath(assetId, "timeline")}${suffix}`, {
        method: "GET",
        signal: options.signal,
      });
      return assertTimelineOverviewV1(value);
    },

    async getTimelineSamples(assetId, options = {}) {
      assertTimelineAssetId(assetId);
      assertTimelineOptions(
        options,
        ["from", "to", "sensorId", "metric", "limit", "cursor", "signal"],
        "samples"
      );
      const query = samplesQuery(options);
      const suffix = query.size > 0 ? `?${query}` : "";
      const value = await requestJson(`${assetPath(assetId, "timeline/samples")}${suffix}`, {
        method: "GET",
        signal: options.signal,
      });
      return assertTimelinePageV1(value);
    },

    async getTimelineContext(assetId, options = {}) {
      assertTimelineAssetId(assetId);
      assertTimelineOptions(options, ["pointId", "at", "segmentId", "signal"], "context");
      const query = contextQuery(options);
      const value = await requestJson(`${assetPath(assetId, "timeline/context")}?${query}`, {
        method: "GET",
        signal: options.signal,
      });
      return assertTimelineContextV1(value);
    },

    async getSnapshot(assetId, { signal } = {}) {
      assertAssetId(assetId);
      const value = await requestJson(assetPath(assetId, "snapshot"), {
        method: "GET",
        signal,
      });
      return assertDigitalTwinSnapshotV2(value);
    },

    async refresh(assetId, { signal } = {}) {
      assertAssetId(assetId);
      const value = await requestJson(assetPath(assetId, "refresh"), {
        method: "POST",
        signal,
      });
      if (value === null || typeof value !== "object" || Array.isArray(value)) {
        throw new TypeError("TwinOps refresh response must be an object");
      }
      assertDigitalTwinSnapshotV2(value.snapshot);
      return value;
    },

    async getHistory(assetId, { sensorId, limit, signal } = {}) {
      assertAssetId(assetId);
      if (sensorId !== undefined && !["s1", "s2"].includes(sensorId)) {
        throw new TypeError("TwinOps history sensorId must be s1 or s2");
      }
      if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > 500)) {
        throw new TypeError("TwinOps history limit must be an integer from 1 to 500");
      }

      const query = new URLSearchParams();
      if (sensorId !== undefined) query.set("sensorId", sensorId);
      if (limit !== undefined) query.set("limit", String(limit));
      const suffix = query.size > 0 ? `?${query}` : "";
      const value = await requestJson(`${assetPath(assetId, "history")}${suffix}`, {
        method: "GET",
        signal,
      });
      if (value === null || typeof value !== "object" || !Array.isArray(value.items)) {
        throw new TypeError("TwinOps history response must contain an items array");
      }
      return value;
    },
  });
}
