export const time = "2026-08-12T15:00:00Z";
export const dataset = { datasetId: "test-dataset", label: "Histórico de teste", pairCount: 7183, readingCount: 14366, startAt: time, endAt: time, sourceHash: "a".repeat(64), sourceFormat: "OOXML", guided: { startRow: 141, endRow: 440 } };
export function frame(sensorId = "s1", row = 141, extra = {}) {
  return { frameId: `${sensorId}-${row}`, sensorId, sourceRow: row, observedAt: time, receivedAt: time,
    measurements: { vibrationVelocityRms: { value: 0.4, unit: "mm/s", semanticConfidence: "confirmed" }, temperature: { value: 32, unit: "degC", semanticConfidence: "confirmed" }, vibrationAcceleration: { value: 0.03, unit: "g", statistic: "unknown", semanticConfidence: "unconfirmed" } },
    qualityFlags: [], gapBefore: false, preloaded: false, ...extra };
}
export function context(revision = 0, overrides = {}) {
  return { schemaVersion: "demo-1.0", assetId: "forzy-motor-01", mode: "replay", revision, generatedAt: time, status: "insufficient_data",
    replay: { runId: "test-run", generation: 0, state: "paused", scenario: "guided", speed: 1, cursor: 0, totalPairs: 300, startRow: 141, endRow: 440, sourceRow: null, sourceTime: null, arrivalTime: null, expiresAt: time, warmupPairs: 0 },
    dataset, sensors: { s1: { latest: null, assessment: null, assessmentState: "unavailable", newInformation: false }, s2: { latest: null, assessment: null, assessmentState: "unavailable", newInformation: false } }, history: [], events: [],
    pipeline: { receivedPairs: 0, receivedReadings: 0, newInformationReadings: 0, repeatedReadings: 0, gapCount: 0, assessmentsComputed: 0, eventsCreated: 0, lastAdvanceMs: null }, capabilities: { copilot: true, twin3d: true, replayControls: true }, ...overrides };
}
export function event(extra = {}) { return { eventId: "test-event", generation: 0, kind: "sustained_watch", sourceRow: 144, observedAt: time, receivedAt: time, contextRevision: 1, sensorIds: ["s1"], status: "pending", attempts: 0, retryable: false, recommendation: null, errorCode: null, ...extra }; }
export const deferred = () => { let resolve, reject; const promise = new Promise((res, rej) => { resolve = res; reject = rej; }); return { promise, resolve, reject }; };
