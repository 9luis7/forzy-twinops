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
    async getSnapshot(assetTag) {
      return getSnapshot(assetTag);
    },
    subscribe(assetTag, listener) {
      const unsubscribe = subscribe(assetTag, listener);
      if (typeof unsubscribe !== "function") {
        throw new TypeError("TwinDataSource subscribe must return an unsubscribe function");
      }
      return unsubscribe;
    },
    capabilities: Object.freeze({ ...capabilities }),
  });
}
