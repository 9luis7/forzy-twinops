const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256 = /^[0-9a-f]{64}$/;
const HTTPS_URL = /^https:\/\//i;
const GROUNDING_STATUSES = new Set([
  "grounded",
  "manual_insufficient",
  "operational_unavailable",
  "degraded_fallback",
  "out_of_scope",
]);
export const MAX_HISTORY_ANSWER_CHARACTERS = 6_000;

const fail = (path, message) => {
  throw new TypeError(`Invalid RAG contract at ${path}: ${message}`);
};

const assertExactKeys = (value, path, allowed) => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail(path, "must be an object");
  }
  const allowedKeys = new Set(allowed);
  for (const key of Object.keys(value)) {
    if (!allowedKeys.has(key)) fail(`${path}.${key}`, "is not allowed");
  }
};

const boundedString = (value, path, maximum) => {
  if (typeof value !== "string") fail(path, "must be a string");
  const trimmed = value.trim();
  if (trimmed.length < 1 || trimmed.length > maximum) {
    fail(path, `must contain 1 to ${maximum} characters`);
  }
  return trimmed;
};

const assertUuid = (value, path) => {
  if (typeof value !== "string" || !UUID.test(value)) fail(path, "must be a UUID");
  return value;
};

const assertBoolean = (value, path) => {
  if (typeof value !== "boolean") fail(path, "must be a boolean");
};

const assertFiniteNumber = (value, path, { minimum, maximum } = {}) => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail(path, "must be a finite number");
  }
  if (minimum !== undefined && value < minimum) fail(path, `must be at least ${minimum}`);
  if (maximum !== undefined && value > maximum) fail(path, `must be at most ${maximum}`);
};

const assertInteger = (value, path, options) => {
  if (!Number.isInteger(value)) fail(path, "must be an integer");
  assertFiniteNumber(value, path, options);
};

const assertTimestamp = (value, path) => {
  boundedString(value, path, 64);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(value) || Number.isNaN(Date.parse(value))) {
    fail(path, "must be an RFC 3339 timestamp with timezone");
  }
};

const assertHttpsUrl = (value, path) => {
  boundedString(value, path, 2_048);
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    fail(path, "must be an HTTPS URL");
  }
  if (
    !HTTPS_URL.test(value)
    || parsed.protocol !== "https:"
    || !parsed.hostname
    || parsed.username
    || parsed.password
    || parsed.hash
  ) {
    fail(path, "must be an HTTPS URL");
  }
};

const assertManualCitation = (value, path) => {
  assertExactKeys(value, path, [
    "type", "chunkId", "documentId", "manufacturer", "equipmentModel", "revision",
    "sourceUrl", "pageStart", "pageEnd", "section", "excerpt", "contentHash",
  ]);
  if (value.type !== "manual") fail(`${path}.type`, "must equal manual");
  boundedString(value.chunkId, `${path}.chunkId`, 200);
  boundedString(value.documentId, `${path}.documentId`, 200);
  boundedString(value.manufacturer, `${path}.manufacturer`, 200);
  boundedString(value.equipmentModel, `${path}.equipmentModel`, 200);
  boundedString(value.revision, `${path}.revision`, 200);
  assertHttpsUrl(value.sourceUrl, `${path}.sourceUrl`);
  assertInteger(value.pageStart, `${path}.pageStart`, { minimum: 1, maximum: 400 });
  assertInteger(value.pageEnd, `${path}.pageEnd`, { minimum: value.pageStart, maximum: 400 });
  if (value.section !== null) boundedString(value.section, `${path}.section`, 500);
  boundedString(value.excerpt, `${path}.excerpt`, 500);
  if (typeof value.contentHash !== "string" || !SHA256.test(value.contentHash)) {
    fail(`${path}.contentHash`, "must be a lowercase SHA-256 hash");
  }
};

