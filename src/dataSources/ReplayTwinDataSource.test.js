import { expect, it } from "vitest";
import { buildReplaySnapshot } from "./ReplayTwinDataSource.js";

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
  expect(snapshot.channels[0].receivedAt).toBe("2026-08-12T15:00:00.000Z");
  expect(snapshot.channels[0].measurements.vibrationAcceleration.value).toBe(2.1);
  expect(snapshot.channels[0].measurements.vibrationVelocityRms).toBeNull();
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
  expect(snapshot.channels[0].raw.current).toBeNull();
  expect(snapshot.channels[0].raw.rotation).toBeNull();
});
