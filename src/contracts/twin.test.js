import { expect, it } from "vitest";
import { assertTwinSnapshot, isTwinSnapshot, SCHEMA_VERSION } from "./twin.js";

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
  expect(() => assertTwinSnapshot({ schemaVersion: "2.0" })).toThrow(/schemaVersion/);
});

it("accepts the public snapshot boundary and returns the same value", () => {
  const value = snapshot();
  expect(assertTwinSnapshot(value)).toBe(value);
  expect(isTwinSnapshot(value)).toBe(true);
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
  expect(() => assertTwinSnapshot({ ...snapshot(), [field]: value })).toThrow(field);
});

it("isTwinSnapshot returns false rather than throwing for invalid values", () => {
  expect(isTwinSnapshot(null)).toBe(false);
  expect(isTwinSnapshot({ schemaVersion: "2.0" })).toBe(false);
});