const assertTelemetryCitation = (value, path) => {
  assertExactKeys(value, path, [
    "type", "assessmentId", "evidenceId", "feature", "value", "unit", "windowStart",
    "windowEnd", "receivedAt", "freshnessMs", "windowSeconds", "qualityStatus",
  ]);
  if (value.type !== "telemetry") fail(`${path}.type`, "must equal telemetry");
  assertUuid(value.assessmentId, `${path}.assessmentId`);
  boundedString(value.evidenceId, `${path}.evidenceId`, 300);
  boundedString(value.feature, `${path}.feature`, 300);
  assertFiniteNumber(value.value, `${path}.value`);
  boundedString(value.unit, `${path}.unit`, 80);
  assertTimestamp(value.windowStart, `${path}.windowStart`);
  assertTimestamp(value.windowEnd, `${path}.windowEnd`);
  assertTimestamp(value.receivedAt, `${path}.receivedAt`);
  assertFiniteNumber(value.freshnessMs, `${path}.freshnessMs`, { minimum: 0 });
  if (value.windowSeconds !== null) {
    assertFiniteNumber(value.windowSeconds, `${path}.windowSeconds`, { minimum: 0 });
  }
  boundedString(value.qualityStatus, `${path}.qualityStatus`, 80);
};

const assertCorpusAnchor = (value, path) => {
  assertExactKeys(value, path, [
    "corpusId", "manufacturer", "equipmentModel", "embeddingModel",
    "embeddingDimensions", "minRelevanceScore",
  ]);
  boundedString(value.corpusId, `${path}.corpusId`, 200);
  boundedString(value.manufacturer, `${path}.manufacturer`, 200);
  boundedString(value.equipmentModel, `${path}.equipmentModel`, 200);
  boundedString(value.embeddingModel, `${path}.embeddingModel`, 300);
  assertInteger(value.embeddingDimensions, `${path}.embeddingDimensions`, {
    minimum: 1,
    maximum: 100_000,
  });
  assertFiniteNumber(value.minRelevanceScore, `${path}.minRelevanceScore`, {
    minimum: 0,
    maximum: 1,
  });
};

const assertAdminCorpus = (value, path) => {
  assertExactKeys(value, path, [
    "corpusId", "assetId", "manufacturer", "equipmentModel", "status", "embeddingModel",
    "embeddingDimensions", "chunkTargetTokens", "chunkOverlapTokens", "minRelevanceScore",
  ]);
  boundedString(value.corpusId, `${path}.corpusId`, 200);
  if (value.assetId !== "forzy-motor-01") fail(`${path}.assetId`, "must equal forzy-motor-01");
  boundedString(value.manufacturer, `${path}.manufacturer`, 200);
  boundedString(value.equipmentModel, `${path}.equipmentModel`, 200);
  if (!["draft", "published"].includes(value.status)) fail(`${path}.status`, "has an unsupported value");
  boundedString(value.embeddingModel, `${path}.embeddingModel`, 300);
  assertInteger(value.embeddingDimensions, `${path}.embeddingDimensions`, { minimum: 1, maximum: 100_000 });
  assertInteger(value.chunkTargetTokens, `${path}.chunkTargetTokens`, { minimum: 200, maximum: 2_000 });
  assertInteger(value.chunkOverlapTokens, `${path}.chunkOverlapTokens`, { minimum: 0, maximum: 500 });
  if (value.chunkOverlapTokens >= value.chunkTargetTokens) {
    fail(`${path}.chunkOverlapTokens`, "must be lower than chunkTargetTokens");
  }
  assertFiniteNumber(value.minRelevanceScore, `${path}.minRelevanceScore`, { minimum: 0, maximum: 1 });
};

