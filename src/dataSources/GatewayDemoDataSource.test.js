import { expect, it, vi } from "vitest";
import { createGatewayDemoDataSource, parseDemoContext } from "./GatewayDemoDataSource.js";
import { context, frame } from "../demo/testFixtures.js";

it("parses the atomic context and preserves repeated frames", () => {
  const c = context(2, { replay: { ...context().replay, sourceRow: 142 }, history: [frame(), frame("s2"), frame("s1", 142), frame("s2", 142)] });
  expect(parseDemoContext(c)).toBe(c); expect(c.history).toHaveLength(4);
});
it.each([
  (c) => { c.revision = -1; },
  (c) => { c.replay.cursor = 301; },
  (c) => { c.history = [frame("s3")]; },
  (c) => { c.history = [frame()]; c.history[0].measurements.temperature.value = NaN; },
  (c) => { c.sensors.s1.latest = frame("s2"); },
  (c) => { c.replay.speed = 3; },
  (c) => { c.history = [frame("s1", 999)]; },
])("rejects invalid runtime contract %#", (alter) => { const c = context(); alter(c); expect(() => parseDemoContext(c)).toThrow(); });
it("sends opaque token only in authorization and preserves idempotency command ID", async () => {
  const fetchImpl = vi.fn(async () => ({ ok: true, json: async () => context() }));
  const source = createGatewayDemoDataSource({ fetchImpl }); const command = { commandId: "unchanged", expectedRevision: 1 };
  await source.advance({ runId: "a/b", token: "secret" }, command);
  expect(fetchImpl.mock.calls[0][0]).toBe("/api/demo/v1/runs/a%2Fb/advance");
  expect(fetchImpl.mock.calls[0][1]).toMatchObject({ cache: "no-store", headers: { Authorization: "Bearer secret" }, body: JSON.stringify(command) });
});
it("reports 409 without automatically resending the action", async () => {
  const fetchImpl = vi.fn(async () => ({ ok: false, status: 409 }));
  const source = createGatewayDemoDataSource({ fetchImpl });
  await expect(source.control({ runId: "x", token: "y" }, {})).rejects.toMatchObject({ status: 409 }); expect(fetchImpl).toHaveBeenCalledTimes(1);
});
it("rejects external gateway origins", () => { expect(() => createGatewayDemoDataSource({ baseUrl: "https://external.test" })).toThrow(); });
it("times out a hung telemetry request as a recoverable network failure", async () => {
  vi.useFakeTimers();
  const fetchImpl = vi.fn((_, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })))));
  const source = createGatewayDemoDataSource({ fetchImpl });
  const task = expect(source.context({ runId: "x", token: "y" })).rejects.toMatchObject({ status: null, name: "DemoGatewayError" });
  await vi.advanceTimersByTimeAsync(25000); await task; vi.useRealTimers();
});
