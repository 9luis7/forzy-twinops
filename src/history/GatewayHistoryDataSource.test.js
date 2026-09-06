import { describe, expect, it, vi } from "vitest";
import { createGatewayHistoryDataSource, HistoryGatewayError, parseHistoryContext, parseHistoricalAssistantResponse } from "./GatewayHistoryDataSource.js";
import { assistantScope, historicalAnswer } from "./testFixtures.js";

export const at = (row) => new Date(Date.UTC(2026, 7, 12, 15, 0, row)).toISOString();
export const historyDataset = { datasetId: "history-real", label: "Histórico preservado", sourceFormat: "OOXML", pairCount: 4, readingCount: 8, startAt: at(1), endAt: at(4) };
export function historicalContext(endRow = 4) {
  const history = [endRow - 1, endRow].flatMap((sourceRow) => ["s1", "s2"].map((sensorId) => ({
    frameId: `${sensorId}-${sourceRow}`, sensorId, sourceRow, observedAt: at(sourceRow), receivedAt: null, gapBefore: false, preloaded: false, qualityFlags: [],
    measurements: { vibrationVelocityRms: { value: sourceRow / 10, unit: "mm/s" }, temperature: { value: 32, unit: "degC" }, vibrationAcceleration: { value: 0, unit: "g" } },
  })));
  return {
    schemaVersion: "historical-1.0", mode: "historical", assetId: "forzy-motor-01", revision: `history-${endRow}`, dataset: historyDataset,
    selection: { from: null, to: null, endRow, limit: 300, observedAt: at(endRow), totalPairs: 4, returnedPairs: 2, hasPrevious: endRow > 2, previousEndRow: endRow > 2 ? 2 : null, hasNext: endRow < 4, nextEndRow: endRow < 4 ? 4 : null },
    sensors: Object.fromEntries(["s1", "s2"].map((id) => [id, { latest: history.findLast((frame) => frame.sensorId === id), assessment: null, assessmentState: "unavailable", newInformation: false }])),
    history, status: "insufficient_data", generatedAt: at(4), capabilities: { twin3d: true, copilot: false, replayControls: false },
  };
}
const response = (value, status = 200) => ({ ok: status === 200, status, json: async () => value });

describe("historical gateway", () => {
  it("only reads same-origin endpoints and preserves timezone and window parameters", async () => {
    const context = historicalContext(); context.selection.from = "2026-08-12T15:00:01Z";
    const fetchImpl = vi.fn().mockResolvedValueOnce(response({ datasets: [historyDataset] })).mockResolvedValueOnce(response(context));
    const source = createGatewayHistoryDataSource({ fetchImpl });
    expect(await source.datasets()).toEqual([historyDataset]);
    await source.context(historyDataset.datasetId, { from: "2026-08-12T12:00:01-03:00", endRow: 4 });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(fetchImpl.mock.calls[0][0]).toBe("/api/history/v1/datasets");
    const query = new URL(fetchImpl.mock.calls[1][0], "https://example.invalid");
    expect(query.searchParams.get("from")).toBe("2026-08-12T12:00:01-03:00");
    expect(query.searchParams.get("endRow")).toBe("4");
    expect(query.searchParams.get("limit")).toBe("300");
    fetchImpl.mock.calls.forEach(([, options]) => expect(options).toMatchObject({ method: "GET", cache: "no-store", credentials: "same-origin", redirect: "error" }));
    expect(Object.keys(source).sort()).toEqual(["context", "datasets", "query"]);
    expect(() => createGatewayHistoryDataSource({ baseUrl: "https://external.invalid" })).toThrow(/mesma origem/);
    expect(() => createGatewayHistoryDataSource({ baseUrl: "//external.invalid" })).toThrow(/mesma origem/);
  });

  it.each([
    (value) => { value.mode = "replay"; },
    (value) => { value.revision = 4; },
    (value) => { value.selection.returnedPairs = 301; },
    (value) => { value.history[0].receivedAt = at(1); },
    (value) => { value.history[0].preloaded = true; },
    (value) => { value.history[0].observedAt = "2026-08-12T15:00:03"; },
    (value) => { value.history[0].sensorId = "s2"; },
    (value) => { value.sensors.s1.latest = value.history[0]; },
    (value) => { value.capabilities.replayControls = true; },
    (value) => { value.sensors.s1.newInformation = true; },
  ])("rejects a replay, malformed window, or inconsistent sensor snapshot", (mutate) => {
    const value = structuredClone(historicalContext()); mutate(value);
    expect(() => parseHistoryContext(value)).toThrow(/histórico inválida/);
  });

  it("reports an empty filter safely and never forwards arbitrary upstream details", async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(response({ detail: "historical_selection_empty" }, 400)).mockResolvedValueOnce(response({ detail: "postgres://private-secret" }, 503));
    const source = createGatewayHistoryDataSource({ fetchImpl });
    await expect(source.context(historyDataset.datasetId)).rejects.toMatchObject({ name: "HistoryGatewayError", code: "historical_selection_empty", message: "Nenhum registro encontrado para o período selecionado." });
    await expect(source.context(historyDataset.datasetId)).rejects.toMatchObject({ status: 503, message: "O histórico está indisponível no momento. Tente novamente." });
  });

  it("accepts an explicitly empty dataset catalogue entry without inventing dates", async () => {
    const empty = { ...historyDataset, pairCount: 0, readingCount: 0, startAt: null, endAt: null };
    const source = createGatewayHistoryDataSource({ fetchImpl: vi.fn().mockResolvedValue(response({ datasets: [empty] })) });
    expect(await source.datasets()).toEqual([empty]);
  });

  it("wraps invalid successful responses in a typed, safe error", async () => {
    const source = createGatewayHistoryDataSource({ fetchImpl: vi.fn().mockResolvedValue(response({ mode: "replay" })) });
    await expect(source.context(historyDataset.datasetId)).rejects.toBeInstanceOf(HistoryGatewayError);
  });

  it("refuses a valid-looking response for a different period than requested", async () => {
    const source = createGatewayHistoryDataSource({ fetchImpl: vi.fn().mockResolvedValue(response(historicalContext())) });
    await expect(source.context(historyDataset.datasetId, { from: at(3) })).rejects.toMatchObject({ code: "invalid_history" });
  });
});

