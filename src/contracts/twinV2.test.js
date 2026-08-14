import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  SCHEMA_VERSION_V2,
  assertDigitalTwinSnapshotV2,
  isDigitalTwinSnapshotV2,
} from "./twinV2.js";

const fixture = (name = "snapshot-received-now.valid.json") =>
  JSON.parse(readFileSync(new URL(`../../contracts/v2/fixtures/${name}`, import.meta.url), "utf8"));

const validAssessment = (timestamp) => ({
  schemaVersion: "2.0",
  assessmentId: "00000000-0000-4000-8000-000000000003",
  assetId: "forzy-motor-01",
  sensorId: "s1",
  window: { start: timestamp, end: timestamp, receivedAt: timestamp, freshnessMs: 0 },
  quality: { status: "ok", flags: [] },
  operatingContext: { state: "steady", estimated: true },
  assessment: {
    status: "normal",
    anomalyScore: 0,
    deteriorationScore: 0,
    scoreSemantics: "relative_to_historical_baseline_not_failure_probability",
    episodeId: null,
    persistenceSeconds: 0,
  },
  componentTag: null,
  recommendation: null,
  humanValidationRequired: true,
  evidence: [],
  model: {
    name: "robust-baseline",
    version: "1.0.0",
    configHash: `sha256:${"0".repeat(64)}`,
    trainedUntil: timestamp,
  },
  limitations: [],
});

const validEvidence = () => ({
  id: "ev-1",
  feature: "temperature",
  value: 0,
  unit: "degC",
});

describe("DigitalTwinSnapshot v2 runtime contract", () => {
  it("accepts both valid fixtures that the JSON schema accepts", () => {
    expect(SCHEMA_VERSION_V2).toBe("2.0");
    expect(isDigitalTwinSnapshotV2(fixture())).toBe(true);
    expect(isDigitalTwinSnapshotV2(fixture("snapshot-last-known.valid.json"))).toBe(true);
  });

  it("rejects a plausible snapshot with a source timestamp claim", () => {
    const value = fixture();
    value.channels[0].timestampQuality = "source";

    expect(() => assertDigitalTwinSnapshotV2(value)).toThrow(/timestampQuality/);
  });

  it("rejects a non-finite measurement while preserving zero as valid", () => {
    const zero = fixture();
    expect(() => assertDigitalTwinSnapshotV2(zero)).not.toThrow();

    const value = fixture();
    value.channels[0].measurements.vibrationAcceleration.value = Number.NaN;
    expect(() => assertDigitalTwinSnapshotV2(value)).toThrow(/value/);
  });

  it("rejects a numeric string measurement", () => {
    const value = fixture();
    value.channels[0].measurements.vibrationAcceleration.value = "0";

    expect(() => assertDigitalTwinSnapshotV2(value)).toThrow(/value/);
  });

  it("rejects invalid calendar timestamps and incoherent frame timestamps", () => {
    const impossible = fixture();
    impossible.generatedAt = "2026-99-99T29:77:88Z";
    expect(() => assertDigitalTwinSnapshotV2(impossible)).toThrow(/generatedAt/);

    const nonLeapDay = fixture();
    nonLeapDay.generatedAt = "2023-02-29T12:34:56Z";
    expect(() => assertDigitalTwinSnapshotV2(nonLeapDay)).toThrow(/generatedAt/);

    const incoherent = fixture();
    incoherent.channels[0].receivedAt = "2026-08-12T15:00:02.000Z";
    expect(() => assertDigitalTwinSnapshotV2(incoherent)).toThrow(/observedAt/);
  });

  it("enforces timestamp nullability from frame timestampQuality", () => {
    const assumedWithNull = fixture();
    assumedWithNull.channels[0].observedAt = null;
    expect(() => assertDigitalTwinSnapshotV2(assumedWithNull)).toThrow(/observedAt/);

    const unavailableWithTimestamps = fixture();
    unavailableWithTimestamps.channels[0].timestampQuality = "unavailable";
    expect(() => assertDigitalTwinSnapshotV2(unavailableWithTimestamps)).toThrow(/timestampQuality/);

    const unavailable = fixture();
    unavailable.channels[0].timestampQuality = "unavailable";
    unavailable.channels[0].observedAt = null;
    unavailable.channels[0].receivedAt = null;
    expect(() => assertDigitalTwinSnapshotV2(unavailable)).not.toThrow();
  });

  it("accepts the leap-second and year-zero timestamp boundaries accepted by the schema", () => {
    const leapSecond = fixture();
    leapSecond.generatedAt = "2024-12-31T23:59:60Z";
    expect(() => assertDigitalTwinSnapshotV2(leapSecond)).not.toThrow();

    const yearZero = fixture();
    yearZero.generatedAt = "0000-01-01T00:00:00Z";
    expect(() => assertDigitalTwinSnapshotV2(yearZero)).not.toThrow();

    const gregorianLeapDay = fixture();
    gregorianLeapDay.generatedAt = "2000-02-29T12:34:56Z";
    expect(() => assertDigitalTwinSnapshotV2(gregorianLeapDay)).not.toThrow();
  });

  it("rejects a leap second outside 23:59 UTC", () => {
    const value = fixture();
    value.generatedAt = "2024-12-31T12:34:60Z";

    expect(() => assertDigitalTwinSnapshotV2(value)).toThrow(/generatedAt/);
  });

  it("rejects extra fields, duplicate channels, incomplete health, and altered capabilities", () => {
    const extra = fixture();
    extra.asset.assetTag = "invented";
    expect(() => assertDigitalTwinSnapshotV2(extra)).toThrow(/asset/);

    const duplicate = fixture();
    duplicate.channels[1].sensorId = "s1";
    expect(() => assertDigitalTwinSnapshotV2(duplicate)).toThrow(/channels/);

    const health = fixture();
    delete health.integration.sensors.s2;
    expect(() => assertDigitalTwinSnapshotV2(health)).toThrow(/sensors/);

    const capability = fixture();
    capability.capabilities.replayControls = true;
    expect(() => assertDigitalTwinSnapshotV2(capability)).toThrow(/replayControls/);
  });

  it("rejects the shared assetTag fixture", () => {
    expect(() => assertDigitalTwinSnapshotV2(fixture("snapshot-asset-tag.invalid.json"))).toThrow();
  });

  it("requires assessment and validates its object form", () => {
    const missing = fixture();
    delete missing.assessment;
    expect(() => assertDigitalTwinSnapshotV2(missing)).toThrow(/assessment/);

    const invalid = fixture();
    invalid.assessment = {};
    expect(() => assertDigitalTwinSnapshotV2(invalid)).toThrow(/assessment/);

    const valid = fixture();
    valid.assessment = validAssessment(valid.generatedAt);
    expect(() => assertDigitalTwinSnapshotV2(valid)).not.toThrow();
  });

  it("rejects an invalid nested assessment evidence value", () => {
    const value = fixture();
    value.assessment = validAssessment(value.generatedAt);
    value.assessment.evidence = [{ ...validEvidence(), value: "0" }];

    expect(() => assertDigitalTwinSnapshotV2(value)).toThrow(/evidence.*value/);
  });

  it("rejects an invalid optional assessment evidence value", () => {
    const value = fixture();
    value.assessment = validAssessment(value.generatedAt);
    value.assessment.evidence = [{ ...validEvidence(), baseline: "0" }];

    expect(() => assertDigitalTwinSnapshotV2(value)).toThrow(/baseline/);
  });
});