const assertCoverage = (value, path) => {
  assertExactKeys(value, path, [
    "corpusId", "documentCount", "pageCount", "coveragePages", "chunkCount",
  ]);
  boundedString(value.corpusId, `${path}.corpusId`, 200);
  assertInteger(value.documentCount, `${path}.documentCount`, { minimum: 0 });
  assertInteger(value.pageCount, `${path}.pageCount`, { minimum: 0 });
  assertInteger(value.coveragePages, `${path}.coveragePages`, { minimum: 0 });
  assertInteger(value.chunkCount, `${path}.chunkCount`, { minimum: 0 });
  if (value.coveragePages > value.pageCount) {
    fail(`${path}.coveragePages`, "must not exceed pageCount");
  }
};

const assertDocument = (value, path) => {
  assertExactKeys(value, path, [
    "documentId", "corpusId", "manufacturer", "equipmentModel", "revision", "language",
    "sourceUrl", "sha256", "pageCount", "coveragePages",
  ]);
  boundedString(value.documentId, `${path}.documentId`, 200);
  boundedString(value.corpusId, `${path}.corpusId`, 200);
  boundedString(value.manufacturer, `${path}.manufacturer`, 200);
  boundedString(value.equipmentModel, `${path}.equipmentModel`, 200);
  boundedString(value.revision, `${path}.revision`, 200);
  boundedString(value.language, `${path}.language`, 80);
  assertHttpsUrl(value.sourceUrl, `${path}.sourceUrl`);
  if (typeof value.sha256 !== "string" || !SHA256.test(value.sha256)) {
    fail(`${path}.sha256`, "must be a lowercase SHA-256 hash");
  }
  assertInteger(value.pageCount, `${path}.pageCount`, { minimum: 1, maximum: 400 });
  assertInteger(value.coveragePages, `${path}.coveragePages`, { minimum: 1, maximum: value.pageCount });
};

const assertRetrievalItem = (value, path) => {
  assertExactKeys(value, path, [
    "chunkId", "documentId", "pageStart", "pageEnd", "section", "excerpt", "contentHash",
    "absoluteScore", "rankScore", "vectorRank", "lexicalRank",
  ]);
  boundedString(value.chunkId, `${path}.chunkId`, 200);
  boundedString(value.documentId, `${path}.documentId`, 200);
  assertInteger(value.pageStart, `${path}.pageStart`, { minimum: 1, maximum: 400 });
  assertInteger(value.pageEnd, `${path}.pageEnd`, { minimum: value.pageStart, maximum: 400 });
  if (value.section !== null) boundedString(value.section, `${path}.section`, 500);
  boundedString(value.excerpt, `${path}.excerpt`, 500);
  if (typeof value.contentHash !== "string" || !SHA256.test(value.contentHash)) {
    fail(`${path}.contentHash`, "must be a lowercase SHA-256 hash");
  }
  assertFiniteNumber(value.absoluteScore, `${path}.absoluteScore`, { minimum: 0, maximum: 1 });
  assertFiniteNumber(value.rankScore, `${path}.rankScore`, { minimum: 0, maximum: 1 });
  for (const field of ["vectorRank", "lexicalRank"]) {
    if (value[field] !== null) {
      assertInteger(value[field], `${path}.${field}`, { minimum: 1, maximum: 12 });
    }
  }
};

export function createAssistantQueryRequest(value) {
  assertExactKeys(value, "request", ["question", "conversationId", "history"]);
  const question = boundedString(value.question, "request.question", 500);
  const history = value.history ?? [];
  if (!Array.isArray(history)) fail("request.history", "must be an array");

  const result = {
    question,
    ...(value.conversationId === undefined || value.conversationId === null
      ? {}
      : { conversationId: assertUuid(value.conversationId, "request.conversationId") }),
    history: history.slice(-4).map((turn, index) => {
      assertExactKeys(turn, `request.history[${index}]`, ["question", "answer"]);
      return {
        question: boundedString(turn.question, `request.history[${index}].question`, 500),
        answer: boundedString(
          turn.answer,
          `request.history[${index}].answer`,
          MAX_HISTORY_ANSWER_CHARACTERS,
        ),
      };
    }),
  };
  return result;
}

