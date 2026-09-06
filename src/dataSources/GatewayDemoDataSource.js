import { assertAssistantQueryResponse } from "../contracts/rag.js";

const statuses = ["normal", "watch", "alert", "insufficient_data", "unknown"];
const record = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const fail = (key) => { throw new TypeError(`Resposta demo inválida: ${key}`); };
const integer = (v, key) => { if (!Number.isInteger(v) || v < 0) fail(key); };
const timestamp = (v, key, nullable = false) => {
  if (nullable && v === null) return;
  if (typeof v !== "string" || !v.endsWith("Z") || !Number.isFinite(Date.parse(v))) fail(key);
};
const text = (v, key) => { if (typeof v !== "string" || !v.length) fail(key); };

export function parseDemoDataset(v) {
  if (!record(v)) fail("dataset");
  for (const key of ["datasetId", "label", "sourceHash", "sourceFormat"]) text(v[key], key);
  for (const key of ["pairCount", "readingCount"]) integer(v[key], key);
  if (v.readingCount !== v.pairCount * 2 || !/^(sha256:)?[a-f0-9]{64}$/.test(v.sourceHash)) fail("dataset provenance");
  timestamp(v.startAt, "startAt"); timestamp(v.endAt, "endAt");
  return v;
}

export function parseDemoFrame(v) {
  if (!record(v) || !["s1", "s2"].includes(v.sensorId)) fail("frame");
  text(v.frameId, "frameId"); integer(v.sourceRow, "sourceRow");
  timestamp(v.observedAt, "observedAt"); timestamp(v.receivedAt, "receivedAt");
  if (!record(v.measurements) || !Array.isArray(v.qualityFlags)
      || v.qualityFlags.some((flag) => typeof flag !== "string")
      || typeof v.gapBefore !== "boolean" || typeof v.preloaded !== "boolean") fail("frame metadata");
  for (const [key, unit] of [["temperature", "degC"], ["vibrationVelocityRms", "mm/s"], ["vibrationAcceleration", "g"]]) {
    const value = v.measurements[key];
    if (value !== null && (!record(value) || !Number.isFinite(value.value) || value.unit !== unit)) fail(key);
  }
  return v;
}

export function parseDemoEvent(v) {
  if (!record(v)) fail("event");
  text(v.eventId, "eventId");
  for (const key of ["generation", "sourceRow", "contextRevision", "attempts"]) integer(v[key], key);
  timestamp(v.observedAt, "event.observedAt"); timestamp(v.receivedAt, "event.receivedAt");
  if (!["sustained_watch", "escalation", "recovery"].includes(v.kind)
    || !["pending", "processing", "ready", "degraded"].includes(v.status)
    || !Array.isArray(v.sensorIds) || v.sensorIds.some((id) => !["s1", "s2"].includes(id))
    || typeof v.retryable !== "boolean") fail("event state");
  if (v.recommendation !== null) assertAssistantQueryResponse(v.recommendation);
  return v;
}

export function parseDemoContext(v) {
  if (!record(v) || v.schemaVersion !== "demo-1.0" || v.assetId !== "forzy-motor-01"
      || v.mode !== "replay" || !statuses.includes(v.status)) fail("context");
  integer(v.revision, "revision"); timestamp(v.generatedAt, "generatedAt");
  const r = v.replay;
  if (!record(r) || !["paused", "running", "completed"].includes(r.state)
    || !["guided", "full"].includes(r.scenario) || ![1, 2, 5].includes(r.speed)) fail("replay");
  text(r.runId, "runId");
  for (const key of ["generation", "cursor", "totalPairs", "startRow", "endRow", "warmupPairs"]) integer(r[key], key);
  if (r.cursor > r.totalPairs || r.startRow > r.endRow) fail("cursor bounds");
  if (r.sourceRow !== null) integer(r.sourceRow, "sourceRow");
  timestamp(r.sourceTime, "sourceTime", true); timestamp(r.arrivalTime, "arrivalTime", true);
  timestamp(r.expiresAt, "expiresAt"); parseDemoDataset(v.dataset);
  for (const id of ["s1", "s2"]) {
    const sensor = v.sensors?.[id];
    if (!record(sensor) || !["unavailable", "computed", "reused"].includes(sensor.assessmentState)
      || typeof sensor.newInformation !== "boolean") fail(`sensor ${id}`);
    if (sensor.latest !== null && parseDemoFrame(sensor.latest).sensorId !== id) fail("sensor identity");
    if (sensor.assessment !== null) {
      const a = sensor.assessment;
      if (!record(a) || !statuses.includes(a.assessment?.status)
        || !Array.isArray(a.evidence) || !record(a.model)) fail("assessment");
      for (const key of ["anomalyScore", "deteriorationScore", "persistenceSeconds"]) {
        if (a.assessment[key] !== null && !Number.isFinite(a.assessment[key])) fail(`assessment.${key}`);
      }
    }
  }
  if (!Array.isArray(v.history) || v.history.length > 600 || !Array.isArray(v.events)) fail("history/events");
  v.history.forEach(parseDemoFrame); v.events.forEach(parseDemoEvent);
  if (v.events.some((e) => e.generation !== r.generation || e.contextRevision > v.revision)) fail("event revision");
  const lastAllowedRow = r.sourceRow ?? r.startRow - 1;
  if (v.history.some((frame, index) => frame.sourceRow > lastAllowedRow
    || (index > 0 && frame.sourceRow < v.history[index - 1].sourceRow))) fail("history prefix/order");
  if (["s1", "s2"].some((id) => v.sensors[id].latest?.sourceRow > lastAllowedRow)) fail("latest prefix");
  if (!record(v.pipeline)) fail("pipeline");
  for (const key of ["receivedPairs", "receivedReadings", "newInformationReadings", "repeatedReadings", "gapCount", "assessmentsComputed", "eventsCreated"]) integer(v.pipeline[key], key);
  if (v.pipeline.lastAdvanceMs !== null && (!Number.isFinite(v.pipeline.lastAdvanceMs) || v.pipeline.lastAdvanceMs < 0)) fail("lastAdvanceMs");
  if (!record(v.capabilities)) fail("capabilities");
  return v;
}

