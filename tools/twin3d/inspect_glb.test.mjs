import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { BoxGeometry, Group, Mesh, MeshBasicMaterial, Scene } from "three";
import { expect, it } from "vitest";
import { validateReport, validateTraceability } from "./inspect_glb.mjs";


const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const inspector = path.join(repositoryRoot, "tools", "twin3d", "inspect_glb.mjs");
const source = "C:\\Users\\Luis\\Downloads\\ChallengeForzy-bomba-teste.stp";
const glb = path.join(repositoryRoot, "public", "models", "conjunto-motor-bomba.glb");
const manifest = path.join(repositoryRoot, "public", "models", "conjunto-motor-bomba.manifest.json");
const report = path.join(repositoryRoot, "artifacts", "twin3d", "conversion-report.json");


function runInspector(sourcePath = source, manifestPath = manifest, reportPath = report) {
  return spawnSync(
    process.execPath,
    [inspector, "--source", sourcePath, glb, manifestPath, reportPath],
    { cwd: repositoryRoot, encoding: "utf8" },
  );
}

it("passes only when anchored to the independently supplied STEP source", () => {
  const result = runInspector();

  expect(result.status, result.stderr).toBe(0);
  expect(JSON.parse(result.stdout)).toMatchObject({ status: "PASS", observedTraceableNodes: 17 });
});

it("rejects a STEP source whose independently calculated hash differs", async () => {
  const temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), "twin3d-inspector-"));
  const tamperedSource = path.join(temporaryDirectory, "tampered.step");
  try {
    await writeFile(tamperedSource, "not the approved STEP", "utf8");

    const result = runInspector(tamperedSource);

    expect(result.status).toBe(1);
    expect(result.stderr).toMatch(/independent STEP source/);
  } finally {
    await rm(temporaryDirectory, { recursive: true });
  }
});

it("rejects duplicate sensor IDs instead of accepting two s1 entries", async () => {
  const temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), "twin3d-inspector-"));
  const invalidManifest = path.join(temporaryDirectory, "manifest.json");
  try {
    const value = JSON.parse(await readFile(manifest, "utf8"));
    value.sensors[1] = { ...value.sensors[0] };
    await writeFile(invalidManifest, JSON.stringify(value), "utf8");

    const result = runInspector(source, invalidManifest);

    expect(result.status).toBe(1);
    expect(result.stderr).toMatch(/sensor IDs must be exactly s1 and s2/);
  } finally {
    await rm(temporaryDirectory, { recursive: true });
  }
});

it("requires report.nodes and all 17 mappings to form the manifest bijection", async () => {
  const manifestValue = JSON.parse(await readFile(manifest, "utf8"));
  const reportValue = JSON.parse(await readFile(report, "utf8"));

  expect(() => validateReport(manifestValue, { ...reportValue, nodes: reportValue.nodes.slice().reverse() }))
    .toThrow(/report\.nodes/);

  const duplicateMapping = structuredClone(reportValue);
  duplicateMapping.nodeMappings[1].nodeName = duplicateMapping.nodeMappings[0].nodeName;
  expect(() => validateReport(manifestValue, duplicateMapping)).toThrow(/ordered bijection/);

  const missingMapping = structuredClone(reportValue);
  missingMapping.nodeMappings.pop();
  expect(() => validateReport(manifestValue, missingMapping)).toThrow(/17 nodeMappings/);
});

it("counts exact scene-name occurrences and requires a mesh below every traceable node", async () => {
  const manifestValue = JSON.parse(await readFile(manifest, "utf8"));
  const scene = new Scene();
  const geometry = new BoxGeometry(1, 1, 1);
  const material = new MeshBasicMaterial();
  const groups = manifestValue.nodes.map((nodeName) => {
    const group = new Group();
    group.name = nodeName;
    group.add(new Mesh(geometry, material));
    scene.add(group);
    return group;
  });

  expect(validateTraceability(scene, manifestValue)).toMatchObject({ observedTraceableNodes: 17 });

  const duplicate = groups[0].clone(true);
  scene.add(duplicate);
  expect(() => validateTraceability(scene, manifestValue)).toThrow(/observed 2/);
  scene.remove(duplicate);

  groups[0].clear();
  expect(() => validateTraceability(scene, manifestValue)).toThrow(/no mesh descendant/);
  geometry.dispose();
  material.dispose();
});
