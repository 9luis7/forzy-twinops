import { describe, expect, it } from "vitest";

import { buildExplanationRequest } from "./buildExplanationContext.js";

const snapshot = {
  assetTag: "MOTOR-01",
  history: [{ raw: { secret: true } }],
  assessment: {
    assessmentId: "assessment-1",
    assetTag: "MOTOR-01",
    assessment: { status: "watch" },
    evidence: [{ id: "ev-1", feature: "velocity", value: 1, unit: "mm/s" }],
  },
};

describe("buildExplanationRequest", () => {
  it("sends only the question, asset and assessment", () => {
    const request = buildExplanationRequest({ question: "O que mudou?", snapshot });

    expect(request).toEqual({
      question: "O que mudou?",
      assetTag: "MOTOR-01",
      assessment: snapshot.assessment,
    });
    expect(request).not.toHaveProperty("history");
    expect(JSON.stringify(request)).not.toContain("raw");
  });

  it("rejects snapshots without an assessment", () => {
    expect(() =>
      buildExplanationRequest({ question: "O que mudou?", snapshot: { assetTag: "MOTOR-01" } })
    ).toThrow("assessment");
  });
});
