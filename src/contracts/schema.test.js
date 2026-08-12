import { readFileSync } from "node:fs";
import Ajv from "ajv";
import { describe, expect, it } from "vitest";

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));

describe("contracts/v1", () => {
  it("accepts canonical live telemetry and rejects numeric strings", () => {
    const ajv = new Ajv({ allErrors: true, strict: true });
    const validate = ajv.compile(json("../../contracts/v1/telemetry-sample.schema.json"));
    expect(validate(json("../../contracts/v1/fixtures/telemetry-live-s1.valid.json"))).toBe(true);
    expect(validate(json("../../contracts/v1/fixtures/telemetry-string.invalid.json"))).toBe(false);
  });
});
