import { describe, expect, it } from "vitest";
import { buildTwinViewModel } from "./twinViewModel.js";
import { alertSnapshot, normalSnapshot } from "./testFixtures.js";


describe("buildTwinViewModel", () => {
  it("derives a single global material treatment from snapshot status", () => {
    const normal = buildTwinViewModel({ snapshot: normalSnapshot });
    const alert = buildTwinViewModel({ snapshot: alertSnapshot });

    expect(normal.status).toBe("normal");
    expect(alert.status).toBe("alert");
    expect(alert.materialColor).not.toBe(normal.materialColor);
    expect(alert.emissiveIntensity).toBeGreaterThan(normal.emissiveIntensity);
  });

  it("does not expose component or sensor node bindings", () => {
    const viewModel = buildTwinViewModel({ snapshot: alertSnapshot });

    expect(viewModel).not.toHaveProperty("highlightedNodeNames");
    expect(viewModel).not.toHaveProperty("activeNodeNames");
    expect(viewModel).not.toHaveProperty("channels");
  });
});
