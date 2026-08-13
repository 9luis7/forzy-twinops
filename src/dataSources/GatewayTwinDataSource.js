import { assertDigitalTwinSnapshot } from "../contracts/twin.js";

const snapshotPath = (assetTag) =>
  `/api/v1/twin/assets/${encodeURIComponent(assetTag)}/snapshot`;

const gatewayUrl = (baseUrl, assetTag) => `${baseUrl.replace(/\/$/, "")}${snapshotPath(assetTag)}`;

const responseError = (response) =>
  new Error(`Gateway snapshot request failed with status ${response.status ?? "unknown"}`);

const assertSameOriginBaseUrl = (baseUrl) => {
  if (
    typeof baseUrl !== "string" ||
    /[\x00-\x1f\x7f]/.test(baseUrl) ||
    baseUrl.includes("\\") ||
    (baseUrl !== "" && !baseUrl.startsWith("/")) ||
    baseUrl.startsWith("//")
  ) {
    throw new TypeError("GatewayTwinDataSource baseUrl must be empty or a same-origin absolute path");
  }
};

/**
 * Creates a same-origin gateway-backed source for canonical digital-twin snapshots.
 */
export function createGatewayTwinDataSource({ baseUrl = "", fetchImpl = fetch, pollMs = 5000 } = {}) {
  assertSameOriginBaseUrl(baseUrl);
  if (typeof fetchImpl !== "function") {
    throw new TypeError("GatewayTwinDataSource fetchImpl must be a function");
  }
  if (!Number.isFinite(pollMs) || pollMs <= 0) {
    throw new TypeError("GatewayTwinDataSource pollMs must be a positive number");
  }

  const requestSnapshot = async (assetTag, signal) => {
    const response = await fetchImpl(gatewayUrl(baseUrl, assetTag), { signal });
    if (!response?.ok) throw responseError(response ?? {});

    return assertDigitalTwinSnapshot(await response.json());
  };

  return Object.freeze({
    async getSnapshot(assetTag) {
      const controller = new AbortController();
      return requestSnapshot(assetTag, controller.signal);
    },

    subscribe(assetTag, listener) {
      if (typeof listener !== "function") {
        throw new TypeError("GatewayTwinDataSource listener must be a function");
      }

      let active = true;
      let controller = null;
      let timer = null;
      const poll = async () => {
        const requestController = new AbortController();
        controller = requestController;

        try {
          const value = await requestSnapshot(assetTag, requestController.signal);
          if (active) listener(null, value);
        } catch (error) {
          if (active && error?.name !== "AbortError") listener(error);
        } finally {
          if (controller === requestController) controller = null;
          if (active) timer = setTimeout(poll, pollMs);
        }
      };

      timer = setTimeout(poll, 0);

      return () => {
        if (!active) return;
        active = false;
        if (timer !== null) clearTimeout(timer);
        controller?.abort();
      };
    },

    capabilities: Object.freeze({
      replayControls: false,
      liveUpdates: true,
      copilot: false,
      twin3d: false,
    }),
  });
}
