export const SCHEMA_VERSION_V2 = "2.0";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA256 = /^sha256:[0-9a-f]{64}$/;
const TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?Z$/;

const isRecord = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

function fail(path, message) {
  throw new TypeError(`${path} ${message}`);
}

function assertRecord(value, path, required, optional = []) {
  if (!isRecord(value)) fail(path, "must be an object");

  const allowed = new Set([...required, ...optional]);
  const keys = Object.keys(value);
  const missing = required.find((key) => !Object.hasOwn(value, key));
  if (missing) fail(`${path}.${missing}`, "is required");
  if (keys.length !== required.length + optional.filter((key) => Object.hasOwn(value, key)).length
    || keys.some((key) => !allowed.has(key))) fail(path, "has unexpected fields");
}

function assertString(value, path, { minLength = 0, pattern } = {}) {
  if (typeof value !== "string" || value.length < minLength || (pattern && !pattern.test(value))) {
    fail(path, "must be a valid string");
  }
}

function assertEnum(value, path, allowed) {
  if (!allowed.includes(value)) fail(path, "has an invalid value");
}

function assertFiniteNumber(value, path, { minimum } = {}) {
  if (typeof value !== "number" || !Number.isFinite(value) || (minimum !== undefined && value < minimum)) {
    fail(path, "must be a finite number");
  }
}

function assertBoolean(value, path) {
  if (typeof value !== "boolean") fail(path, "must be a boolean");
}

