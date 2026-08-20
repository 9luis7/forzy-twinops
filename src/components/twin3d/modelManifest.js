const ROOT_KEYS = new Set([
  "schemaVersion",
  "assetId",
  "modelUrl",
  "sourceSha256",
  "generatedBy",
  "solidCount",
  "units",
  "upAxis",
  "nodes",
  "groups",
  "sensors",
]);
const GENERATED_BY_KEYS = new Set(["tool", "version", "cadqueryVersion"]);
const GROUP_KEYS = new Set(["nodeNames"]);
const SENSOR_KEYS = new Set(["sensorId", "placement"]);
const GROUP_NAMES = ["motor", "pump", "base", "coupling"];
const EXPECTED_NODES = 17;
const SAFE_NODE_NAME = /^[A-Za-z0-9_-]+$/;


const hasOwn = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const isPlainRecord = (value) => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
};

function invalid(message) {
  throw new Error(`Invalid twin model manifest: ${message}`);
}

function requireOnlyKeys(value, allowed, location) {
  if (!isPlainRecord(value)) invalid(`${location} must be a plain record`);
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) invalid(`${location}.${key} is not allowed`);
  }
  for (const key of allowed) {
    if (!hasOwn(value, key)) invalid(`${location}.${key} must be an own property`);
  }
}

function requireNonEmptyString(value, location) {
  if (typeof value !== "string" || value.length === 0) invalid(location);
}

export function parseModelManifest(value) {
  requireOnlyKeys(value, ROOT_KEYS, "root");
  if (value.schemaVersion !== "1.0") invalid("schemaVersion");
  if (value.assetId !== "forzy-motor-01") invalid("assetId");
  if (value.modelUrl !== "/models/conjunto-motor-bomba.glb") invalid("modelUrl");
  if (typeof value.sourceSha256 !== "string" || !/^[a-f0-9]{64}$/.test(value.sourceSha256)) {
    invalid("sourceSha256");
  }

  requireOnlyKeys(value.generatedBy, GENERATED_BY_KEYS, "generatedBy");
  if (value.generatedBy.tool !== "tools/twin3d/convert_step.py") invalid("generatedBy.tool");
  if (value.generatedBy.version !== "1.0.0") invalid("generatedBy.version");
  requireNonEmptyString(value.generatedBy.cadqueryVersion, "generatedBy.cadqueryVersion");

  if (value.solidCount !== EXPECTED_NODES) invalid("solidCount");
  if (value.units !== "m") invalid("units");
  if (value.upAxis !== "Y") invalid("upAxis");
  if (!Array.isArray(value.nodes) || value.nodes.length !== EXPECTED_NODES) invalid("nodes");
  if (value.nodes.some((nodeName) => typeof nodeName !== "string" || !SAFE_NODE_NAME.test(nodeName))) {
    invalid("nodes contains an unsafe or wildcard name");
  }
  const nodeInventory = new Set(value.nodes);
  if (nodeInventory.size !== value.nodes.length) invalid("nodes contains duplicates");

  requireOnlyKeys(value.groups, new Set(GROUP_NAMES), "groups");
  if (Object.keys(value.groups).length !== GROUP_NAMES.length) invalid("groups");
  const groupedNodes = new Set();
  for (const groupName of GROUP_NAMES) {
    const group = value.groups[groupName];
    requireOnlyKeys(group, GROUP_KEYS, `groups.${groupName}`);
    if (!Array.isArray(group.nodeNames) || group.nodeNames.length === 0) {
      invalid(`groups.${groupName}.nodeNames`);
    }
    for (const nodeName of group.nodeNames) {
      if (typeof nodeName !== "string" || !SAFE_NODE_NAME.test(nodeName)) invalid(`groups.${groupName}.${nodeName}`);
      if (!nodeInventory.has(nodeName)) invalid(`groups.${groupName}.${nodeName} is absent from nodes`);
      if (groupedNodes.has(nodeName)) invalid(`groups.${groupName}.${nodeName} is duplicated`);
      groupedNodes.add(nodeName);
    }
  }
  if (groupedNodes.size !== nodeInventory.size) invalid("groups must partition nodes");

  if (!Array.isArray(value.sensors) || value.sensors.length !== 2) invalid("sensors");
  const sensorIds = new Set();
  for (const sensor of value.sensors) {
    requireOnlyKeys(sensor, SENSOR_KEYS, "sensors");
    if ((sensor.sensorId !== "s1" && sensor.sensorId !== "s2") || sensorIds.has(sensor.sensorId)) {
      invalid("sensors.sensorId");
    }
    if (sensor.placement !== "unvalidated") invalid("sensors.placement");
    sensorIds.add(sensor.sensorId);
  }
  if (sensorIds.size !== 2) invalid("sensors");

  return value;
}

export function nodeGroup(manifest, nodeName) {
  for (const groupName of GROUP_NAMES) {
    if (manifest.groups[groupName].nodeNames.includes(nodeName)) return groupName;
  }
  return null;
}
