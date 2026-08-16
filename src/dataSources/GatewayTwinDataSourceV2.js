import { assertDigitalTwinSnapshotV2 } from "../contracts/twinV2.js";

const UNSAFE_IDENTIFIER = /[\x00-\x1f\x7f\\]/;

const assertSameOriginBaseUrl = (baseUrl) => {
  if (
    typeof baseUrl !== "string" ||
    UNSAFE_IDENTIFIER.test(baseUrl) ||
    (baseUrl !== "" && !baseUrl.startsWith("/")) ||
    baseUrl.startsWith("//")
  ) {
    throw new TypeError("GatewayTwinDataSourceV2 baseUrl must be empty or a same-origin absolute path");
  }
};

const assertSafeIdentifier = (value, label) => {
  if (typeof value !== "string" || value.length === 0 || UNSAFE_IDENTIFIER.test(value)) {
    throw new TypeError(`GatewayTwinDataSourceV2 ${label} must be a safe identifier`);
  }
};

const assetPath = (baseUrl, assetId, suffix) => {
  assertSafeIdentifier(assetId, "assetId");
  return `${baseUrl.replace(/\/$/, "")}/api/v2/assets/${encodeURIComponent(assetId)}/${suffix}`;
};

const responseError = (response) =>
  new Error(`GatewayTwinDataSourceV2 request failed with status ${response.status ?? "unknown"}`);

/**
 * Creates a same-origin gateway-backed client for the twin v2 HTTP surface
 * (GET snapshot, POST refresh, GET history). No polling/timer logic lives here.
 */
export function createGatewayTwinDataSourceV2({ baseUrl = "", fetchImpl = fetch } = {}) {
  assertSameOriginBaseUrl(baseUrl);
  if (typeof fetchImpl !== "function") {
    throw new TypeError("GatewayTwinDataSourceV2 fetchImpl must be a function");
  }

  const requestSnapshotLike = async (url, method, signal) => {
    const response = await fetchImpl(url, { method, signal });
    if (!response?.ok) throw responseError(response ?? {});
    return response.json();
  };

  return Object.freeze({
    async getSnapshot(assetId, { signal } = {}) {
      const url = assetPath(baseUrl, assetId, "snapshot");
      const body = await requestSnapshotLike(url, "GET", signal);
      return assertDigitalTwinSnapshotV2(body);
    },

    async refresh(assetId, { signal } = {}) {
      const url = assetPath(baseUrl, assetId, "refresh");
      const body = await requestSnapshotLike(url, "POST", signal);
      assertDigitalTwinSnapshotV2(body?.snapshot);
      return body;
    },

    async getHistory(assetId, { sensorId, limit, signal } = {}) {
      if (sensorId !== undefined) assertSafeIdentifier(sensorId, "sensorId");
      const params = new URLSearchParams();
      if (sensorId !== undefined) params.set("sensorId", sensorId);
      if (limit !== undefined) params.set("limit", String(limit));
      const query = params.toString();
      const url = `${assetPath(baseUrl, assetId, "history")}${query ? `?${query}` : ""}`;
      return requestSnapshotLike(url, "GET", signal);
    },
  });
}