export function assertAssistantQueryResponse(value) {
  assertExactKeys(value, "response", [
    "answer", "groundingStatus", "citations", "corpus", "models", "fallbackUsed",
    "limitations", "humanValidationRequired", "conversationId", "traceId", "latencyMs",
  ]);
  assertExactKeys(value.answer, "response.answer", ["manual", "currentState"]);
  boundedString(value.answer.manual, "response.answer.manual", 6_000);
  boundedString(value.answer.currentState, "response.answer.currentState", 6_000);
  if (!GROUNDING_STATUSES.has(value.groundingStatus)) {
    fail("response.groundingStatus", "has an unsupported value");
  }
  if (!Array.isArray(value.citations) || value.citations.length > 50) {
    fail("response.citations", "must contain at most 50 items");
  }
  value.citations.forEach((citation, index) => {
    if (citation?.type === "manual") {
      assertManualCitation(citation, `response.citations[${index}]`);
      return;
    }
    if (citation?.type === "telemetry") {
      assertTelemetryCitation(citation, `response.citations[${index}]`);
      return;
    }
    fail(`response.citations[${index}].type`, "has an unsupported discriminator");
  });
  if (value.corpus !== null) assertCorpusAnchor(value.corpus, "response.corpus");
  assertExactKeys(value.models, "response.models", ["embedding", "generation"]);
  boundedString(value.models.embedding, "response.models.embedding", 300);
  boundedString(value.models.generation, "response.models.generation", 300);
  assertBoolean(value.fallbackUsed, "response.fallbackUsed");
  if (!Array.isArray(value.limitations) || value.limitations.length > 20) {
    fail("response.limitations", "must contain at most 20 items");
  }
  value.limitations.forEach((item, index) => {
    boundedString(item, `response.limitations[${index}]`, 1_000);
  });
  if (value.humanValidationRequired !== true) {
    fail("response.humanValidationRequired", "must be true");
  }
  assertUuid(value.conversationId, "response.conversationId");
  assertUuid(value.traceId, "response.traceId");
  assertFiniteNumber(value.latencyMs, "response.latencyMs", { minimum: 0 });
  return value;
}

export function assertRagCorpus(value) {
  assertAdminCorpus(value, "corpus");
  return value;
}

export function assertRagCorpusCoverage(value) {
  assertExactKeys(value, "corpusCoverage", ["corpus", "coverage"]);
  assertAdminCorpus(value.corpus, "corpusCoverage.corpus");
  assertCoverage(value.coverage, "corpusCoverage.coverage");
  if (value.corpus.corpusId !== value.coverage.corpusId) {
    fail("corpusCoverage.coverage.corpusId", "must match corpus.corpusId");
  }
  return value;
}

export function assertRagUploadResult(value) {
  assertExactKeys(value, "upload", ["document", "coverage"]);
  assertDocument(value.document, "upload.document");
  assertCoverage(value.coverage, "upload.coverage");
  if (value.document.corpusId !== value.coverage.corpusId) {
    fail("upload.document.corpusId", "must match coverage.corpusId");
  }
  return value;
}

export function assertRagRetrievalResults(value) {
  assertExactKeys(value, "retrieval", ["items"]);
  if (!Array.isArray(value.items) || value.items.length > 12) {
    fail("retrieval.items", "must contain at most 12 items");
  }
  value.items.forEach((item, index) => assertRetrievalItem(item, `retrieval.items[${index}]`));
  return value;
}

export function assertRagActivation(value) {
  assertExactKeys(value, "activation", [
    "assetId", "corpusId", "previousCorpusId", "activatedAt",
  ]);
  if (value.assetId !== "forzy-motor-01") fail("activation.assetId", "must equal forzy-motor-01");
  boundedString(value.corpusId, "activation.corpusId", 200);
  if (value.previousCorpusId !== null) {
    boundedString(value.previousCorpusId, "activation.previousCorpusId", 200);
  }
  assertTimestamp(value.activatedAt, "activation.activatedAt");
  return value;
}