export class DemoGatewayError extends Error {
  constructor(status, message) { super(message); this.name = "DemoGatewayError"; this.status = status; }
}

export function createGatewayDemoDataSource({ baseUrl = "", fetchImpl = fetch } = {}) {
  if (typeof baseUrl !== "string" || /[\\\x00-\x1f\x7f]/.test(baseUrl)
    || (baseUrl !== "" && !baseUrl.startsWith("/")) || baseUrl.startsWith("//")) throw new TypeError("Demo exige a mesma origem");
  const root = `${baseUrl.replace(/\/$/, "")}/api/demo/v1`;
  async function request(path, { method = "GET", body, session, signal } = {}, parse = (v) => v) {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    if (signal?.aborted) cancel();
    signal?.addEventListener("abort", cancel, { once: true });
    const timer = setTimeout(cancel, /assistant|recommendation/.test(path) ? 45000 : 25000);
    let response;
    try {
      try {
        response = await fetchImpl(`${root}${path}`, {
          method, signal: controller.signal, cache: "no-store",
          headers: { ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
            ...(session ? { Authorization: `Bearer ${session.token}` } : {}) },
          ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
        });
      } catch (error) {
        if (error.name === "AbortError" && signal?.aborted) throw error;
        throw new DemoGatewayError(null, "Conexão interrompida. Reconecte para confirmar o estado do replay.");
      }
      if (!response.ok) throw new DemoGatewayError(response.status, {
        404: "Sessão não encontrada. Crie uma nova sessão.",
        409: "O replay mudou durante a operação. Estado atualizado; escolha a ação novamente.",
        410: "Esta sessão expirou após 24 horas. Crie uma nova sessão.",
        503: "O serviço ou conjunto histórico está indisponível. Tente reconectar.",
      }[response.status] ?? "Não foi possível concluir a operação. Tente reconectar.");
      try { return parse(await response.json()); }
      catch (error) {
        if (controller.signal.aborted && !signal?.aborted) throw new DemoGatewayError(null, "Resposta interrompida. Reconecte para confirmar o estado do replay.");
        throw error;
      }
    } finally { clearTimeout(timer); signal?.removeEventListener("abort", cancel); }
  }
  const path = (s, operation) => `/runs/${encodeURIComponent(s.runId)}/${operation}`;
  return Object.freeze({
    datasets: ({ signal } = {}) => request("/datasets", { signal }, (v) => {
      if (!Array.isArray(v?.datasets)) fail("datasets");
      v.datasets.forEach(parseDemoDataset); return v.datasets;
    }),
    create: (body, { signal } = {}) => request("/runs", { method: "POST", body, signal }, (v) => {
      text(v?.token, "token"); text(v.runId, "runId"); parseDemoContext(v.context);
      if (v.context.replay.runId !== v.runId) fail("run identity"); return v;
    }),
    context: (session, { signal } = {}) => request(path(session, "context"), { session, signal }, parseDemoContext),
    control: (session, body, { signal } = {}) => request(path(session, "control"), { method: "POST", session, body, signal }, parseDemoContext),
    advance: (session, body, { signal } = {}) => request(path(session, "advance"), { method: "POST", session, body, signal }, parseDemoContext),
    recommend: (session, eventId, { signal } = {}) => request(path(session, `events/${encodeURIComponent(eventId)}/recommendation`), { method: "POST", session, body: {}, signal }, parseDemoEvent),
    query: (session, body, { signal } = {}) => request(path(session, "assistant/query"), { method: "POST", session, body, signal }, (v) => {
      integer(v?.contextRevision, "contextRevision"); integer(v.sourceRow, "sourceRow"); timestamp(v.observedAt, "observedAt");
      assertAssistantQueryResponse(v.response); return v;
    }),
  });
}
