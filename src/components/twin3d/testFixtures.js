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
  assessment: {
    schemaVersion: "1.0",
    assessmentId: "22222222-2222-4222-8222-222222222222",
    assetTag: "MTR-BMB-042",
    sensorId: "s1",
    window: {
      start: "2026-08-12T14:55:00.000Z",
      end: "2026-08-12T15:00:00.000Z",
      receivedAt: "2026-08-12T15:00:00.080Z",
      freshnessMs: 80,
    },
    quality: { status: "ok", flags: [] },
    operatingContext: { state: "steady", estimated: true },
    assessment: {
      status: "alert",
      anomalyScore: 0.8,
      deteriorationScore: 0.7,
      scoreSemantics: "relative_to_historical_baseline_not_failure_probability",
      episodeId: "episode-001",
      persistenceSeconds: 60,
    },
    componentTag: "CMP-MOTOR-VALIDATED",
    recommendation: "Inspecionar o conjunto com validação humana.",
    humanValidationRequired: true,
    evidence: [],
    model: {
      name: "robust-baseline",
      version: "1.0.0",
      configHash: `sha256:${"0".repeat(64)}`,
      trainedUntil: "2026-08-11T23:59:59.000Z",
    },
    limitations: [],
  },
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
