import { assertAssistantQueryResponse, createAssistantQueryRequest } from "../contracts/rag.js";

const statuses = ["normal", "watch", "alert", "insufficient_data", "unknown"];
const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const fail = () => { throw new TypeError("Resposta do histórico inválida."); };
const text = (value) => { if (typeof value !== "string" || !value.trim()) fail(); };
const integer = (value, minimum = 0) => { if (!Number.isSafeInteger(value) || value < minimum) fail(); };
const timestamp = (value, nullable = false) => {
  if (nullable && value === null) return;
  if (typeof value !== "string" || !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) fail();
};

export function parseHistoryDataset(value) {
  if (!record(value)) fail();
  ["datasetId", "label", "sourceFormat"].forEach((key) => text(value[key]));
  integer(value.pairCount); integer(value.readingCount);
  timestamp(value.startAt, value.pairCount === 0); timestamp(value.endAt, value.pairCount === 0);
  if (value.readingCount !== value.pairCount * 2 || Date.parse(value.startAt) > Date.parse(value.endAt)) fail();
  return value;
}

function parseFrame(value) {
  if (!record(value) || !["s1", "s2"].includes(value.sensorId) || value.receivedAt !== null || value.preloaded !== false) fail();
  text(value.frameId); integer(value.sourceRow, 1); timestamp(value.observedAt);
  if (!record(value.measurements) || !Array.isArray(value.qualityFlags)
    || value.qualityFlags.some((flag) => typeof flag !== "string") || typeof value.gapBefore !== "boolean") fail();
  for (const [key, unit] of [["temperature", "degC"], ["vibrationVelocityRms", "mm/s"], ["vibrationAcceleration", "g"]]) {
    const measurement = value.measurements[key];
    if (measurement !== null && (!record(measurement) || !Number.isFinite(measurement.value) || measurement.unit !== unit)) fail();
  }
  return value;
}

function parseAssessment(value) {
  if (value === null) return;
  if (!record(value) || !record(value.assessment) || !statuses.includes(value.assessment.status)
    || !Array.isArray(value.evidence) || !record(value.model)) fail();
  ["name", "version"].forEach((key) => text(value.model[key]));
  if (value.model.trainedUntil !== undefined) timestamp(value.model.trainedUntil);
  for (const key of ["anomalyScore", "deteriorationScore", "persistenceSeconds"]) {
    const number = value.assessment[key];
    if (number !== null && (!Number.isFinite(number) || number < 0)) fail();
  }
  value.evidence.forEach((evidence) => {
    if (!record(evidence) || !Number.isFinite(evidence.value)) fail();
    ["id", "feature", "unit"].forEach((key) => text(evidence[key]));
  });
}

export function parseHistoryContext(value) {
  if (!record(value) || value.schemaVersion !== "historical-1.0" || value.mode !== "historical"
    || value.assetId !== "forzy-motor-01" || !statuses.includes(value.status)) fail();
  text(value.revision); timestamp(value.generatedAt); parseHistoryDataset(value.dataset);
  if (value.capabilities?.twin3d !== true || typeof value.capabilities?.copilot !== "boolean" || value.capabilities?.replayControls !== false) fail();
  const selection = value.selection;
  if (!record(selection)) fail();
  timestamp(selection.from, true); timestamp(selection.to, true); timestamp(selection.observedAt);
  integer(selection.endRow, 1); integer(selection.totalPairs, 1); integer(selection.returnedPairs, 1); integer(selection.limit, 1);
  if (selection.limit > 300 || selection.returnedPairs > selection.limit || selection.returnedPairs > selection.totalPairs || selection.totalPairs > value.dataset.pairCount
    || (selection.from && selection.to && Date.parse(selection.from) > Date.parse(selection.to))) fail();
  for (const [flag, row] of [["hasPrevious", "previousEndRow"], ["hasNext", "nextEndRow"]]) {
    if (typeof selection[flag] !== "boolean") fail();
    if (selection[flag]) integer(selection[row], 1);
    else if (selection[row] !== null) fail();
  }
  if ((selection.hasPrevious && selection.previousEndRow >= selection.endRow)
    || (selection.hasNext && selection.nextEndRow <= selection.endRow)) fail();
  if (!Array.isArray(value.history) || value.history.length !== selection.returnedPairs * 2 || !record(value.sensors)) fail();
  let previousRow = 0;
  for (let index = 0; index < value.history.length; index += 2) {
    const first = parseFrame(value.history[index]), second = parseFrame(value.history[index + 1]);
    if (first.sourceRow <= previousRow || first.sourceRow !== second.sourceRow || first.sensorId === second.sensorId
      || first.observedAt !== second.observedAt || first.sourceRow > selection.endRow) fail();
    const at = Date.parse(first.observedAt);
    if (at < Date.parse(value.dataset.startAt) || at > Date.parse(value.dataset.endAt)
      || (selection.from && at < Date.parse(selection.from)) || (selection.to && at > Date.parse(selection.to))) fail();
    previousRow = first.sourceRow;
  }
  if (previousRow !== selection.endRow) fail();
  for (const id of ["s1", "s2"]) {
    const sensor = value.sensors[id];
    if (!record(sensor) || sensor.newInformation !== false || !["unavailable", "computed", "reused"].includes(sensor.assessmentState)) fail();
    const latest = parseFrame(sensor.latest);
    const lastFrame = value.history.slice(-2).find((frame) => frame.sensorId === id);
    if (latest.sensorId !== id || latest.sourceRow !== selection.endRow || latest.observedAt !== selection.observedAt
      || latest.frameId !== lastFrame?.frameId) fail();
    for (const key of ["temperature", "vibrationVelocityRms", "vibrationAcceleration"]) {
      if (latest.measurements[key]?.value !== lastFrame.measurements[key]?.value
        || latest.measurements[key]?.unit !== lastFrame.measurements[key]?.unit) fail();
    }
    parseAssessment(sensor.assessment);
  }
  return value;
}

