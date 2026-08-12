export const SCHEMA_VERSION = "1.0";

const MODES = new Set(["replay", "live"]);
const STATUSES = new Set(["normal", "watch", "alert", "unknown", "insufficient_data"]);
const FRESHNESS_VALUES = new Set(["fresh", "delayed", "expected_idle", "unavailable", "unknown"]);
const TIMESTAMP_QUALITY = new Set(["source", "collector", "synthetic", "unknown"]);
const SOURCE_MODES = new Set(["replay", "live", "historical"]);
const CONFIDENCE = new Set(["confirmed", "inferred_from_datasheet", "unconfirmed"]);
const ASSESSMENT_STATUS = new Set(["normal", "watch", "alert", "insufficient_data"]);
const QUALITY_STATUS = new Set(["ok", "degraded", "insufficient_data"]);
const OPERATING_STATES = new Set(["steady", "startup", "shutdown", "stopped", "unknown"]);
const EVIDENCE_DIRECTIONS = new Set(["up", "down", "stable", "unknown"]);
const TIMESTAMP = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const HASH = /^sha256:[0-9a-f]{64}$/;

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const invalid = (field) => {
  throw new TypeError(`Invalid DigitalTwinSnapshot ${field}`);
};
const requiredObject = (value, field, keys) => {
  if (!isObject(value)) invalid(field);
  const actual = Object.keys(value);
  if (actual.length !== keys.length || actual.some((key) => !keys.includes(key))) invalid(field);
  for (const key of keys) if (!(key in value)) invalid(`${field}.${key}`);
};
const string = (value, field) => {
  if (typeof value !== "string" || value.length === 0) invalid(field);
};
const nullableString = (value, field) => {
  if (value !== null) string(value, field);
};
const finiteNumber = (value, field) => {
  if (!Number.isFinite(value)) invalid(field);
};
const stringArray = (value, field) => {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) invalid(field);
};
const timestamp = (value, field, nullable = false) => {
  if (nullable && value === null) return;
  if (typeof value !== "string" || !TIMESTAMP.test(value)) invalid(field);
};
const identifier = (value, field) => {
  if (typeof value !== "string" || !UUID.test(value)) invalid(field);
};

const assertMeasurement = (value, field, unit, extra = {}) => {
  if (value === null) return;
  requiredObject(value, field, ["value", "unit", ...Object.keys(extra), "semanticConfidence"]);
  if (value.value !== null) finiteNumber(value.value, `${field}.value`);
  if (!(Array.isArray(unit) ? unit.includes(value.unit) : value.unit === unit)) invalid(`${field}.unit`);
  if (!CONFIDENCE.has(value.semanticConfidence)) invalid(`${field}.semanticConfidence`);
  for (const [key, expected] of Object.entries(extra)) if (value[key] !== expected) invalid(`${field}.${key}`);
};

const assertFrame = (value, field) => {
  requiredObject(value, field, [
    "schemaVersion", "frameId", "assetTag", "sensorId", "sourceMode", "observedAt", "receivedAt",
    "timestampQuality", "measurements", "qualityFlags",
  ]);
  if (value.schemaVersion !== SCHEMA_VERSION) invalid(`${field}.schemaVersion`);
  identifier(value.frameId, `${field}.frameId`);
  string(value.assetTag, `${field}.assetTag`);
  if (value.sensorId !== "s1" && value.sensorId !== "s2") invalid(`${field}.sensorId`);
  if (!SOURCE_MODES.has(value.sourceMode)) invalid(`${field}.sourceMode`);
  timestamp(value.observedAt, `${field}.observedAt`, true);
  timestamp(value.receivedAt, `${field}.receivedAt`, true);
  if (!TIMESTAMP_QUALITY.has(value.timestampQuality)) invalid(`${field}.timestampQuality`);
  requiredObject(value.measurements, `${field}.measurements`, [
    "vibrationVelocityRms", "vibrationAcceleration", "temperature",
  ]);
  assertMeasurement(value.measurements.vibrationVelocityRms, `${field}.measurements.vibrationVelocityRms`, "mm/s");
  assertMeasurement(
    value.measurements.vibrationAcceleration,
    `${field}.measurements.vibrationAcceleration`,
    ["g", "m/s²"],
    { statistic: "unknown" }
  );
  assertMeasurement(value.measurements.temperature, `${field}.measurements.temperature`, "degC");
  stringArray(value.qualityFlags, `${field}.qualityFlags`);
};

