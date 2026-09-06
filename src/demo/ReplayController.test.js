import { afterEach, expect, it, vi } from "vitest";
import { ReplayController } from "./ReplayController.js";
import { context, dataset, deferred, event } from "./testFixtures.js";

const controllers = [];
afterEach(() => { controllers.forEach((c) => c.dispose()); controllers.length = 0; vi.useRealTimers(); });
function setup() {
  const source = { datasets: vi.fn(async () => [dataset]), create: vi.fn(async () => ({ runId: "test-run", token: "secret", context: context() })), context: vi.fn(async () => context()), control: vi.fn(async () => context(1)), advance: vi.fn(async () => context(2)), recommend: vi.fn(async () => event()), query: vi.fn() };
  const storage = { getItem: vi.fn(), setItem: vi.fn() };
  const c = new ReplayController(source, { storage }); controllers.push(c);
  return { c, source, storage };
}
it("keeps run/token in tab storage and never embeds the token in context", async () => {
  const { c, storage } = setup(); await c.create(dataset.datasetId);
  expect(storage.setItem).toHaveBeenCalledWith("twinops.demo.session.v1", JSON.stringify({ runId: "test-run", token: "secret" }));
  expect(c.state.context.token).toBeUndefined();
});
it("invokes browser timer defaults with globalThis as their native receiver", async () => {
  const interval = vi.spyOn(globalThis, "setInterval").mockImplementation(function () {
    expect(this).toBe(globalThis); return 12345;
  });
  const clear = vi.spyOn(globalThis, "clearInterval").mockImplementation(function (id) {
    expect(this).toBe(globalThis); expect(id).toBe(12345);
  });
  try {
    const { c } = setup(); await c.start(); expect(interval).toHaveBeenCalledTimes(1);
    c.dispose(); expect(clear).toHaveBeenCalledTimes(1); c.timer = undefined;
  } finally { interval.mockRestore(); clear.mockRestore(); }
});
it("advances on a one-second timer with at most one request in flight", async () => {
  vi.useFakeTimers(); const { c, source } = setup(); await c.start(); await c.create(dataset.datasetId);
  c.accept(context(1, { replay: { ...context().replay, state: "running" } }), c.epoch);
  const pending = deferred(); source.advance.mockReturnValue(pending.promise);
  await vi.advanceTimersByTimeAsync(5000); expect(source.advance).toHaveBeenCalledTimes(1);
  pending.resolve(context(2)); await pending.promise; await Promise.resolve();
  expect(c.state.busy).toBe(false);
});
it("rejects stale revisions and previous generation responses", async () => {
  const { c } = setup(); await c.create(dataset.datasetId);
  c.accept(context(8, { replay: { ...context().replay, generation: 2 } }), c.epoch);
  expect(c.accept(context(7, { replay: { ...context().replay, generation: 2 } }), c.epoch)).toBe(false);
  expect(c.accept(context(9), c.epoch)).toBe(false); expect(c.state.context.revision).toBe(8);
});
it("reloads conflict context without replaying the rejected action", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  source.control.mockRejectedValue(Object.assign(new Error("conflict"), { status: 409 })); source.context.mockResolvedValue(context(9));
  await c.command("step"); expect(source.control).toHaveBeenCalledTimes(1); expect(c.context.revision).toBe(9); expect(c.state.suspended).toBe(true);
});
it("reconnection confirms current state without retrying an ambiguous advance", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  source.advance.mockRejectedValue(new Error("network")); await c.transact("advance");
  source.context.mockResolvedValue(context(2)); await c.refresh();
  expect(source.advance).toHaveBeenCalledTimes(1); expect(c.context.revision).toBe(2); expect(c.state.error).toBeNull(); expect(c.state.suspended).toBe(true);
});
it("ignores an old pending advance after creating another session", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  const pending = deferred(); source.advance.mockReturnValue(pending.promise); const task = c.transact("advance");
  await c.create(dataset.datasetId); pending.resolve(context(99)); await task;
  expect(c.context.revision).toBe(0); expect(c.state.busy).toBe(false);
});
it("queues pause during advance, stops ticks immediately and applies once on the committed revision", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  c.accept(context(1, { replay: { ...context().replay, state: "running" } }), c.epoch);
  const pending = deferred(); source.advance.mockReturnValue(pending.promise); c.tick();
  const pause = c.command("pause"); const duplicate = c.command("pause");
  expect(duplicate).toBe(pause); expect(c.state.queuedAction).toBe("pause"); expect(c.state.suspended).toBe(true);
  c.tick(); c.tick(); expect(source.advance).toHaveBeenCalledTimes(1); expect(source.control).not.toHaveBeenCalled();
  source.control.mockResolvedValue(context(3));
  pending.resolve(context(2, { replay: { ...context().replay, state: "running", cursor: 1 } })); await pause;
  expect(source.control).toHaveBeenCalledTimes(1); expect(source.control.mock.calls[0][1]).toMatchObject({ action: "pause", expectedRevision: 2 });
  c.tick(); expect(source.advance).toHaveBeenCalledTimes(1); expect(c.state.queuedAction).toBeNull(); expect(c.context.replay.state).toBe("paused");
});
it("queues restart during advance and rejects any earlier-generation snapshot after effective restart", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  c.accept(context(1, { replay: { ...context().replay, state: "running" } }), c.epoch);
  const pending = deferred(); source.advance.mockReturnValue(pending.promise); c.tick();
  const restart = c.command("restart");
  source.control.mockResolvedValue(context(3, { replay: { ...context().replay, generation: 1 } }));
  const advanced = context(2, { replay: { ...context().replay, state: "running", cursor: 5 }, events: [event()] });
  pending.resolve(advanced); await restart;
  expect(source.control.mock.calls[0][1]).toMatchObject({ action: "restart", expectedRevision: 2 });
  expect(c.context.replay).toMatchObject({ generation: 1, cursor: 0, state: "paused" });
  expect(c.accept(advanced, c.epoch)).toBe(false); expect(c.state.events).toEqual([]); expect(c.context.replay.cursor).toBe(0);
});
it("refetches an ambiguous advance before applying the queued restart once", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  const pending = deferred(); source.advance.mockReturnValue(pending.promise); c.transact("advance");
  const restart = c.command("restart"); source.context.mockResolvedValue(context(7));
  source.control.mockResolvedValue(context(8, { replay: { ...context().replay, generation: 1 } }));
  pending.reject(new Error("network interrupted")); await restart;
  expect(source.context).toHaveBeenCalledTimes(1); expect(source.advance).toHaveBeenCalledTimes(1);
  expect(source.control).toHaveBeenCalledTimes(1); expect(source.control.mock.calls[0][1].expectedRevision).toBe(7);
});
it("invalidates a queued restart when a new session replaces the pending advance", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  const pending = deferred(); source.advance.mockReturnValue(pending.promise); c.transact("advance");
  const restart = c.command("restart"); await c.create(dataset.datasetId);
  pending.resolve(context(9)); await restart;
  expect(source.control).not.toHaveBeenCalled(); expect(c.context.revision).toBe(0); expect(c.state.queuedAction).toBeNull();
});
it("does not send a queued action if the committed revision cannot be recovered", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  const pending = deferred(); source.advance.mockReturnValue(pending.promise); c.transact("advance");
  const pause = c.command("pause"); source.context.mockRejectedValue(new Error("reconnect required"));
  pending.reject(new Error("network interrupted")); await pause;
  expect(source.control).not.toHaveBeenCalled(); expect(c.state.error).toBe("reconnect required"); expect(c.state.suspended).toBe(true);
});
it("automatic recommendation does not block telemetry and has one pending request", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  c.accept(context(1, { events: [event()], replay: { ...context().replay, state: "running" } }), c.epoch);
  const pending = deferred(); source.recommend.mockReturnValue(pending.promise);
  c.tick(); c.tick(); expect(source.recommend).toHaveBeenCalledTimes(1); expect(source.advance).toHaveBeenCalledTimes(1);
  pending.resolve(event({ status: "ready" })); await pending.promise;
});
it("exposes only request identity while telemetry advances, then clears it on completion", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  c.accept(context(1, { events: [event()] }), c.epoch);
  const pending = deferred(); source.recommend.mockReturnValue(pending.promise);
  const request = c.recommendNext();
  expect(c.state.recommendationPending).toEqual({ eventId: "test-event", generation: 0 });
  expect(c.state.events[0]).toMatchObject({ status: "pending", attempts: 0 });
  source.advance.mockResolvedValue(context(2, { events: [event()] }));
  await c.transact("advance");
  expect(c.context.revision).toBe(2); expect(c.state.recommendationPending?.eventId).toBe("test-event");
  expect(source.recommend).toHaveBeenCalledTimes(1);
  pending.resolve(event({ status: "ready", attempts: 1 })); await request;
  expect(c.state.recommendationPending).toBeNull(); expect(c.state.events[0].status).toBe("ready");
});
it("clears request feedback on error without fabricating a backend status", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId); c.accept(context(1, { events: [event()] }), c.epoch);
  source.recommend.mockRejectedValue(new Error("interrupted")); await c.recommendNext();
  expect(c.state.recommendationPending).toBeNull(); expect(c.state.events[0].status).toBe("pending");
  expect(c.state.assistantError).toMatch(/pendente/);
});
it("does not let an old session request clear the new request feedback when abort is ignored", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId); c.accept(context(1, { events: [event()] }), c.epoch);
  const old = deferred(), next = deferred(); source.recommend.mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
  const oldRequest = c.recommendNext(); const oldSignal = source.recommend.mock.calls[0][2].signal;
  await c.create(dataset.datasetId); expect(oldSignal.aborted).toBe(true); expect(c.state.recommendationPending).toBeNull();
  c.accept(context(1, { events: [event({ eventId: "next-event" })] }), c.epoch);
  const nextRequest = c.recommendNext();
  old.resolve(event({ status: "ready" })); await oldRequest;
  expect(c.state.recommendationPending?.eventId).toBe("next-event");
  next.resolve(event({ eventId: "next-event", status: "ready" })); await nextRequest;
  expect(c.state.recommendationPending).toBeNull();
});
it("clears request feedback on disposal even if the transport ignores abort", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId); c.accept(context(1, { events: [event()] }), c.epoch);
  const pending = deferred(); source.recommend.mockReturnValue(pending.promise); const request = c.recommendNext();
  c.dispose(); expect(source.recommend.mock.calls[0][2].signal.aborted).toBe(true);
  expect(c.state.recommendationPending).toBeNull();
  pending.resolve(event({ status: "ready" })); await request;
  expect(c.state.events[0].status).toBe("pending"); expect(c.state.recommendationPending).toBeNull();
});
it("accepts a newer processing attempt over an old cached retryable pending result", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId); c.accept(context(1, { events: [event()] }), c.epoch);
  source.recommend.mockResolvedValue(event({ status: "pending", attempts: 1, retryable: true })); await c.recommendNext();
  const processing = event({ status: "processing", attempts: 2 });
  c.accept(context(2, { events: [processing] }), c.epoch);
  expect(c.state.events[0]).toBe(processing);
  c.accept(context(3, { events: [event({ status: "pending", attempts: 1, retryable: true })] }), c.epoch);
  expect(c.state.events[0]).toBe(processing);
  const completedAttempt = event({ status: "pending", attempts: 2, retryable: true });
  c.accept(context(4, { events: [completedAttempt] }), c.epoch);
  expect(c.state.events[0]).toBe(completedAttempt);
});
it("does not regress processing when an older pending POST response arrives late", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId); c.accept(context(1, { events: [event()] }), c.epoch);
  const pending = deferred(); source.recommend.mockReturnValue(pending.promise); const request = c.recommendNext();
  const processing = event({ status: "processing", attempts: 2 }); c.accept(context(2, { events: [processing] }), c.epoch);
  pending.resolve(event({ status: "pending", attempts: 1, retryable: true })); await request;
  expect(c.state.events[0]).toBe(processing); expect(c.state.recommendationPending).toBeNull();
});
it("backs off processing/transient recommendations and preserves terminal responses across context refresh", async () => {
  vi.useFakeTimers(); const { c, source } = setup(); await c.create(dataset.datasetId);
  c.accept(context(1, { events: [event()] }), c.epoch);
  source.recommend.mockResolvedValueOnce(event({ status: "processing" })).mockResolvedValueOnce(event({ status: "ready" }));
  await c.recommendNext(); await c.recommendNext(); expect(source.recommend).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(5000); await c.recommendNext();
  c.accept(context(2, { events: [event()] }), c.epoch);
  expect(c.state.events[0].status).toBe("ready");
});
it("anchors a delayed manual response to its original revision", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  const pending = deferred(); source.query.mockReturnValue(pending.promise); const task = c.query("Por quê?");
  c.accept(context(3), c.epoch); pending.resolve({ contextRevision: 0, sourceRow: 141, response: {} }); await task;
  expect(c.state.answers[0].contextRevision).toBe(0); expect(c.context.revision).toBe(3);
});
it("accepts a terminal server event over an older local processing result", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId); c.accept(context(1, { events: [event()] }), c.epoch);
  source.recommend.mockResolvedValue(event({ status: "processing" })); await c.recommendNext();
  c.accept(context(2, { events: [event({ status: "ready" })] }), c.epoch);
  expect(c.state.events[0].status).toBe("ready");
});
it("clears an old manual inflight lock immediately on new session even if abort is ignored", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId);
  const pending = deferred(); source.query.mockReturnValue(pending.promise); c.query("Anterior");
  await c.create(dataset.datasetId); expect(c.state.manualPending).toBe(false);
  source.query.mockResolvedValue({ contextRevision: 0 }); await c.query("Nova");
  expect(c.state.answers[0].question).toBe("Nova");
  pending.resolve({ contextRevision: 0 }); await pending.promise; expect(c.state.answers).toHaveLength(1);
});
it("discards a recommendation from the previous generation after restart", async () => {
  const { c, source } = setup(); await c.create(dataset.datasetId); c.accept(context(1, { events: [event()] }), c.epoch);
  const pending = deferred(); source.recommend.mockReturnValue(pending.promise); const task = c.recommendNext();
  source.control.mockResolvedValue(context(2, { replay: { ...context().replay, generation: 1 } })); await c.command("restart");
  expect(c.state.recommendationPending).toBeNull(); expect(source.recommend.mock.calls[0][2].signal.aborted).toBe(true);
  pending.resolve(event({ status: "ready" })); await task; expect(c.state.events).toEqual([]);
  expect(c.state.recommendationPending).toBeNull();
});
it("pauses on visibility loss and requires explicit continue when visible", async () => {
  const { c, source } = setup(); let handler; c.document = { hidden: false, addEventListener: (_, cb) => { handler = cb; }, removeEventListener: vi.fn() };
  await c.start(); await c.create(dataset.datasetId); c.accept(context(1, { replay: { ...context().replay, state: "running" } }), c.epoch);
  c.document.hidden = true; handler(); await Promise.resolve(); await Promise.resolve();
  expect(source.control.mock.calls[0][1].action).toBe("pause");
  c.document.hidden = false; handler(); c.tick(); expect(c.state.suspended).toBe(true); expect(source.advance).not.toHaveBeenCalled();
});
it.each([
  ["play", false], ["play", true], ["resume", false], ["resume", true],
])("preserves visibility suspension for pending %s (visible before response: %s)", async (action, visibleFirst) => {
  const { c, source } = setup(); let visibility;
  c.document = { hidden: false, addEventListener: (_, handler) => { visibility = handler; }, removeEventListener: vi.fn() };
  await c.start(); await c.create(dataset.datasetId);
  const pending = deferred(); source.control.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(context(2));
  const requested = c.command(action);
  c.document.hidden = true; visibility();
  if (visibleFirst) { c.document.hidden = false; visibility(); }
  pending.resolve(context(1, { replay: { ...context().replay, state: "running" } }));
  await requested; await c.inflight;
  if (!visibleFirst) { c.document.hidden = false; visibility(); }
  c.tick(); expect(c.state.suspended).toBe(true); expect(source.advance).not.toHaveBeenCalled();
  expect(source.control).toHaveBeenCalledTimes(2); expect(source.control.mock.calls[1][1]).toMatchObject({ action: "pause", expectedRevision: 1 });
  source.control.mockResolvedValue(context(3, { replay: { ...context().replay, state: "running" } }));
  await c.command("resume"); expect(c.state.suspended).toBe(false); c.tick(); expect(source.advance).toHaveBeenCalledTimes(1);
});
it.each(["ready", "degraded"])("preserves %s recommendation when an older processing response arrives late", async (status) => {
  const { c, source } = setup(); await c.create(dataset.datasetId); c.accept(context(1, { events: [event()] }), c.epoch);
  const pending = deferred(); source.recommend.mockReturnValue(pending.promise); const request = c.recommendNext();
  const terminal = event({ status, recommendation: { answer: "immutable terminal response" } });
  c.accept(context(2, { events: [terminal] }), c.epoch);
  pending.resolve(event({ status: "processing" })); await request;
  expect(c.state.events[0]).toBe(terminal); expect(c.eventResults.get(terminal.eventId)).toBe(terminal);
  c.accept(context(3, { events: [event({ status: "processing" })] }), c.epoch);
  expect(c.state.events[0]).toBe(terminal); await c.recommendNext(); expect(source.recommend).toHaveBeenCalledTimes(1);
});
it.each([{ eventId: "different-event" }, { generation: 5 }])("rejects mismatched recommendation identity %o", async (override) => {
  const { c, source } = setup(); await c.create(dataset.datasetId); c.accept(context(1, { events: [event()] }), c.epoch);
  source.recommend.mockResolvedValue(event({ status: "processing", ...override })); await c.recommendNext();
  expect(c.state.events[0].status).toBe("pending"); expect(c.eventResults.size).toBe(0);
});
