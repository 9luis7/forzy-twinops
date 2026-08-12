export const SCHEMA_VERSION = "1.0";

const MODES = new Set(["replay", "live"]);
const STATUSES = new Set(["normal", "watch", "alert", "unknown", "insufficient_data"]);
const FRESHNESS_VALUES = new Set(["fresh", "delayed", "expected_idle", "unavailable", "unknown"]);

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

const invalid = (field) => {
  throw new TypeError(`Invalid DigitalTwinSnapshot ${field}`);
};

/**
 * Validates the stable frontend boundary for a twin snapshot.
 *
 * This deliberately checks only the fields needed by consumers at this
 * boundary. Full JSON Schema validation remains in the contract tests.
 */
export function assertDigitalTwinSnapshot(value) {
  if (!isObject(value)) invalid("value");
  if (value.schemaVersion !== SCHEMA_VERSION) invalid("schemaVersion");
  if (typeof value.assetTag !== "string" || value.assetTag.length === 0) invalid("assetTag");
  if (!MODES.has(value.mode)) invalid("mode");
  if (!STATUSES.has(value.status)) invalid("status");
  if (!FRESHNESS_VALUES.has(value.freshness)) invalid("freshness");
  if (!Array.isArray(value.channels)) invalid("channels");
  if (!Array.isArray(value.history)) invalid("history");
  if (!isObject(value.capabilities)) invalid("capabilities");

  return value;
}

export function isDigitalTwinSnapshot(value) {
  try {
    assertDigitalTwinSnapshot(value);
    return true;
  } catch {
    return false;
  }
}
