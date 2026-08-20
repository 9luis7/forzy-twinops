import { assertDigitalTwinSnapshotV2 } from "../contracts/twinV2.js";

const assertBaseUrl = (baseUrl) => {
  if (
    typeof baseUrl !== "string" ||
    /[\x00-\x1f\x7f]/.test(baseUrl) ||
    baseUrl.includes("\\") ||
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
