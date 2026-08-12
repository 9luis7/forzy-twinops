const ROOT_KEYS = new Set(["schemaVersion", "modelUrl", "sourceSha256", "units", "upAxis", "groups", "sensors"]);
const GROUP_KEYS = new Set(["nodeNames", "componentTag"]);
const SENSOR_KEYS = new Set(["sensorId", "placement"]);
const GROUP_NAMES = ["motor", "pump", "base"];

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

function invalid(message) {
  throw new Error(`Invalid twin model manifest: ${message}`);
}

function requireOnlyKeys(value, allowed, location) {
  if (!isObject(value)) invalid(`${location} must be an object`);
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) invalid(`${location}.${key} is not allowed`);
  }
}

export function parseModelManifest(value) {
  requireOnlyKeys(value, ROOT_KEYS, "root");
  if (value.schemaVersion !== "1.0") invalid("schemaVersion");
  if (value.modelUrl !== "/models/conjunto-motor-bomba.glb") invalid("modelUrl");
  if (typeof value.sourceSha256 !== "string" || !/^[a-f0-9]{64}$/.test(value.sourceSha256)) invalid("sourceSha256");
  if (value.units !== "m") invalid("units");
  if (value.upAxis !== "Y") invalid("upAxis");
  if (!isObject(value.groups)) invalid("groups");

  for (const name of GROUP_NAMES) {
    const group = value.groups[name];
    if (!group) invalid(name);
    requireOnlyKeys(group, GROUP_KEYS, `groups.${name}`);
    if (!Array.isArray(group.nodeNames) || group.nodeNames.length === 0 || group.nodeNames.some((node) => typeof node !== "string" || node.length === 0)) {
      invalid(`groups.${name}.nodeNames`);
    }
    if (group.componentTag !== null && (typeof group.componentTag !== "string" || group.componentTag.length === 0)) {
      invalid(`groups.${name}.componentTag`);
    }
  }

  if (!Array.isArray(value.sensors)) invalid("sensors");
  const sensorIds = new Set();
  for (const sensor of value.sensors) {
    requireOnlyKeys(sensor, SENSOR_KEYS, "sensors");
    if ((sensor.sensorId !== "s1" && sensor.sensorId !== "s2") || sensorIds.has(sensor.sensorId)) invalid("sensors.sensorId");
    if (sensor.placement !== "unvalidated") invalid("sensors.placement");
    sensorIds.add(sensor.sensorId);
  }
  if (value.sensors.length !== 2 || sensorIds.size !== 2) invalid("sensors");

  return value;
}

export function componentTagForNode(manifest, nodeName) {
  for (const group of Object.values(manifest.groups)) {
    if (group.componentTag !== null && group.nodeNames.includes(nodeName)) return group.componentTag;
  }
  return null;
}