const assertAssessment = (value) => {
  if (value === null) return;
  const field = "assessment";
  requiredObject(value, field, [
    "schemaVersion", "assessmentId", "assetTag", "sensorId", "window", "quality", "operatingContext",
    "assessment", "componentTag", "recommendation", "humanValidationRequired", "evidence", "model", "limitations",
  ]);
  if (value.schemaVersion !== SCHEMA_VERSION) invalid(`${field}.schemaVersion`);
  identifier(value.assessmentId, `${field}.assessmentId`);
  string(value.assetTag, `${field}.assetTag`);
  if (value.sensorId !== "s1" && value.sensorId !== "s2") invalid(`${field}.sensorId`);
  requiredObject(value.window, `${field}.window`, ["start", "end", "receivedAt", "freshnessMs"]);
  timestamp(value.window.start, `${field}.window.start`);
  timestamp(value.window.end, `${field}.window.end`);
  timestamp(value.window.receivedAt, `${field}.window.receivedAt`);
  finiteNumber(value.window.freshnessMs, `${field}.window.freshnessMs`);
  if (value.window.freshnessMs < 0) invalid(`${field}.window.freshnessMs`);
  requiredObject(value.quality, `${field}.quality`, ["status", "flags"]);
  if (!QUALITY_STATUS.has(value.quality.status)) invalid(`${field}.quality.status`);
  stringArray(value.quality.flags, `${field}.quality.flags`);
  requiredObject(value.operatingContext, `${field}.operatingContext`, ["state", "estimated"]);
  if (!OPERATING_STATES.has(value.operatingContext.state)) invalid(`${field}.operatingContext.state`);
  if (typeof value.operatingContext.estimated !== "boolean") invalid(`${field}.operatingContext.estimated`);
  requiredObject(value.assessment, `${field}.assessment`, [
    "status", "anomalyScore", "deteriorationScore", "scoreSemantics", "episodeId", "persistenceSeconds",
  ]);
  if (!ASSESSMENT_STATUS.has(value.assessment.status)) invalid(`${field}.assessment.status`);
  finiteNumber(value.assessment.anomalyScore, `${field}.assessment.anomalyScore`);
  finiteNumber(value.assessment.deteriorationScore, `${field}.assessment.deteriorationScore`);
  if (value.assessment.scoreSemantics !== "relative_to_historical_baseline_not_failure_probability") {
    invalid(`${field}.assessment.scoreSemantics`);
  }
  nullableString(value.assessment.episodeId, `${field}.assessment.episodeId`);
  finiteNumber(value.assessment.persistenceSeconds, `${field}.assessment.persistenceSeconds`);
  if (value.assessment.persistenceSeconds < 0) invalid(`${field}.assessment.persistenceSeconds`);
  nullableString(value.componentTag, `${field}.componentTag`);
  nullableString(value.recommendation, `${field}.recommendation`);
  if (typeof value.humanValidationRequired !== "boolean") invalid(`${field}.humanValidationRequired`);
  if (!Array.isArray(value.evidence)) invalid(`${field}.evidence`);
  value.evidence.forEach((item, index) => {
    const evidenceField = `${field}.evidence[${index}]`;
    if (!isObject(item)) invalid(evidenceField);
    const allowed = ["id", "feature", "value", "unit", "baseline", "deviation", "direction", "windowSeconds"];
    const keys = Object.keys(item);
    if (keys.some((key) => !allowed.includes(key))) invalid(evidenceField);
    for (const key of ["id", "feature", "value", "unit"]) if (!(key in item)) invalid(`${evidenceField}.${key}`);
    string(item.id, `${evidenceField}.id`);
    string(item.feature, `${evidenceField}.feature`);
    finiteNumber(item.value, `${evidenceField}.value`);
    string(item.unit, `${evidenceField}.unit`);
    for (const numeric of ["baseline", "deviation"]) {
      if (numeric in item && item[numeric] !== null) finiteNumber(item[numeric], `${evidenceField}.${numeric}`);
    }
    if ("direction" in item && item.direction !== null && !EVIDENCE_DIRECTIONS.has(item.direction)) invalid(`${evidenceField}.direction`);
    if ("windowSeconds" in item && item.windowSeconds !== null) {
      finiteNumber(item.windowSeconds, `${evidenceField}.windowSeconds`);
      if (item.windowSeconds < 0) invalid(`${evidenceField}.windowSeconds`);
    }
  });
  requiredObject(value.model, `${field}.model`, ["name", "version", "configHash", "trainedUntil"]);
  string(value.model.name, `${field}.model.name`);
  string(value.model.version, `${field}.model.version`);
  if (typeof value.model.configHash !== "string" || !HASH.test(value.model.configHash)) invalid(`${field}.model.configHash`);
  timestamp(value.model.trainedUntil, `${field}.model.trainedUntil`);
  stringArray(value.limitations, `${field}.limitations`);
};

/**
 * Validates the normative v1 gateway boundary without shipping a JSON-schema engine.
 */
export function assertDigitalTwinSnapshot(value) {
  requiredObject(value, "value", [
    "schemaVersion", "assetTag", "mode", "generatedAt", "status", "freshness", "channels", "history",
    "assessment", "capabilities",
  ]);
  if (value.schemaVersion !== SCHEMA_VERSION) invalid("schemaVersion");
  string(value.assetTag, "assetTag");
  if (!MODES.has(value.mode)) invalid("mode");
  timestamp(value.generatedAt, "generatedAt");
  if (!STATUSES.has(value.status)) invalid("status");
  if (!FRESHNESS_VALUES.has(value.freshness)) invalid("freshness");
  if (!Array.isArray(value.channels)) invalid("channels");
  value.channels.forEach((frame, index) => assertFrame(frame, `channels[${index}]`));
  if (value.mode === "live" && (value.channels.length !== 2 || new Set(value.channels.map((frame) => frame.sensorId)).size !== 2 || !value.channels.some((frame) => frame.sensorId === "s1") || !value.channels.some((frame) => frame.sensorId === "s2"))) invalid("channels");
  if (!Array.isArray(value.history)) invalid("history");
  value.history.forEach((frame, index) => assertFrame(frame, `history[${index}]`));
  assertAssessment(value.assessment);
  requiredObject(value.capabilities, "capabilities", ["replayControls", "liveUpdates", "copilot", "twin3d"]);
  Object.entries(value.capabilities).forEach(([key, capability]) => {
    if (typeof capability !== "boolean") invalid(`capabilities.${key}`);
  });

  return value;
}

export function isDigitalTwinSnapshot(value) {
  try {
    assertDigitalTwinSnapshot(value);
    return true;
  } catch {
    return false;
  }
}
