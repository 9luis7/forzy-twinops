import { readFileSync } from "node:fs";
import Ajv from "ajv";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));

const validators = () => {
  const ajv = new Ajv({ allErrors: true, strict: true, schemas: [
    json("../../contracts/v2/canonical-sensor-reading.schema.json"),
    json("../../contracts/v2/sensor-telemetry-frame.schema.json"),
    json("../../contracts/v2/asset-condition-assessment.schema.json"),
  ] });
  addFormats(ajv);

  return {
    canonical: ajv.getSchema("forzy://contracts/v2/canonical-sensor-reading"),
    frame: ajv.getSchema("forzy://contracts/v2/sensor-telemetry-frame"),
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

  it("isolates the schema-enforceable Forzy source-time claims", () => {
    const { canonical } = validators();
    const valid = json("../../contracts/v2/fixtures/canonical-live-s1.valid.json");
    const wrongQuality = structuredClone(valid);
    wrongQuality.timestampQuality = "source";
    const sourceProvided = structuredClone(valid);
    sourceProvided.provenance.sourceTimestampProvided = true;

    expect(canonical(valid)).toBe(true);
    expect(canonical(wrongQuality)).toBe(false);
    expect(canonical(sourceProvided)).toBe(false);
    expect(canonical(json("../../contracts/v2/fixtures/canonical-source-time.invalid.json"))).toBe(false);
  });

  it.each([
    ["0000-01-01T00:00:00Z", true],
    ["2000-02-29T12:34:56Z", true],
    ["2024-12-31T23:59:60Z", true],
    ["2023-02-29T12:34:56Z", false],
    ["2024-12-31T12:34:60Z", false],
    ["2026-99-99T29:77:88Z", false],
  ])("validates the normative RFC 3339 UTC matrix for %s", (timestamp, expected) => {
    const { canonical } = validators();
    const reading = json("../../contracts/v2/fixtures/canonical-live-s1.valid.json");

    reading.scheduledAt = timestamp;
    expect(canonical(reading)).toBe(expected);
  });

  it("enforces frame timestamp nullability from timestampQuality", () => {
    const { frame } = validators();
    const assumed = json("../../contracts/v2/fixtures/snapshot-received-now.valid.json").channels[0];
    const assumedWithNull = structuredClone(assumed);
    assumedWithNull.observedAt = null;
    const unavailableWithTimestamps = structuredClone(assumed);
    unavailableWithTimestamps.timestampQuality = "unavailable";
    const unavailable = structuredClone(unavailableWithTimestamps);
    unavailable.observedAt = null;
    unavailable.receivedAt = null;

    expect(frame(assumed)).toBe(true);
    expect(frame(assumedWithNull)).toBe(false);
    expect(frame(unavailableWithTimestamps)).toBe(false);
    expect(frame(unavailable)).toBe(true);
  });

  it("leaves cross-property timestamp equality to semantic validators", () => {
    const { canonical, frame } = validators();
    const canonicalWithMismatch = json("../../contracts/v2/fixtures/canonical-live-s1.valid.json");
    canonicalWithMismatch.observedAt = "2026-08-12T15:00:00.000Z";
    const frameWithMismatch = json("../../contracts/v2/fixtures/snapshot-received-now.valid.json").channels[0];
    frameWithMismatch.observedAt = "2026-08-12T15:00:00.000Z";

    expect(canonical(canonicalWithMismatch)).toBe(true);
    expect(frame(frameWithMismatch)).toBe(true);
  });
});