const sameTime = (left, right) => left === null || right === null ? left === right : Date.parse(left) === Date.parse(right);

function parseAssistantSelection(value) {
  if (!record(value)) fail();
  timestamp(value.from, true); timestamp(value.to, true); integer(value.endRow, 1); integer(value.limit, 1);
  if (value.limit > 300 || (value.from && value.to && Date.parse(value.from) > Date.parse(value.to))) fail();
  return { from: value.from, to: value.to, endRow: value.endRow, limit: value.limit };
}

export function parseHistoricalAssistantResponse(value, expected) {
  if (!record(value) || value.schemaVersion !== "historical-assistant-1.0" || value.datasetId !== expected.datasetId
    || value.contextRevision !== expected.contextRevision) fail();
  const selection = parseAssistantSelection(value.selection), requested = parseAssistantSelection(expected.selection);
  timestamp(value.selection.observedAt);
  integer(value.selection.totalPairs, 1); integer(value.selection.returnedPairs, 1);
  if (value.selection.returnedPairs > selection.limit || value.selection.returnedPairs > value.selection.totalPairs) fail();
  for (const [flag, row] of [["hasPrevious", "previousEndRow"], ["hasNext", "nextEndRow"]]) {
    if (typeof value.selection[flag] !== "boolean") fail();
    if (value.selection[flag]) integer(value.selection[row], 1);
    else if (value.selection[row] !== null) fail();
  }
  if (selection.endRow !== requested.endRow || selection.limit !== requested.limit
    || !sameTime(selection.from, requested.from) || !sameTime(selection.to, requested.to)
    || (expected.selection.observedAt && !sameTime(value.selection.observedAt, expected.selection.observedAt))) fail();
  assertAssistantQueryResponse(value.response);
  if (value.response.citations.some((citation) => citation.type !== "manual")) fail();
  if (!Array.isArray(value.historicalEvidence) || value.historicalEvidence.length !== 2) fail();
  const seen = new Set();
  for (const sensor of value.historicalEvidence) {
    if (!record(sensor) || !["s1", "s2"].includes(sensor.sensorId) || seen.has(sensor.sensorId)
      || sensor.component !== (sensor.sensorId === "s1" ? "motor" : "bomba") || sensor.positionAssumed !== true
      || !statuses.includes(sensor.status) || !Array.isArray(sensor.qualityFlags) || sensor.qualityFlags.some((flag) => typeof flag !== "string")
      || "receivedAt" in sensor || "freshnessMs" in sensor) fail();
    seen.add(sensor.sensorId); text(sensor.qualityStatus); timestamp(sensor.observedAt);
    integer(sensor.sourceRow, 1);
    if (sensor.sourceRow !== selection.endRow || !sameTime(sensor.observedAt, value.selection.observedAt)) fail();
    if (sensor.assessmentId !== null) text(sensor.assessmentId);
    for (const key of ["windowStart", "windowEnd", "trainedUntil"]) timestamp(sensor[key], true);
    if (sensor.scoreSemantics !== null) text(sensor.scoreSemantics);
    for (const key of ["anomalyScore", "deteriorationScore", "persistenceSeconds"]) {
      if (sensor[key] != null && (!Number.isFinite(sensor[key]) || sensor[key] < 0)) fail();
    }
    if (Boolean(sensor.windowStart) !== Boolean(sensor.windowEnd)
      || (sensor.windowEnd && (Date.parse(sensor.windowEnd) > Date.parse(sensor.observedAt) || Date.parse(sensor.windowStart) > Date.parse(sensor.windowEnd)))) fail();
    if (!Array.isArray(sensor.evidence) || sensor.evidence.length > 50) fail();
    for (const evidence of sensor.evidence) {
      if (!record(evidence) || !Number.isFinite(evidence.value) || "receivedAt" in evidence || "freshnessMs" in evidence) fail();
      ["id", "feature", "unit"].forEach((key) => text(evidence[key]));
      if (evidence.windowSeconds !== null && (!Number.isFinite(evidence.windowSeconds) || evidence.windowSeconds < 0)) fail();
      for (const key of ["baseline", "deviation", "robustScale", "normalizedDistance", "anomalyScoreComponent", "positiveScoreComponent"]) {
        if (evidence[key] != null && !Number.isFinite(evidence[key])) fail();
      }
      if (evidence.direction != null && !["up", "down", "stable", "unknown"].includes(evidence.direction)) fail();
    }
  }
  return value;
}

