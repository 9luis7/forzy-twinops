const measurements = {
  vibrationVelocityRms: { value: 0.04, unit: "mm/s", semanticConfidence: "inferred_from_datasheet" },
  vibrationAcceleration: { value: 0, unit: "g", statistic: "unknown", semanticConfidence: "unconfirmed" },
  temperature: { value: 34, unit: "degC", semanticConfidence: "inferred_from_datasheet" },
};

const channel = (sensorId) => ({
  schemaVersion: "1.0",
  frameId: `11111111-1111-4111-8111-11111111111${sensorId === "s1" ? "1" : "2"}`,
  assetTag: "MTR-BMB-042",
  sensorId,
  sourceMode: "replay",
  receivedAt: "2026-08-12T15:00:00.080Z",
  observedAt: null,
  timestampQuality: "synthetic",
  measurements,
  qualityFlags: [],
});

export const normalSnapshot = {
  schemaVersion: "1.0",
  assetTag: "MTR-BMB-042",
  mode: "replay",
  generatedAt: "2026-08-12T15:00:00.100Z",
  status: "normal",
  freshness: "fresh",
  channels: [channel("s1"), channel("s2")],
  history: [],
  assessment: null,
  capabilities: { replayControls: true, liveUpdates: false, copilot: false, twin3d: true },
};

export const liveSnapshot = {
  ...normalSnapshot,
  mode: "live",
  capabilities: { replayControls: false, liveUpdates: true, copilot: false, twin3d: true },
};

export const alertSnapshot = {
  ...normalSnapshot,
  status: "alert",
  assessment: { componentTag: "CMP-MOTOR-VALIDATED" },
};

export const manifestWithApprovedMotorBinding = {
  schemaVersion: "1.0",
  modelUrl: "/models/conjunto-motor-bomba.glb",
  sourceSha256: "a".repeat(64),
  units: "m",
  upAxis: "Y",
  groups: {
    motor: { nodeNames: ["ME22A_CORPO", "ME22A_EIXO"], componentTag: "CMP-MOTOR-VALIDATED" },
    pump: { nodeNames: ["BOMBA_CORPO"], componentTag: null },
    base: { nodeNames: ["BASE_01"], componentTag: null },
  },
  sensors: [
    { sensorId: "s1", placement: "unvalidated" },
    { sensorId: "s2", placement: "unvalidated" },
  ],
};
