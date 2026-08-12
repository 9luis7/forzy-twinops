const SCHEMA_VERSION = "1.0";
const DEMO_LIMITATION = "demo_scenario_not_model_inference";
const ZERO_HASH = `sha256:${"0".repeat(64)}`;

const statusByLegacyValue = {
  alerta: "alert",
  critico: "alert",
  desconhecido: "unknown",
};

const asNullable = (value) => (value === undefined ? null : value);

const timestamp = (value) => {
  if (typeof value === "number") return new Date(value).toISOString();
  return asNullable(value);
};

const sampleId = (index) =>
  `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`;

const toSnapshotStatus = (status) => statusByLegacyValue[status] ?? status ?? "unknown";

const toFrame = ({ assetTag, reading, index }) => {
  const observedAt = timestamp(reading?.ts);

  return {
    schemaVersion: SCHEMA_VERSION,
    frameId: sampleId(index),
    assetTag,
    sensorId: "s1",
    sourceMode: "replay",
    observedAt,
    receivedAt: null,
    timestampQuality: "synthetic",
    measurements: {
      vibrationVelocityRms: null,
      vibrationAcceleration: {
        value: asNullable(reading?.vibration),
        unit: "g",
        statistic: "unknown",
        semanticConfidence: "unconfirmed",
      },
      temperature: {
        value: asNullable(reading?.temperature),
        unit: "degC",
        semanticConfidence: "unconfirmed",
      },
    },
    qualityFlags: [],
  };
};

const toAssessment = ({ assetTag, timestamp: receivedAt, status, scenario, risk }) => {
  if (!scenario && !risk) return null;

  const score = asNullable(risk?.score);
  return {
    schemaVersion: SCHEMA_VERSION,
    assessmentId: "00000000-0000-4000-8000-000000000003",
    assetTag,
    sensorId: "s1",
    window: { start: receivedAt, end: receivedAt, receivedAt, freshnessMs: 0 },
    quality: { status: "ok", flags: [DEMO_LIMITATION] },
    operatingContext: { state: "unknown", estimated: true },
    assessment: {
      status: status === "unknown" ? "insufficient_data" : status,
      anomalyScore: score,
      deteriorationScore: score,
      scoreSemantics: "relative_to_historical_baseline_not_failure_probability",
      episodeId: scenario?.id ?? null,
      persistenceSeconds: 0,
    },
    componentTag: null,
    recommendation: null,
    humanValidationRequired: status === "alert",
    evidence: [],
    model: {
      name: "forzy-demo-scenario",
      version: "1.0",
      configHash: ZERO_HASH,
      trainedUntil: receivedAt,
    },
    limitations: [DEMO_LIMITATION],
  };
};

/**
 * Adapts deterministic legacy replay values to the frontend TwinSnapshot boundary.
 */
export function buildReplaySnapshot({ assetTag, live, reading, status, scenario, risk }) {
  const generatedAt = timestamp(reading?.ts);
  const history = (live?.points ?? []).map((point, index) =>
    toFrame({ assetTag, reading: point, index: index + 1 })
  );
  const snapshotStatus = toSnapshotStatus(status);

  return {
    schemaVersion: SCHEMA_VERSION,
    assetTag,
    mode: "replay",
    generatedAt,
    status: snapshotStatus,
    freshness: "expected_idle",
    channels: [toFrame({ assetTag, reading, index: 0 })],
    history,
    assessment: toAssessment({
      assetTag,
      timestamp: generatedAt,
      status: snapshotStatus,
      scenario,
      risk,
    }),
    capabilities: {
      replayControls: true,
      liveUpdates: false,
      copilot: false,
      twin3d: true,
    },
  };
}