export class HistoryGatewayError extends Error {
  constructor(status, code, message) { super(message); this.name = "HistoryGatewayError"; this.status = status; this.code = code; }
}

export function createGatewayHistoryDataSource({ baseUrl = "", fetchImpl = fetch } = {}) {
  if (typeof baseUrl !== "string" || (baseUrl !== "" && !/^\/(?!\/)[\w/-]*$/.test(baseUrl))) {
    throw new TypeError("O histórico exige a mesma origem.");
  }
  const root = `${baseUrl.replace(/\/$/, "")}/api/history/v1`;
  async function request(path, signal, parse, body) {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    if (signal?.aborted) cancel();
    signal?.addEventListener("abort", cancel, { once: true });
    const timer = setTimeout(cancel, body ? 45000 : 25000);
    try {
      const response = await fetchImpl(`${root}${path}`, { method: body ? "POST" : "GET", signal: controller.signal, cache: "no-store", credentials: "same-origin", redirect: "error", ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
      if (!response.ok) {
        let code;
        try { code = (await response.json())?.detail; } catch { /* Never display an upstream response body. */ }
        if (response.status === 400 && code === "historical_selection_empty") {
          throw new HistoryGatewayError(400, code, "Nenhum registro encontrado para o período selecionado.");
        }
        if (body && response.status === 409) throw new HistoryGatewayError(409, "historical_context_changed", "O contexto histórico mudou. Atualize a seleção antes de consultar novamente.");
        if (body && response.status === 503) throw new HistoryGatewayError(503, "historical_assistant_unavailable", "O manual ou o serviço de consulta histórica está indisponível no momento.");
        throw new HistoryGatewayError(response.status, "history_unavailable", {
          400: "Confira o período e o instante selecionados.",
          404: "Este conjunto histórico não foi encontrado.",
          503: "O histórico está indisponível no momento. Tente novamente.",
        }[response.status] ?? "Não foi possível consultar o histórico. Tente novamente.");
      }
      try { return parse(await response.json()); }
      catch { throw new HistoryGatewayError(response.status, "invalid_history", "A resposta do histórico não pôde ser validada. Tente novamente."); }
    } catch (error) {
      if (signal?.aborted) throw new DOMException("Consulta cancelada", "AbortError");
      if (error instanceof HistoryGatewayError) throw error;
      throw new HistoryGatewayError(null, "history_connection", "A conexão com o histórico foi interrompida. Tente novamente.");
    } finally { clearTimeout(timer); signal?.removeEventListener("abort", cancel); }
  }
  return Object.freeze({
    datasets: ({ signal } = {}) => request("/datasets", signal, (value) => {
      if (!Array.isArray(value?.datasets)) fail();
      value.datasets.forEach(parseHistoryDataset);
      if (new Set(value.datasets.map((dataset) => dataset.datasetId)).size !== value.datasets.length) fail();
      return value.datasets;
    }),
    context: (datasetId, { from = null, to = null, endRow = null, limit = 300 } = {}, { signal } = {}) => {
      text(datasetId); timestamp(from, true); timestamp(to, true); integer(limit, 1);
      if (limit > 300 || (from && to && Date.parse(from) > Date.parse(to))) fail();
      if (endRow !== null) integer(endRow, 1);
      const query = new URLSearchParams({ limit: String(limit) });
      if (from) query.set("from", from);
      if (to) query.set("to", to);
      if (endRow !== null) query.set("endRow", String(endRow));
      return request(`/datasets/${encodeURIComponent(datasetId)}/context?${query}`, signal, (value) => {
        const context = parseHistoryContext(value);
        if (context.dataset.datasetId !== datasetId || context.selection.returnedPairs > limit
          || (from && Date.parse(context.selection.from) !== Date.parse(from))
          || (to && Date.parse(context.selection.to) !== Date.parse(to))
          || (endRow !== null && context.selection.endRow > endRow)) fail();
        return context;
      });
    },
    query: (datasetId, input, { signal } = {}) => {
      text(datasetId); text(input?.contextRevision);
      const selection = parseAssistantSelection(input.selection);
      const normalized = createAssistantQueryRequest({ question: input.question, conversationId: input.conversationId, history: input.history ?? [] });
      const body = { ...normalized, selection, contextRevision: input.contextRevision };
      return request(`/datasets/${encodeURIComponent(datasetId)}/assistant/query`, signal,
        (value) => parseHistoricalAssistantResponse(value, { datasetId, contextRevision: input.contextRevision, selection }), body);
    },
  });
}
