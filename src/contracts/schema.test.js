import { readFileSync } from "node:fs";
import Ajv from "ajv";
import { describe, expect, it } from "vitest";

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const clone = (value) => JSON.parse(JSON.stringify(value));

const schemas = [
  json("../../contracts/v1/telemetry-sample.schema.json"),
  json("../../contracts/v1/detection-assessment.schema.json"),
  json("../../contracts/v1/twin-snapshot.schema.json"),
];

const validators = () => {
  const ajv = new Ajv({ allErrors: true, strict: true });
  schemas.forEach((schema) => ajv.addSchema(schema));
  return {
    telemetry: ajv.getSchema("forzy://contracts/v1/telemetry-sample"),
    detection: ajv.getSchema("forzy://contracts/v1/detection-assessment"),
    snapshot: ajv.getSchema("forzy://contracts/v1/twin-snapshot"),
  };
};

describe("contracts/v1", () => {
  it("compiles the three registered schemas", () => {
    const compiled = validators();
    expect(compiled.telemetry).toBeTypeOf("function");
    expect(compiled.detection).toBeTypeOf("function");
    expect(compiled.snapshot).toBeTypeOf("function");
  });

  it("accepts canonical live telemetry and rejects numeric strings", () => {
    const { telemetry } = validators();
    expect(telemetry(json("../../contracts/v1/fixtures/telemetry-live-s1.valid.json"))).toBe(true);
    expect(telemetry(json("../../contracts/v1/fixtures/telemetry-string.invalid.json"))).toBe(false);
  });

  it("rejects a live sample with an observed timestamp or ambiguous vibration", () => {
    const { telemetry } = validators();
    const observedLive = clone(json("../../contracts/v1/fixtures/telemetry-live-s1.valid.json"));
    observedLive.observedAt = "2026-08-12T15:00:00.000Z";
    const ambiguousLive = clone(json("../../contracts/v1/fixtures/telemetry-live-s1.valid.json"));
    ambiguousLive.measurements.vibration = 2.1;

    expect(telemetry(observedLive)).toBe(false);
    expect(telemetry(ambiguousLive)).toBe(false);
  });

  it("accepts the replay fixture and rejects an arbitrary snapshot assessment", () => {
    const { snapshot } = validators();
    const arbitraryAssessment = clone(json("../../contracts/v1/fixtures/twin-snapshot-live.valid.json"));
    arbitraryAssessment.assessment = {};

    expect(snapshot(json("../../contracts/v1/fixtures/twin-snapshot-replay.valid.json"))).toBe(true);
    expect(snapshot(arbitraryAssessment)).toBe(false);
  });

  it("requires exactly one s1 and one s2 channel for live snapshots", () => {
    const { snapshot } = validators();
    const live = json("../../contracts/v1/fixtures/twin-snapshot-live.valid.json");
    const missingS2 = clone(live);
    missingS2.channels = [missingS2.channels[0]];
    const duplicateS1 = clone(live);
    duplicateS1.channels[1] = { ...duplicateS1.channels[0], sampleId: "00000000-0000-4000-8000-000000000003" };
    const embeddedObservedLive = clone(live);
    embeddedObservedLive.channels[0].observedAt = "2026-08-12T15:00:00.000Z";

    expect(snapshot(live)).toBe(true);
    expect(snapshot(missingS2)).toBe(false);
    expect(snapshot(duplicateS1)).toBe(false);
    expect(snapshot(embeddedObservedLive)).toBe(false);
  });
});
