import { expect, it } from "vitest";
import generatedManifest from "../../../public/models/conjunto-motor-bomba.manifest.json";
import { nodeGroup, parseModelManifest } from "./modelManifest.js";


const fixture = () => structuredClone(generatedManifest);

it("accepts the generated manifest without sensor placement", () => {
  const manifest = parseModelManifest(generatedManifest);

  expect(manifest.assetId).toBe("forzy-motor-01");
  expect(manifest.solidCount).toBe(17);
  expect(manifest.sensors).toEqual([
    { sensorId: "s1", placement: "unvalidated" },
    { sensorId: "s2", placement: "unvalidated" },
  ]);
});

it("resolves only exact generated node names to informational groups", () => {
  const manifest = parseModelManifest(generatedManifest);

  expect(nodeGroup(manifest, "R11_06-2130-ME22A_001")).toBe("motor");
  expect(nodeGroup(manifest, "R11_06-2130-B01A_BOMBA_008")).toBe("pump");
  expect(nodeGroup(manifest, "R11_06-2130-B01A_BASE_011")).toBe("base");
  expect(nodeGroup(manifest, "R11_06-2130-B01A_A")).toBe("coupling");
  expect(nodeGroup(manifest, "R11_06-2130-UNKNOWN")).toBeNull();
});

it("rejects sensor coordinates while placement is unvalidated", () => {
  const manifest = fixture();
  manifest.sensors[0].position = [1, 2, 3];

  expect(() => parseModelManifest(manifest)).toThrow(/position/);
});

it("rejects fictitious component bindings", () => {
  const manifest = fixture();
  manifest.groups.motor.componentTag = "CMP-MOTOR-FICTITIOUS";

  expect(() => parseModelManifest(manifest)).toThrow(/componentTag/);
});

it("rejects group nodes absent from the generated node inventory", () => {
  const manifest = fixture();
  manifest.groups.motor.nodeNames[0] = "ABSENT_NODE";

  expect(() => parseModelManifest(manifest)).toThrow(/ABSENT_NODE/);
});

it("rejects wildcard group bindings", () => {
  const manifest = fixture();
  manifest.groups.motor.nodeNames[0] = "*";

  expect(() => parseModelManifest(manifest)).toThrow(/\*/);
});

it("rejects the legacy fictitious assetTag", () => {
  const manifest = fixture();
  manifest.assetTag = "MTR-BMB-042";

  expect(() => parseModelManifest(manifest)).toThrow(/assetTag/);
});
