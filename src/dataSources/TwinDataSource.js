const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

/**
 * Creates the minimal frontend protocol used to obtain and observe snapshots.
 */
export function createTwinDataSource({ getSnapshot, subscribe, capabilities } = {}) {
  if (typeof getSnapshot !== "function") {
    throw new TypeError("TwinDataSource getSnapshot must be a function");
  }
  if (typeof subscribe !== "function") {
    throw new TypeError("TwinDataSource subscribe must be a function");
  }
  if (!isObject(capabilities)) {
    throw new TypeError("TwinDataSource capabilities must be an object");
  }

  return Object.freeze({
    getSnapshot(assetTag) {
      return getSnapshot(assetTag);
    },
    subscribe(assetTag, listener) {
      return subscribe(assetTag, listener);
    },
    capabilities: Object.freeze({ ...capabilities }),
  });
}
