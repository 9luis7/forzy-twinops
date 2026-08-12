import { expect, it } from "vitest";
import { assertDigitalTwinSnapshot, isDigitalTwinSnapshot, SCHEMA_VERSION } from "./twin.js";

const timestamp = "2026-08-12T15:00:00.000Z";
const uuid = (suffix) => `00000000-0000-4000-8000-${suffix.padStart(12, "0")}`;
const frame = (sensorId) => ({
  schemaVersion: "1.0",
  frameId: uuid(sensorId === "s1" ? "1" : "2"),
  assetTag: "MTR-BMB-042",
  sensorId,
  sourceMode: "live",
  observedAt: timestamp,
  receivedAt: timestamp,
  timestampQuality: "source",
  measurements: {
    vibrationVelocityRms: { value: 2.1, unit: "mm/s", semanticConfidence: "confirmed" },
    vibrationAcceleration: { value: 0.3, unit: "g", statistic: "unknown", semanticConfidence: "confirmed" },
    temperature: { value: 34, unit: "degC", semanticConfidence: "confirmed" },
  },
  qualityFlags: [],
});

const assessment = () => ({
  schemaVersion: "1.0",
  assessmentId: uuid("3"),
  assetTag: "MTR-BMB-042",
  sensorId: "s1",
  window: { start: timestamp, end: timestamp, receivedAt: timestamp, freshnessMs: 0 },
  quality: { status: "ok", flags: [] },
  operatingContext: { state: "steady", estimated: false },
  assessment: {
    status: "normal",
    anomalyScore: 0.1,
    deteriorationScore: 0.2,
    scoreSemantics: "relative_to_historical_baseline_not_failure_probability",
    episodeId: null,
    persistenceSeconds: 0,
  },
  componentTag: null,
  recommendation: null,
  humanValidationRequired: false,
  evidence: [],
  model: { name: "model", version: "1", configHash: `sha256:${"0".repeat(64)}`, trainedUntil: timestamp },
  limitations: [],
});

const snapshot = () => ({
  schemaVersion: "1.0",
  assetTag: "MTR-BMB-042",
  mode: "live",
  generatedAt: timestamp,
  status: "normal",
  freshness: "fresh",
  channels: [frame("s1"), frame("s2")],
  history: [],
  assessment: assessment(),
  capabilities: { replayControls: false, liveUpdates: true, copilot: false, twin3d: true },
});

it("exports the current schema version", () => {
  expect(SCHEMA_VERSION).toBe("1.0");
});

it("accepts a complete v1 DigitalTwinSnapshot and returns the same value", () => {
  const value = snapshot();
  expect(assertDigitalTwinSnapshot(value)).toBe(value);
  expect(isDigitalTwinSnapshot(value)).toBe(true);
});

it.each([
  ["schemaVersion", "2.0"],
  ["generatedAt", undefined],
  ["mode", "offline"],
  ["status", "broken"],
  ["freshness", "old"],
  ["capabilities", { replayControls: false, liveUpdates: true, copilot: false }],
])("rejects a snapshot with invalid %s", (field, value) => {
  const candidate = snapshot();
  if (value === undefined) delete candidate[field];
  else candidate[field] = value;
  expect(() => assertDigitalTwinSnapshot(candidate)).toThrow(/DigitalTwinSnapshot/);
});

it("rejects live snapshots that do not contain exactly s1 and s2 channels", () => {
  const candidate = snapshot();
  candidate.channels = [frame("s1")];
  expect(() => assertDigitalTwinSnapshot(candidate)).toThrow(/channels/);
});

it("rejects a channel missing required telemetry-frame fields", () => {
  const candidate = snapshot();
  delete candidate.channels[0].measurements.temperature;
  expect(() => assertDigitalTwinSnapshot(candidate)).toThrow(/channels\[0\].measurements/);
});

it("rejects ambiguous legacy vibration measurements", () => {
  const candidate = snapshot();
  candidate.channels[0].measurements.vibration = 2.1;
  expect(() => assertDigitalTwinSnapshot(candidate)).toThrow(/channels\[0\].measurements/);
});

it("rejects an assessment with invalid numeric, quality, model, or evidence data", () => {
  const candidate = snapshot();
  candidate.assessment.assessment.anomalyScore = "0.1";
  expect(() => assertDigitalTwinSnapshot(candidate)).toThrow(/assessment.assessment.anomalyScore/);

  candidate.assessment.assessment.anomalyScore = 0.1;
  candidate.assessment.quality = { status: "ok" };
  expect(() => assertDigitalTwinSnapshot(candidate)).toThrow(/assessment.quality/);

  candidate.assessment.quality = { status: "ok", flags: [] };
  candidate.assessment.model.configHash = "unknown";
  expect(() => assertDigitalTwinSnapshot(candidate)).toThrow(/assessment.model.configHash/);

  candidate.assessment.model.configHash = `sha256:${"0".repeat(64)}`;
  candidate.assessment.evidence = [{ unsupported: true }];
  expect(() => assertDigitalTwinSnapshot(candidate)).toThrow(/assessment.evidence\[0\]/);
});

it("accepts typed assessment evidence and rejects non-finite evidence values", () => {
  const candidate = snapshot();
  candidate.assessment.evidence = [{
    id: "ev-1", feature: "velocity_rms_ewma", value: 0.08, unit: "mm/s",
    baseline: null, deviation: 0.04, direction: "up", windowSeconds: 300,
  }];
  expect(assertDigitalTwinSnapshot(candidate)).toBe(candidate);
  candidate.assessment.evidence[0].value = Number.NaN;
  expect(() => assertDigitalTwinSnapshot(candidate)).toThrow(/evidence\[0\].value/);
});

it("isDigitalTwinSnapshot returns false rather than throwing for invalid values", () => {
  expect(isDigitalTwinSnapshot(null)).toBe(false);
  expect(isDigitalTwinSnapshot({ schemaVersion: "2.0" })).toBe(false);
});
