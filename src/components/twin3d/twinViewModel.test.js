import { describe, expect, it } from "vitest";
import { buildTwinViewModel } from "./twinViewModel.js";
import { alertSnapshot, manifestWithApprovedMotorBinding } from "./testFixtures.js";

describe("buildTwinViewModel", () => {
  it("highlights only nodes explicitly bound to assessment.componentTag", () => {
    const vm = buildTwinViewModel({
      snapshot: alertSnapshot,
      manifest: manifestWithApprovedMotorBinding,
      activeComponent: null,
    });

    expect(vm.highlightedNodeNames).toEqual(["ME22A_CORPO", "ME22A_EIXO"]);
    expect(vm.status).toBe("alert");
  });

  it("does not infer a highlight when componentTag is null and keeps channels separate", () => {
    const vm = buildTwinViewModel({
      snapshot: { ...alertSnapshot, assessment: { ...alertSnapshot.assessment, componentTag: null } },
      manifest: manifestWithApprovedMotorBinding,
      activeComponent: null,
    });

    expect(vm.highlightedNodeNames).toEqual([]);
    expect(vm.channels).toEqual([
      expect.objectContaining({ sensorId: "s1", placementLabel: "Posição não validada" }),
      expect.objectContaining({ sensorId: "s2", placementLabel: "Posição não validada" }),
    ]);
  });

  it("warns instead of binding an unknown componentTag", () => {
    const vm = buildTwinViewModel({
      snapshot: { ...alertSnapshot, assessment: { ...alertSnapshot.assessment, componentTag: "CMP-UNKNOWN" } },
      manifest: manifestWithApprovedMotorBinding,
      activeComponent: null,
    });

    expect(vm.highlightedNodeNames).toEqual([]);
    expect(vm.warning).toBe("Sem associação 3D aprovada para CMP-UNKNOWN");
  });
});
