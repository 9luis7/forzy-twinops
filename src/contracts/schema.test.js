import { readFileSync } from "node:fs";
import Ajv from "ajv";
import { describe, expect, it } from "vitest";

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const clone = (value) => JSON.parse(JSON.stringify(value));

const schemas = [
  json("../../contracts/v1/canonical-sensor-reading.schema.json"),
  json("../../contracts/v1/sensor-telemetry-frame.schema.json"),
  json("../../contracts/v1/asset-condition-assessment.schema.json"),
  json("../../contracts/v1/digital-twin-snapshot.schema.json"),
];

const validators = () => {
  const ajv = new Ajv({ allErrors: true, strict: true });
  schemas.forEach((schema) => ajv.addSchema(schema));
  return {
    canonical: ajv.getSchema("forzy://contracts/v1/canonical-sensor-reading"),
    frame: ajv.getSchema("forzy://contracts/v1/sensor-telemetry-frame"),
    assessment: ajv.getSchema("forzy://contracts/v1/asset-condition-assessment"),
    snapshot: ajv.getSchema("forzy://contracts/v1/digital-twin-snapshot"),
  };
};

describe("contracts/v1", () => {
  it("compiles the four separated registered schemas", () => {
    const compiled = validators();
    expect(compiled.canonical).toBeTypeOf("function");
    expect(compiled.frame).toBeTypeOf("function");
    expect(compiled.assessment).toBeTypeOf("function");
    expect(compiled.snapshot).toBeTypeOf("function");
  });

  it("accepts immutable canonical readings and rejects numeric strings", () => {
    const { canonical } = validators();
    expect(canonical(json("../../contracts/v1/fixtures/canonical-sensor-reading-live-s1.valid.json"))).toBe(true);
    expect(canonical(json("../../contracts/v1/fixtures/canonical-sensor-reading-string.invalid.json"))).toBe(false);
  });

  it("rejects a canonical reading with ambiguous vibration", () => {
    const { canonical } = validators();
    const ambiguousLive = clone(json("../../contracts/v1/fixtures/canonical-sensor-reading-live-s1.valid.json"));
    ambiguousLive.measurements.vibration = 2.1;

    expect(canonical(ambiguousLive)).toBe(false);
  });

  it("accepts the replay fixture and rejects an arbitrary snapshot assessment", () => {
    const { snapshot } = validators();
    const arbitraryAssessment = clone(json("../../contracts/v1/fixtures/digital-twin-snapshot-live.valid.json"));
    arbitraryAssessment.assessment = {};

    expect(snapshot(json("../../contracts/v1/fixtures/digital-twin-snapshot-replay.valid.json"))).toBe(true);
    expect(snapshot(arbitraryAssessment)).toBe(false);
  });

  it("requires exactly one s1 and one s2 frame for live snapshots", () => {
    const { snapshot } = validators();
    const live = json("../../contracts/v1/fixtures/digital-twin-snapshot-live.valid.json");
    const missingS2 = clone(live);
    missingS2.channels = [missingS2.channels[0]];
    const duplicateS1 = clone(live);
    duplicateS1.channels[1] = {
      ...duplicateS1.channels[0],
      frameId: "00000000-0000-4000-8000-000000000003",
      sensorId: "s1",
    };
    const embeddedObservedLive = clone(live);

    expect(snapshot(live)).toBe(true);
    expect(snapshot(missingS2)).toBe(false);
    expect(snapshot(duplicateS1)).toBe(false);
    expect(snapshot(embeddedObservedLive)).toBe(true);
  });
});
