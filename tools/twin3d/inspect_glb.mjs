import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Box3 } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";


const MAX_GLB_BYTES = 20 * 1024 * 1024;
const EXPECTED_SOLID_COUNT = 17;

if (globalThis.ProgressEvent === undefined) {
  globalThis.ProgressEvent = class ProgressEvent {
    constructor(type, init = {}) {
      this.type = type;
      Object.assign(this, init);
    }
  };
}

function fail(message) {
  throw new Error(`Invalid Twin 3D asset: ${message}`);
}

function withoutHashPrefix(value) {
  return typeof value === "string" ? value.replace(/^sha256:/, "") : value;
}

function finiteVector(vector, label) {
  if (vector.some((value) => !Number.isFinite(value))) fail(`${label} is not finite`);
}

function closeVector(actual, expected, label, tolerance = 0.001) {
  finiteVector(expected, `${label} report`);
  if (actual.some((value, index) => Math.abs(value - expected[index]) > tolerance)) {
    fail(`${label} differs from conversion report`);
  }
}

function validateManifest(manifest) {
  if (manifest.assetId !== "forzy-motor-01") fail("assetId");
  if (manifest.modelUrl !== "/models/conjunto-motor-bomba.glb") fail("modelUrl");
  if (manifest.units !== "m" || manifest.upAxis !== "Y") fail("units or upAxis");
  if (manifest.solidCount !== EXPECTED_SOLID_COUNT) fail("solidCount must be 17");
  if (!Array.isArray(manifest.nodes) || manifest.nodes.length !== manifest.solidCount) fail("nodes");
  if (new Set(manifest.nodes).size !== manifest.nodes.length) fail("duplicate nodes");
  if (typeof manifest.sourceSha256 !== "string" || !/^[a-f0-9]{64}$/.test(manifest.sourceSha256)) {
    fail("sourceSha256");
  }

  const expectedGroups = ["motor", "pump", "base", "coupling"];
  if (!manifest.groups || Object.keys(manifest.groups).sort().join(",") !== expectedGroups.sort().join(",")) {
    fail("groups");
  }
  const groupedNodes = expectedGroups.flatMap((groupName) => {
    const group = manifest.groups[groupName];
    if (!group || Object.keys(group).join(",") !== "nodeNames" || !Array.isArray(group.nodeNames)) {
      fail(`groups.${groupName}`);
    }
    return group.nodeNames;
  });
  if (groupedNodes.length !== manifest.nodes.length || new Set(groupedNodes).size !== groupedNodes.length) {
    fail("group nodes must partition manifest nodes");
  }
  if (groupedNodes.some((nodeName) => !manifest.nodes.includes(nodeName))) fail("group node absent from nodes");

  if (!Array.isArray(manifest.sensors) || manifest.sensors.length !== 2) fail("sensors");
  for (const sensor of manifest.sensors) {
    if (Object.keys(sensor).sort().join(",") !== "placement,sensorId") fail("sensor coordinates or metadata");
    if (!(["s1", "s2"].includes(sensor.sensorId)) || sensor.placement !== "unvalidated") fail("sensor binding");
  }

  const serialised = JSON.stringify(manifest);
  if (/"(?:assetTag|componentTag|position|coordinates)"/.test(serialised)) {
    fail("invented identity, component binding, or coordinates");
  }
}

async function inspect(glbPath, manifestPath, reportPath) {
  const [glb, manifestText, reportText, glbStat] = await Promise.all([
    readFile(glbPath),
    readFile(manifestPath, "utf8"),
    readFile(reportPath, "utf8"),
    stat(glbPath),
  ]);
  const manifest = JSON.parse(manifestText);
  const report = JSON.parse(reportText);
  validateManifest(manifest);

  if (glbStat.size > MAX_GLB_BYTES) fail(`GLB exceeds ${MAX_GLB_BYTES} bytes`);
  if (glb.subarray(0, 4).toString("ascii") !== "glTF") fail("GLB header");

  const sourceHash = withoutHashPrefix(report.sourceSha256);
  if (manifest.sourceSha256 !== sourceHash) fail("source hash differs from conversion report");
  const glbHash = createHash("sha256").update(glb).digest("hex");
  if (glbHash !== withoutHashPrefix(report.glbSha256)) fail("GLB hash differs from conversion report");
  if (report.glbBytes !== glbStat.size || report.solidCount !== manifest.solidCount) {
    fail("report size or solid count");
  }

  const arrayBuffer = glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength);
  const gltf = await new GLTFLoader().parseAsync(arrayBuffer, `${path.dirname(glbPath)}${path.sep}`);
  const sceneNames = new Set();
  let meshCount = 0;
  gltf.scene.traverse((node) => {
    if (node.name) sceneNames.add(node.name);
    if (node.isMesh) meshCount += 1;
  });
  if (meshCount === 0) fail("GLB has zero meshes");
  for (const nodeName of manifest.nodes) {
    if (!sceneNames.has(nodeName)) fail(`manifest node missing from GLB: ${nodeName}`);
  }

  gltf.scene.updateMatrixWorld(true);
  const bounds = new Box3().setFromObject(gltf.scene);
  if (bounds.isEmpty()) fail("GLB bounds are empty");
  const minimum = bounds.min.toArray();
  const maximum = bounds.max.toArray();
  finiteVector(minimum, "bounds.min");
  finiteVector(maximum, "bounds.max");
  if (!report.bounds || !Array.isArray(report.bounds.min) || !Array.isArray(report.bounds.max)) {
    fail("conversion report bounds");
  }
  closeVector(minimum, report.bounds.min, "bounds.min");
  closeVector(maximum, report.bounds.max, "bounds.max");

  return {
    status: "PASS",
    glbBytes: glbStat.size,
    glbSha256: `sha256:${glbHash}`,
    sourceSha256: `sha256:${sourceHash}`,
    solidCount: manifest.solidCount,
    meshCount,
    traceableNodes: manifest.nodes.length,
    bounds: { min: minimum, max: maximum },
  };
}

const [glbArgument, manifestArgument, reportArgument] = process.argv.slice(2);
if (!glbArgument || !manifestArgument) {
  console.error("Usage: node tools/twin3d/inspect_glb.mjs <model.glb> <manifest.json> [conversion-report.json]");
  process.exitCode = 2;
} else {
  const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
  const repositoryRoot = path.resolve(scriptDirectory, "..", "..");
  const reportPath = reportArgument ?? path.join(repositoryRoot, "artifacts", "twin3d", "conversion-report.json");
  try {
    const result = await inspect(path.resolve(glbArgument), path.resolve(manifestArgument), path.resolve(reportPath));
    console.log(JSON.stringify(result));
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