function isLeapYear(year) {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

function assertTimestamp(value, path) {
  assertString(value, path);
  const match = TIMESTAMP.exec(value);
  if (!match) fail(path, "must be an RFC 3339 UTC timestamp");

  const [, yearText, monthText, dayText, hourText, minuteText, secondText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const days = [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

  if (year === 0 || month < 1 || month > 12 || day < 1 || day > days[month - 1]
    || hour > 23 || minute > 59 || second > 59) {
    fail(path, "must be an RFC 3339 UTC timestamp");
  }
}

function assertNullableTimestamp(value, path) {
  if (value !== null) assertTimestamp(value, path);
}

function assertMeasurement(value, path, unit, { statistic = false } = {}) {
  const required = statistic
    ? ["value", "unit", "statistic", "semanticConfidence"]
    : ["value", "unit", "semanticConfidence"];
  assertRecord(value, path, required);
  assertFiniteNumber(value.value, `${path}.value`);
  if (value.unit !== unit) fail(`${path}.unit`, `must equal ${unit}`);
  if (statistic && value.statistic !== "unknown") fail(`${path}.statistic`, "must equal unknown");
  assertEnum(value.semanticConfidence, `${path}.semanticConfidence`, [
    "confirmed", "inferred_from_datasheet", "unconfirmed",
  ]);
}

function assertFrame(value, path) {
  assertRecord(value, path, [
    "schemaVersion", "frameId", "assetId", "sensorId", "observedAt", "receivedAt",
    "timestampQuality", "measurements", "qualityFlags",
  ]);
  if (value.schemaVersion !== SCHEMA_VERSION_V2) fail(`${path}.schemaVersion`, "must equal 2.0");
  assertString(value.frameId, `${path}.frameId`, { pattern: UUID });
  if (value.assetId !== "forzy-motor-01") fail(`${path}.assetId`, "must equal forzy-motor-01");
  assertEnum(value.sensorId, `${path}.sensorId`, ["s1", "s2"]);
  assertNullableTimestamp(value.observedAt, `${path}.observedAt`);
  assertNullableTimestamp(value.receivedAt, `${path}.receivedAt`);
  assertEnum(value.timestampQuality, `${path}.timestampQuality`, ["assumed_from_retrieval", "unavailable"]);
  if (value.timestampQuality === "assumed_from_retrieval"
    && (value.observedAt === null || value.receivedAt === null || value.observedAt !== value.receivedAt)) {
    fail(`${path}.observedAt`, "must equal receivedAt when timestampQuality is assumed_from_retrieval");
  }
  if (value.timestampQuality === "unavailable" && (value.observedAt !== null || value.receivedAt !== null)) {
    fail(`${path}.timestampQuality`, "requires null observedAt and receivedAt when unavailable");
  }

  assertRecord(value.measurements, `${path}.measurements`, [
    "vibrationVelocityRms", "vibrationAcceleration", "temperature",
  ]);
  if (value.measurements.vibrationVelocityRms !== null) {
    assertMeasurement(value.measurements.vibrationVelocityRms, `${path}.measurements.vibrationVelocityRms`, "mm/s");
  }
  if (value.measurements.vibrationAcceleration !== null) {
    assertMeasurement(value.measurements.vibrationAcceleration, `${path}.measurements.vibrationAcceleration`, "g", { statistic: true });
  }
  if (value.measurements.temperature !== null) {
    assertMeasurement(value.measurements.temperature, `${path}.measurements.temperature`, "degC");
  }
  assertStringArray(value.qualityFlags, `${path}.qualityFlags`);
}

function assertStringArray(value, path) {
  if (!Array.isArray(value)) fail(path, "must be an array");
  value.forEach((entry, index) => assertString(entry, `${path}[${index}]`));
}

function assertSensorHealth(value, path) {
  assertRecord(value, path, ["lastAttemptAt", "lastSuccessAt", "latencyMs", "error", "sampleCount"]);
  assertNullableTimestamp(value.lastAttemptAt, `${path}.lastAttemptAt`);
  assertNullableTimestamp(value.lastSuccessAt, `${path}.lastSuccessAt`);
  if (value.latencyMs !== null) assertFiniteNumber(value.latencyMs, `${path}.latencyMs`, { minimum: 0 });
  assertEnum(value.error, `${path}.error`, ["upstream_unavailable", "invalid_payload", null]);
  if (!Number.isInteger(value.sampleCount) || value.sampleCount < 0) fail(`${path}.sampleCount`, "must be a non-negative integer");
}

function assertEvidence(value, path) {
  assertRecord(value, path, ["id", "feature", "value", "unit"], ["baseline", "deviation", "direction", "windowSeconds"]);
  assertString(value.id, `${path}.id`, { minLength: 1 });
  assertString(value.feature, `${path}.feature`, { minLength: 1 });
  assertFiniteNumber(value.value, `${path}.value`);
  assertString(value.unit, `${path}.unit`, { minLength: 1 });
  if (Object.hasOwn(value, "baseline") && value.baseline !== null) assertFiniteNumber(value.baseline, `${path}.baseline`);
  if (Object.hasOwn(value, "deviation") && value.deviation !== null) assertFiniteNumber(value.deviation, `${path}.deviation`);
  if (Object.hasOwn(value, "direction")) assertEnum(value.direction, `${path}.direction`, ["up", "down", "stable", "unknown", null]);
  if (Object.hasOwn(value, "windowSeconds") && value.windowSeconds !== null) {
    assertFiniteNumber(value.windowSeconds, `${path}.windowSeconds`, { minimum: 0 });
  }
}

function assertAssessment(value, path) {
  assertRecord(value, path, [
    "schemaVersion", "assessmentId", "assetId", "sensorId", "window", "quality", "operatingContext",
    "assessment", "componentTag", "recommendation", "humanValidationRequired", "evidence", "model", "limitations",
  ]);
  if (value.schemaVersion !== SCHEMA_VERSION_V2) fail(`${path}.schemaVersion`, "must equal 2.0");
  assertString(value.assessmentId, `${path}.assessmentId`, { pattern: UUID });
  if (value.assetId !== "forzy-motor-01") fail(`${path}.assetId`, "must equal forzy-motor-01");
  assertEnum(value.sensorId, `${path}.sensorId`, ["s1", "s2"]);

  assertRecord(value.window, `${path}.window`, ["start", "end", "receivedAt", "freshnessMs"]);
  assertTimestamp(value.window.start, `${path}.window.start`);
  assertTimestamp(value.window.end, `${path}.window.end`);
  assertTimestamp(value.window.receivedAt, `${path}.window.receivedAt`);
  assertFiniteNumber(value.window.freshnessMs, `${path}.window.freshnessMs`, { minimum: 0 });

  assertRecord(value.quality, `${path}.quality`, ["status", "flags"]);
  assertEnum(value.quality.status, `${path}.quality.status`, ["ok", "degraded", "insufficient_data"]);
  assertStringArray(value.quality.flags, `${path}.quality.flags`);

  assertRecord(value.operatingContext, `${path}.operatingContext`, ["state", "estimated"]);
  assertEnum(value.operatingContext.state, `${path}.operatingContext.state`, ["steady", "startup", "shutdown", "stopped", "unknown"]);
  assertBoolean(value.operatingContext.estimated, `${path}.operatingContext.estimated`);

  assertRecord(value.assessment, `${path}.assessment`, ["status", "anomalyScore", "deteriorationScore", "scoreSemantics", "episodeId", "persistenceSeconds"]);
  assertEnum(value.assessment.status, `${path}.assessment.status`, ["normal", "watch", "alert", "insufficient_data"]);
  assertFiniteNumber(value.assessment.anomalyScore, `${path}.assessment.anomalyScore`);
  assertFiniteNumber(value.assessment.deteriorationScore, `${path}.assessment.deteriorationScore`);
  if (value.assessment.scoreSemantics !== "relative_to_historical_baseline_not_failure_probability") {
    fail(`${path}.assessment.scoreSemantics`, "has an invalid value");
  }
  if (value.assessment.episodeId !== null) assertString(value.assessment.episodeId, `${path}.assessment.episodeId`);
  assertFiniteNumber(value.assessment.persistenceSeconds, `${path}.assessment.persistenceSeconds`, { minimum: 0 });

  if (value.componentTag !== null) fail(`${path}.componentTag`, "must be null");
  if (value.recommendation !== null) assertString(value.recommendation, `${path}.recommendation`);
  assertBoolean(value.humanValidationRequired, `${path}.humanValidationRequired`);
  if (!Array.isArray(value.evidence)) fail(`${path}.evidence`, "must be an array");
  value.evidence.forEach((entry, index) => assertEvidence(entry, `${path}.evidence[${index}]`));

  assertRecord(value.model, `${path}.model`, ["name", "version", "configHash", "trainedUntil"]);
  assertString(value.model.name, `${path}.model.name`, { minLength: 1 });
  assertString(value.model.version, `${path}.model.version`, { minLength: 1 });
  assertString(value.model.configHash, `${path}.model.configHash`, { pattern: SHA256 });
  assertTimestamp(value.model.trainedUntil, `${path}.model.trainedUntil`);
  assertStringArray(value.limitations, `${path}.limitations`);
}

export function assertDigitalTwinSnapshotV2(value) {
  assertRecord(value, "snapshot", [
    "schemaVersion", "asset", "generatedAt", "status", "operationalState", "freshnessBasis",
    "channels", "history", "assessment", "integration", "capabilities",
  ]);
  if (value.schemaVersion !== SCHEMA_VERSION_V2) fail("snapshot.schemaVersion", "must equal 2.0");

  assertRecord(value.asset, "snapshot.asset", ["assetId", "displayName", "officialTag"]);
  if (value.asset.assetId !== "forzy-motor-01") fail("snapshot.asset.assetId", "must equal forzy-motor-01");
  if (value.asset.displayName !== "Conjunto motor-bomba monitorado") fail("snapshot.asset.displayName", "has an invalid value");
  if (value.asset.officialTag !== null) fail("snapshot.asset.officialTag", "must be null");
  assertTimestamp(value.generatedAt, "snapshot.generatedAt");
  assertEnum(value.status, "snapshot.status", ["normal", "watch", "alert", "unknown", "insufficient_data"]);
  assertEnum(value.operationalState, "snapshot.operationalState", ["received_now", "last_known", "expected_idle", "unavailable"]);
  assertEnum(value.freshnessBasis, "snapshot.freshnessBasis", ["retrieval_time", "last_received", "schedule", "none"]);

  if (!Array.isArray(value.channels) || value.channels.length !== 2) fail("snapshot.channels", "must contain exactly two channels");
  value.channels.forEach((channel, index) => assertFrame(channel, `snapshot.channels[${index}]`));
  const channelIds = value.channels.map((channel) => channel.sensorId);
  if (channelIds.filter((sensorId) => sensorId === "s1").length !== 1 || channelIds.filter((sensorId) => sensorId === "s2").length !== 1) {
    fail("snapshot.channels", "must contain exactly one s1 and one s2");
  }
  if (!Array.isArray(value.history)) fail("snapshot.history", "must be an array");
  value.history.forEach((frame, index) => assertFrame(frame, `snapshot.history[${index}]`));
  if (value.assessment !== null) assertAssessment(value.assessment, "snapshot.assessment");

  assertRecord(value.integration, "snapshot.integration", ["sensors"]);
  assertRecord(value.integration.sensors, "snapshot.integration.sensors", ["s1", "s2"]);
  assertSensorHealth(value.integration.sensors.s1, "snapshot.integration.sensors.s1");
  assertSensorHealth(value.integration.sensors.s2, "snapshot.integration.sensors.s2");

  assertRecord(value.capabilities, "snapshot.capabilities", ["liveUpdates", "replayControls", "copilot", "twin3d"]);
  if (value.capabilities.liveUpdates !== true) fail("snapshot.capabilities.liveUpdates", "must be true");
  if (value.capabilities.replayControls !== false) fail("snapshot.capabilities.replayControls", "must be false");
  if (value.capabilities.copilot !== false) fail("snapshot.capabilities.copilot", "must be false");
  assertBoolean(value.capabilities.twin3d, "snapshot.capabilities.twin3d");
  return value;
}

export function isDigitalTwinSnapshotV2(value) {
  try {
    assertDigitalTwinSnapshotV2(value);
    return true;
  } catch {
    return false;
  }
}
