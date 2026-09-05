import { expect, it } from "vitest";
import { BoxGeometry, Group, Mesh, MeshStandardMaterial, Scene } from "three";
import manifest from "../../../public/models/conjunto-motor-bomba.demo.manifest.json";
import { applyDemoMaterials, parseDemoModelManifest } from "./demoModel.js";
import { context } from "../../demo/testFixtures.js";

it("validates assumed anchors in transformed model world meters", () => {
  expect(parseDemoModelManifest(manifest)).toBe(manifest);
  expect(manifest.sensors[0].position).toEqual([71.935, 0.695, 18.775]);
  expect(manifest.sensors[1].placement).toBe("unvalidated");
  expect(() => parseDemoModelManifest({ ...manifest, sensors: manifest.sensors.map((s) => ({ ...s, coordinateSpace: "screen" })) })).toThrow();
});
it("sets independent motor/pump condition colors, neutral base/coupling, including child meshes", () => {
  const scene = new Scene(); const meshes = {};
  for (const group of ["motor", "pump", "base", "coupling"]) {
    const parent = new Group(); parent.name = manifest.groups[group].nodeNames[0];
    const mesh = new Mesh(new BoxGeometry(), new MeshStandardMaterial()); parent.add(mesh); scene.add(parent); meshes[group] = mesh;
  }
  const snapshot = context(); snapshot.sensors.s1.assessment = { assessment: { status: "alert" } }; snapshot.sensors.s2.assessment = { assessment: { status: "normal" } };
  applyDemoMaterials(scene, manifest, snapshot);
  expect(meshes.motor.material.color.getHexString()).toBe("d95757"); expect(meshes.pump.material.color.getHexString()).toBe("4f86a8");
  expect(meshes.base.material.color.getHexString()).toBe("405366"); expect(meshes.coupling.material.color.getHexString()).toBe("a7bdca");
  applyDemoMaterials(scene, manifest, snapshot, { selected: "s2", isolate: true });
  expect(meshes.pump.visible).toBe(true); expect(meshes.motor.visible).toBe(false);
  applyDemoMaterials(scene, manifest, snapshot); expect(meshes.motor.visible).toBe(true);
  Object.values(meshes).forEach((m) => { m.geometry.dispose(); m.material.dispose(); });
});
