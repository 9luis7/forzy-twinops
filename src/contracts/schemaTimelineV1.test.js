import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  assertCollectionPolicyV1,
  createTimelineAjvV1,
} from "./timelineV1.js";

const names = [
  "historical-sensor-reading",
  "timeline-point",
  "historical-assessment",
  "collection-policy",
  "timeline-event-candidate",
  "timeline-overview",
  "timeline-page",
  "timeline-decision-facts",
  "timeline-context",
];

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const timelineSchemas = () => names.map((name) => json(`../../contracts/timeline/v1/${name}.schema.json`));
const assessmentSchema = () => json("../../contracts/v2/asset-condition-assessment.schema.json");
const fixture = (name) => json(`../../contracts/timeline/v1/fixtures/${name}`);

const visit = (value, callback, path = "$") => {
  if (!value || typeof value !== "object") return;
  callback(value, path);
  if (Array.isArray(value)) {
    value.forEach((child, index) => visit(child, callback, `${path}[${index}]`));
    return;
  }
  Object.entries(value).forEach(([key, child]) => visit(child, callback, `${path}.${key}`));
};

describe("Timeline v1 draft-07 schema contract", () => {
  it("registers every unique absolute id and compiles all roots with cross-schema refs", () => {
    const schemas = timelineSchemas();
    const ajv = createTimelineAjvV1({
      timelineSchemas: schemas,
      assetAssessmentSchema: assessmentSchema(),
    });
    expect(new Set(schemas.map((schema) => schema.$id)).size).toBe(schemas.length);
    for (const schema of schemas) {
      expect(schema.$schema).toBe("http://json-schema.org/draft-07/schema#");
      expect(schema.$id).toMatch(/^forzy:\/\/contracts\/timeline\/v1\/[a-z0-9-]+$/);
      expect(ajv.getSchema(schema.$id)).toBeTypeOf("function");
    }
    expect(() => ajv.getSchema("forzy://contracts/timeline/v1/timeline-context")(
      fixture("context-historical-gap.valid.json"),
    )).not.toThrow();
  });

  it("uses draft-07 definitions and closes every concrete object", () => {
    for (const schema of timelineSchemas()) {
      visit(schema, (node, path) => {
        expect(node, `${schema.$id}:${path}`).not.toHaveProperty("$defs");
        const isNarrowingPredicate = path.includes(".oneOf[") || path.includes(".allOf[");
        if (node.type === "object" && !isNarrowingPredicate) {
          expect(node.additionalProperties, `${schema.$id}:${path}`).toBe(false);
        }
      });
    }
  });

  it("fails on duplicate ids and unresolved absolute references", () => {
    const duplicate = timelineSchemas();
    duplicate.push(structuredClone(duplicate[0]));
    expect(() => createTimelineAjvV1({
      timelineSchemas: duplicate,
      assetAssessmentSchema: assessmentSchema(),
    })).toThrow(/duplicate/i);

    const unresolved = timelineSchemas();
    const context = unresolved.find((schema) => schema.$id.endsWith("timeline-context"));
    context.properties.anchor = { $ref: "forzy://contracts/timeline/v1/missing" };
    expect(() => createTimelineAjvV1({
      timelineSchemas: unresolved,
      assetAssessmentSchema: assessmentSchema(),
    })).toThrow(/unresolved/i);
  });

  it("keeps draft-07 structural validation separate from composed invariants", () => {
    const ajv = createTimelineAjvV1({
      timelineSchemas: timelineSchemas(),
      assetAssessmentSchema: assessmentSchema(),
    });
    const barePolicy = ajv.getSchema("forzy://contracts/timeline/v1/collection-policy");
    const invalidInterval = fixture("collection-policy.valid.json");
    invalidInterval.effectiveTo = "2026-08-21T23:59:59.999Z";

    expect(barePolicy(invalidInterval)).toBe(true);
    expect(() => assertCollectionPolicyV1(invalidInterval)).toThrow();
  });

  it("does not coerce values, apply defaults, or remove extra keys", () => {
    const ajv = createTimelineAjvV1({
      timelineSchemas: timelineSchemas(),
      assetAssessmentSchema: assessmentSchema(),
    });
    const validate = ajv.getSchema("forzy://contracts/timeline/v1/timeline-point");
    const numericString = fixture("live-point.valid.json");
    numericString.measurements.temperature.value = "30";
    expect(validate(numericString)).toBe(false);
    expect(numericString.measurements.temperature.value).toBe("30");

    const missing = fixture("live-point.valid.json");
    delete missing.qualityFlags;
    expect(validate(missing)).toBe(false);
    expect(missing).not.toHaveProperty("qualityFlags");

    const extra = fixture("live-point.valid.json");
    extra.measurements.temperature.unexpected = true;
    expect(validate(extra)).toBe(false);
    expect(extra.measurements.temperature).toHaveProperty("unexpected", true);
  });
});