describe("historical manual consultation", () => {
  it("posts only after an explicit query and pins the existing selected revision", async () => {
    const scope = assistantScope(), answer = historicalAnswer(scope), fetchImpl = vi.fn().mockResolvedValue(response(answer));
    const source = createGatewayHistoryDataSource({ fetchImpl });
    expect(fetchImpl).not.toHaveBeenCalled();
    const input = { question: "Como verificar o motor?", contextRevision: scope.revision, selection: { from: null, to: null, endRow: 4, limit: 300 }, history: [] };
    expect(await source.query("history-test", input)).toEqual(answer);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, options] = fetchImpl.mock.calls[0];
    expect(url).toBe("/api/history/v1/datasets/history-test/assistant/query");
    expect(options.method).toBe("POST"); expect(JSON.parse(options.body)).toEqual(input);
  });

  it.each([
    (value) => { value.contextRevision = "f".repeat(64); },
    (value) => { value.datasetId = "another-dataset"; },
    (value) => { value.selection = { ...value.selection, endRow: 3 }; },
    (value) => { value.selection = { ...value.selection, limit: 30 }; },
    (value) => { value.selection = { ...value.selection, from: at(1) }; },
    (value) => { value.historicalEvidence[0].receivedAt = at(4); },
    (value) => { value.historicalEvidence[0].freshnessMs = 0; },
    (value) => { value.historicalEvidence[0].sourceRow = 3; },
    (value) => { value.historicalEvidence[1].sensorId = "s1"; },
  ])("rejects a mismatched scope or simulated arrival in historical evidence", (mutate) => {
    const scope = assistantScope(), answer = structuredClone(historicalAnswer(scope)); mutate(answer);
    expect(() => parseHistoricalAssistantResponse(answer, { datasetId: scope.dataset.datasetId, contextRevision: scope.revision, selection: scope.selection })).toThrow();
  });

  it("keeps documentary grounding status unchanged when historical evidence is separate", () => {
    const scope = assistantScope(), answer = historicalAnswer(scope); answer.response.groundingStatus = "operational_unavailable";
    const parsed = parseHistoricalAssistantResponse(answer, { datasetId: scope.dataset.datasetId, contextRevision: scope.revision, selection: scope.selection });
    expect(parsed.response.groundingStatus).toBe("operational_unavailable");
  });
});
