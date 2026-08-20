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

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function withoutHashPrefix(value) {
  return typeof value === "string" ? value.replace(/^sha256:/, "") : value;
}

function sameArray(left, right) {
  return Array.isArray(left)
    && Array.isArray(right)
    && left.length === right.length
    && left.every((value, index) => value === right[index]);
}

function finiteVector(vector, label) {
  if (!Array.isArray(vector) || vector.length !== 3 || vector.some((value) => !Number.isFinite(value))) {
    fail(`${label} is not a finite three-vector`);
  }
}

function closeVector(actual, expected, label, tolerance = 0.001) {
  finiteVector(expected, `${label} report`);
  if (actual.some((value, index) => Math.abs(value - expected[index]) > tolerance)) {
    fail(`${label} differs from conversion report`);
  }
}

export function validateManifest(manifest) {
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
  const sensorIds = manifest.sensors.map((sensor) => {
    if (Object.keys(sensor).sort().join(",") !== "placement,sensorId") fail("sensor coordinates or metadata");
    if (sensor.placement !== "unvalidated") fail("sensor binding");
    return sensor.sensorId;
  });
  if (new Set(sensorIds).size !== 2 || sensorIds.slice().sort().join(",") !== "s1,s2") {
    fail("sensor IDs must be exactly s1 and s2");
  }

  const serialised = JSON.stringify(manifest);
  if (/"(?:assetTag|componentTag|position|coordinates)"/.test(serialised)) {
    fail("invented identity, component binding, or coordinates");
  }
}

export function validateReport(manifest, report) {
  if (report.solidCount !== manifest.solidCount) fail("report solid count differs from manifest");
  if (!sameArray(report.nodes, manifest.nodes)) fail("report.nodes must exactly equal manifest.nodes");
  if (!Array.isArray(report.nodeMappings) || report.nodeMappings.length !== manifest.solidCount) {
    fail("report must contain 17 nodeMappings");
  }
  const mappedNodeNames = report.nodeMappings.map((mapping, index) => {
    if (
      !mapping
      || Object.keys(mapping).sort().join(",") !== "nodeName,sourceName"
      || typeof mapping.sourceName !== "string"
      || mapping.sourceName.length === 0
      || typeof mapping.nodeName !== "string"
      || mapping.nodeName.length === 0
    ) {
      fail(`invalid nodeMappings[${index}]`);
    }
    return mapping.nodeName;
  });
  if (new Set(mappedNodeNames).size !== manifest.solidCount || !sameArray(mappedNodeNames, manifest.nodes)) {
    fail("nodeMappings must form an ordered bijection onto manifest.nodes");
  }
}

export function validateTraceability(scene, manifest) {
  const expectedNames = new Set(manifest.nodes);
  const occurrences = new Map(manifest.nodes.map((nodeName) => [nodeName, []]));
  let meshCount = 0;
  scene.traverse((node) => {
    if (node.isMesh) meshCount += 1;
    if (expectedNames.has(node.name)) occurrences.get(node.name).push(node);
  });
  if (meshCount === 0) fail("GLB has zero meshes");

  let observedTraceableNodes = 0;
  for (const nodeName of manifest.nodes) {
    const namedNodes = occurrences.get(nodeName);
    observedTraceableNodes += namedNodes.length;
    if (namedNodes.length !== 1) {
      fail(`expected exactly one scene node named ${nodeName}, observed ${namedNodes.length}`);
    }
    let descendantMeshes = 0;
    namedNodes[0].traverse((descendant) => {
      if (descendant.isMesh) descendantMeshes += 1;
    });
    if (descendantMeshes === 0) fail(`traceable node has no mesh descendant: ${nodeName}`);
  }
  if (observedTraceableNodes !== manifest.solidCount) {
    fail(`observed ${observedTraceableNodes} traceable nodes, expected ${manifest.solidCount}`);
  }
  return { meshCount, observedTraceableNodes };
}

export async function inspect({ sourcePath, glbPath, manifestPath, reportPath }) {
  const [source, glb, manifestText, reportText, glbStat] = await Promise.all([
    readFile(sourcePath),
    readFile(glbPath),
    readFile(manifestPath, "utf8"),
    readFile(reportPath, "utf8"),
    stat(glbPath),
  ]);
  const manifest = JSON.parse(manifestText);
  const report = JSON.parse(reportText);
  validateManifest(manifest);
  validateReport(manifest, report);

  if (glbStat.size > MAX_GLB_BYTES) fail(`GLB exceeds ${MAX_GLB_BYTES} bytes`);
  if (glb.subarray(0, 4).toString("ascii") !== "glTF") fail("GLB header");

  const sourceHash = sha256(source);
  if (manifest.sourceSha256 !== sourceHash) fail("manifest source hash differs from independent STEP source");
  if (withoutHashPrefix(report.sourceSha256) !== sourceHash) {
    fail("report source hash differs from independent STEP source");
  }
  const glbHash = sha256(glb);
  if (glbHash !== withoutHashPrefix(report.glbSha256)) fail("GLB hash differs from conversion report");
  if (report.glbBytes !== glbStat.size) fail("report GLB size differs from file");

  const arrayBuffer = glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength);
  const gltf = await new GLTFLoader().parseAsync(arrayBuffer, `${path.dirname(glbPath)}${path.sep}`);
  const { meshCount, observedTraceableNodes } = validateTraceability(gltf.scene, manifest);

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
    observedTraceableNodes,
    traceableNodes: observedTraceableNodes,
    bounds: { min: minimum, max: maximum },
  };
}

function parseArguments(arguments_) {
  let sourceArgument = null;
  const positional = [];
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    if (argument === "--source") {
      sourceArgument = arguments_[index + 1] ?? null;
      index += 1;
    } else if (argument.startsWith("--")) {
      throw new Error(`Unknown option: ${argument}`);
    } else {
      positional.push(argument);
    }
  }
  if (!sourceArgument || positional.length < 2 || positional.length > 3) {
    throw new Error(
      "Usage: node tools/twin3d/inspect_glb.mjs --source <source.step> "
      + "<model.glb> <manifest.json> [conversion-report.json]",
    );
  }
  return { sourceArgument, positional };
}

async function main() {
  const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
  const repositoryRoot = path.resolve(scriptDirectory, "..", "..");
  const { sourceArgument, positional } = parseArguments(process.argv.slice(2));
  const [glbArgument, manifestArgument, reportArgument] = positional;
  const reportPath = reportArgument ?? path.join(repositoryRoot, "artifacts", "twin3d", "conversion-report.json");
  const result = await inspect({
    sourcePath: path.resolve(sourceArgument),
    glbPath: path.resolve(glbArgument),
    manifestPath: path.resolve(manifestArgument),
    reportPath: path.resolve(reportPath),
  });
  console.log(JSON.stringify(result));
}

const isCommandLine = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isCommandLine) {
  try {
    await main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
