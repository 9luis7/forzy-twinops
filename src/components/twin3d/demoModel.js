import { parseModelManifest, nodeGroup } from "./modelManifest.js";
import { buildTwinViewModel } from "./twinViewModel.js";

export function parseDemoModelManifest(value) {
  if (value?.schemaVersion !== "1.1") throw new Error("Demo manifest version invalid");
  parseModelManifest({ ...value, schemaVersion: "1.0", sensors: value.sensors.map(({ sensorId, placement }) => ({ sensorId, placement })) });
  for (const sensor of value.sensors) {
    if (!Array.isArray(sensor.position) || sensor.position.length !== 3 || sensor.position.some((n) => !Number.isFinite(n))
      || sensor.coordinateSpace !== "model-world" || sensor.group !== (sensor.sensorId === "s1" ? "motor" : "pump")
      || typeof sensor.label !== "string" || !sensor.label.includes("assumida")) throw new Error("Demo sensor anchor invalid");
  }
  return value;
}

export function meshGroup(manifest, mesh) {
  let node = mesh;
  while (node) { const group = nodeGroup(manifest, node.name); if (group) return group; node = node.parent; }
  return null;
}

export function applyDemoMaterials(scene, manifest, snapshot, { selected = "all", isolate = false } = {}) {
  scene.traverse((node) => {
    if (!node.isMesh) return;
    const group = meshGroup(manifest, node);
    const sensorId = group === "motor" ? "s1" : group === "pump" ? "s2" : null;
    const status = sensorId ? snapshot.sensors[sensorId].assessment?.assessment.status ?? "unknown" : "unknown";
    const view = buildTwinViewModel({ snapshot: { status } });
    const selectedGroup = selected === "s1" ? "motor" : selected === "s2" ? "pump" : null;
    node.visible = !isolate || !selectedGroup || group === selectedGroup;
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    materials.forEach((material) => {
      material.color?.set(sensorId ? view.materialColor : group === "coupling" ? "#a7bdca" : "#405366");
      material.emissive?.set(sensorId ? view.emissiveColor : "#000000");
      material.emissiveIntensity = sensorId ? view.emissiveIntensity : 0;
      material.metalness = group === "coupling" ? 0.55 : 0.18;
      material.roughness = group === "coupling" ? 0.4 : 0.72;
      material.needsUpdate = true;
    });
  });
}
