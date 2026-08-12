import { expect, it } from "vitest";
import { readFileSync } from "node:fs";
import Ajv from "ajv";
import { buildReplaySnapshot } from "./ReplayTwinDataSource.js";

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const replaySnapshotValidator = () => {
  const ajv = new Ajv({ strict: true });
  [
    json("../../contracts/v1/sensor-telemetry-frame.schema.json"),
    json("../../contracts/v1/asset-condition-assessment.schema.json"),
    json("../../contracts/v1/digital-twin-snapshot.schema.json"),
  ].forEach((schema) => ajv.addSchema(schema));
  return ajv.getSchema("forzy://contracts/v1/digital-twin-snapshot");
};

it("maps the legacy vibration acceleration without calling it RMS velocity", () => {
  const snapshot = buildReplaySnapshot({
    assetTag: "MTR-BMB-042",
    live: { points: [], running: true },
    reading: {
      ts: "2026-08-12T15:00:00.000Z",
      temperature: 34,
      vibration: 2.1,
      current: 17,
      rotation: 1760,
    },
    status: "normal",
    scenario: null,
    risk: { level: "Baixo", score: 12 },
  });

  expect(snapshot.mode).toBe("replay");
  expect(snapshot.generatedAt).toBe("2026-08-12T15:00:00.000Z");
  expect(snapshot.status).toBe("normal");
  expect(snapshot.channels[0].receivedAt).toBeNull();
  expect(snapshot.channels[0].sourceMode).toBe("replay");
  expect(snapshot.channels[0].timestampQuality).toBe("synthetic");
  expect(snapshot.channels[0].measurements.vibrationAcceleration.value).toBe(2.1);
  expect(snapshot.channels[0].measurements.vibrationVelocityRms).toBeNull();
});

it.each([
  ["normal", "normal"],
  ["alerta", "alert"],
  ["critico", "alert"],
  ["desconhecido", "unknown"],
])("maps legacy status %s to %s", (legacyStatus, expectedStatus) => {
  const snapshot = buildReplaySnapshot({
    assetTag: "MTR-BMB-042",
    live: { points: [], running: false },
    reading: { ts: 1_786_497_600_000, temperature: 34, vibration: 2.1 },
    status: legacyStatus,
    scenario: null,
    risk: null,
  });

  expect(snapshot.status).toBe(expectedStatus);
  expect(snapshot.generatedAt).toBe("2026-08-12T01:20:00.000Z");
  expect(snapshot.channels[0]).toMatchObject({
    observedAt: "2026-08-12T01:20:00.000Z",
    receivedAt: null,
    timestampQuality: "synthetic",
  });
});

it("produces a replay snapshot accepted by the separated Ajv contracts", () => {
  const snapshot = buildReplaySnapshot({
    assetTag: "MTR-BMB-042",
    live: { points: [], running: false },
    reading: { ts: "2026-08-12T15:00:00.000Z", temperature: 34, vibration: 2.1 },
    status: "normal",
    scenario: null,
    risk: null,
  });

  expect(replaySnapshotValidator()(snapshot)).toBe(true);
});

it("marks alert replay assessments as demo scenarios instead of model inference", () => {
  const snapshot = buildReplaySnapshot({
    assetTag: "MTR-BMB-042",
    live: { points: [], running: false },
    reading: {
      ts: "2026-08-12T15:00:00.000Z",
      temperature: 81,
      vibration: 7.8,
      current: 17,
      rotation: 1720,
    },
    status: "alert",
    scenario: { id: "imbalance", name: "Desbalanceamento" },
    risk: { level: "Alto", score: 86 },
  });

  expect(snapshot.status).toBe("alert");
  expect(snapshot.capabilities.replayControls).toBe(true);
  expect(snapshot.assessment.assessment.scoreSemantics).toBe(
    "relative_to_historical_baseline_not_failure_probability"
  );
  expect(snapshot.assessment.limitations).toContain("demo_scenario_not_model_inference");
});

it("does not emit an assessment for a normal replay without a finite risk score", () => {
  const snapshot = buildReplaySnapshot({
    assetTag: "MTR-BMB-042",
    live: { points: [], running: false },
    reading: { ts: "2026-08-12T15:00:00.000Z", temperature: 34, vibration: 2.1 },
    status: "normal",
    scenario: null,
    risk: null,
  });

  expect(snapshot.assessment).toBeNull();
  expect(replaySnapshotValidator()(snapshot)).toBe(true);
});

it("does not invent an assessment when a scenario has no finite risk score", () => {
  const snapshot = buildReplaySnapshot({
    assetTag: "MTR-BMB-042",
    live: { points: [], running: false },
    reading: { ts: "2026-08-12T15:00:00.000Z", temperature: 81, vibration: 7.8 },
    status: "alerta",
    scenario: { id: "imbalance" },
    risk: { level: "Alto" },
  });

  expect(snapshot.status).toBe("alert");
  expect(snapshot.assessment).toBeNull();
  expect(replaySnapshotValidator()(snapshot)).toBe(true);
});

it("does not emit an assessment for a non-finite risk score", () => {
  const snapshot = buildReplaySnapshot({
    assetTag: "MTR-BMB-042",
    live: { points: [], running: false },
    reading: { ts: "2026-08-12T15:00:00.000Z", temperature: 81, vibration: 7.8 },
    status: "alerta",
    scenario: { id: "imbalance" },
    risk: { level: "Alto", score: Number.NaN },
  });

  expect(snapshot.status).toBe("alert");
  expect(snapshot.assessment).toBeNull();
  expect(replaySnapshotValidator()(snapshot)).toBe(true);
});

it("preserves missing legacy readings as null", () => {
  const snapshot = buildReplaySnapshot({
    assetTag: "MTR-BMB-042",
    live: { points: [], running: false },
    reading: { ts: "2026-08-12T15:00:00.000Z" },
    status: "unknown",
    scenario: null,
    risk: null,
  });

  expect(snapshot.channels[0].measurements).toMatchObject({
    vibrationAcceleration: { value: null },
    temperature: { value: null },
  });
  expect(snapshot.channels[0]).not.toHaveProperty("raw");
});
