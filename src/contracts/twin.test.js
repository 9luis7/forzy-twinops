import { expect, it } from "vitest";
import { assertDigitalTwinSnapshot, isDigitalTwinSnapshot, SCHEMA_VERSION } from "./twin.js";

const snapshot = () => ({
  schemaVersion: "1.0",
  assetTag: "MTR-BMB-042",
  mode: "live",
  status: "normal",
  freshness: "fresh",
  channels: [],
  history: [],
  capabilities: {},
});

it("exports the current schema version", () => {
  expect(SCHEMA_VERSION).toBe("1.0");
});

it("rejects an unknown schema version", () => {
  expect(() => assertDigitalTwinSnapshot({ schemaVersion: "2.0" })).toThrow(/schemaVersion/);
});

it("accepts the public snapshot boundary and returns the same value", () => {
  const value = snapshot();
  expect(assertDigitalTwinSnapshot(value)).toBe(value);
  expect(isDigitalTwinSnapshot(value)).toBe(true);
});

it.each([
  ["assetTag", ""],
  ["mode", "offline"],
  ["status", "broken"],
  ["freshness", "old"],
  ["channels", {}],
  ["history", {}],
  ["capabilities", []],
])("rejects an invalid %s", (field, value) => {
  expect(() => assertDigitalTwinSnapshot({ ...snapshot(), [field]: value })).toThrow(field);
});

it("isDigitalTwinSnapshot returns false rather than throwing for invalid values", () => {
  expect(isDigitalTwinSnapshot(null)).toBe(false);
  expect(isDigitalTwinSnapshot({ schemaVersion: "2.0" })).toBe(false);
});
