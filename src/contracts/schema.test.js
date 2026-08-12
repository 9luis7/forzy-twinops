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
    expect(canonical(json("../../contracts/v1/fixtures/canonical-sensor-reading-csv-s1.valid.json"))).toBe(true);
    expect(canonical(json("../../contracts/v1/fixtures/canonical-sensor-reading-string.invalid.json"))).toBe(false);
  });

  it("accepts a fully typed assessment evidence item and rejects unknown evidence fields", () => {
    const { assessment } = validators();
    expect(assessment(json("../../contracts/v1/fixtures/asset-condition-assessment-evidence.valid.json"))).toBe(true);
    const candidate = {
      schemaVersion: "1.0", assessmentId: "00000000-0000-4000-8000-000000000003",
      assetTag: "MTR-BMB-042", sensorId: "s1",
      window: { start: "2026-08-12T15:00:00.000Z", end: "2026-08-12T15:00:01.000Z", receivedAt: "2026-08-12T15:00:01.000Z", freshnessMs: 0 },
      quality: { status: "ok", flags: [] }, operatingContext: { state: "steady", estimated: true },
      assessment: { status: "watch", anomalyScore: 0.5, deteriorationScore: 0.2, scoreSemantics: "relative_to_historical_baseline_not_failure_probability", episodeId: null, persistenceSeconds: 0 },
      componentTag: null, recommendation: null, humanValidationRequired: true,
      evidence: [{ id: "ev-1", feature: "velocity_rms_ewma", value: 0.08, unit: "mm/s", baseline: 0.04, deviation: null, direction: "up", windowSeconds: 300 }],
      model: { name: "robust-baseline", version: "1.0.0", configHash: `sha256:${"0".repeat(64)}`, trainedUntil: "2026-08-12T15:00:00.000Z" }, limitations: [],
    };
    expect(assessment(candidate)).toBe(true);
    candidate.evidence[0].extra = true;
    expect(assessment(candidate)).toBe(false);
  });

  it("accepts consumer-safe legacy acceleration in m/s²", () => {
    const { frame } = validators();
    const candidate = clone(json("../../contracts/v1/fixtures/digital-twin-snapshot-live.valid.json").channels[0]);
    candidate.measurements.vibrationAcceleration = { value: 2.1, unit: "m/s²", statistic: "unknown", semanticConfidence: "unconfirmed" };
    expect(frame(candidate)).toBe(true);
  });

  it("rejects a canonical reading with ambiguous vibration", () => {
    const { canonical } = validators();
    const ambiguousLive = clone(json("../../contracts/v1/fixtures/canonical-sensor-reading-live-s1.valid.json"));
    ambiguousLive.measurements.vibration = 2.1;

    expect(canonical(ambiguousLive)).toBe(false);
  });

  it("enforces live and CSV scheduling provenance semantics", () => {
    const { canonical } = validators();
    const invalidLive = clone(json("../../contracts/v1/fixtures/canonical-sensor-reading-live-s1.valid.json"));
    invalidLive.provenance.sourceSystem = "forzy-live";
    const invalidCsv = clone(json("../../contracts/v1/fixtures/canonical-sensor-reading-csv-s1.valid.json"));
    invalidCsv.scheduledAt = "2026-08-12T15:00:00.000Z";
    expect(canonical(invalidLive)).toBe(false);
    expect(canonical(invalidCsv)).toBe(false);
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
