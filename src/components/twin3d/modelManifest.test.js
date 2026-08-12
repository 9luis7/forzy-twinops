import { expect, it } from "vitest";
import { componentTagForNode, parseModelManifest } from "./modelManifest.js";
import { manifestWithApprovedMotorBinding } from "./testFixtures.js";

it("rejects a manifest without all physical groups", () => {
  const { base, ...incomplete } = manifestWithApprovedMotorBinding.groups;

  expect(() => parseModelManifest({ ...manifestWithApprovedMotorBinding, groups: incomplete })).toThrow(/base/);
});

it("rejects forged physical groups", () => {
  expect(() => parseModelManifest({
    ...manifestWithApprovedMotorBinding,
    groups: {
      ...manifestWithApprovedMotorBinding.groups,
      forged: { nodeNames: ["FORGED_01"], componentTag: null },
    },
  })).toThrow(/groups\.forged/);
});

it("rejects sensor coordinates while placement is unvalidated", () => {
  expect(() => parseModelManifest({
    ...manifestWithApprovedMotorBinding,
    sensors: [{ sensorId: "s1", placement: "unvalidated", position: [1, 2, 3] }],
  })).toThrow(/position/);
});

it("resolves only approved node bindings", () => {
  expect(componentTagForNode(manifestWithApprovedMotorBinding, "ME22A_CORPO")).toBe("CMP-MOTOR-VALIDATED");
  expect(componentTagForNode(manifestWithApprovedMotorBinding, "BOMBA_CORPO")).toBeNull();
});
