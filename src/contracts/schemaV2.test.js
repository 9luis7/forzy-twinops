import { readFileSync } from "node:fs";
import Ajv from "ajv";
import { describe, expect, it } from "vitest";

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));

const validators = () => {
  const ajv = new Ajv({ allErrors: true, strict: true, schemas: [
    json("../../contracts/v2/canonical-sensor-reading.schema.json"),
    json("../../contracts/v2/sensor-telemetry-frame.schema.json"),
    json("../../contracts/v2/asset-condition-assessment.schema.json"),
  ] });

  return {
    canonical: ajv.getSchema("forzy://contracts/v2/canonical-sensor-reading"),
    snapshot: ajv.compile(json("../../contracts/v2/digital-twin-snapshot.schema.json")),
  };
};

describe("contracts/v2", () => {
  it("accepts v2 and rejects the invented assetTag boundary", () => {
    const { snapshot } = validators();

    expect(snapshot(json("../../contracts/v2/fixtures/snapshot-received-now.valid.json"))).toBe(true);
    expect(snapshot(json("../../contracts/v2/fixtures/snapshot-last-known.valid.json"))).toBe(true);
    expect(snapshot(json("../../contracts/v2/fixtures/snapshot-asset-tag.invalid.json"))).toBe(false);
  });

  it("rejects a Forzy live reading that claims a source timestamp", () => {
    const { canonical } = validators();

    expect(canonical(json("../../contracts/v2/fixtures/canonical-live-s1.valid.json"))).toBe(true);
    expect(canonical(json("../../contracts/v2/fixtures/canonical-source-time.invalid.json"))).toBe(false);
  });
});
