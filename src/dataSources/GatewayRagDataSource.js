import {
  assertAssistantQueryResponse,
  assertRagActivation,
  assertRagCorpus,
  assertRagCorpusCoverage,
  assertRagRetrievalResults,
  assertRagUploadResult,
  createAssistantQueryRequest,
} from "../contracts/rag.js";

const MAX_PDF_BYTES = 25 * 1024 * 1024;

const assertBaseUrl = (baseUrl) => {
  if (
    typeof baseUrl !== "string"
    || /[\x00-\x1f\x7f]/.test(baseUrl)
    || baseUrl.includes("\\")
    || (baseUrl !== "" && !baseUrl.startsWith("/"))
    || baseUrl.startsWith("//")
  ) {
    throw new TypeError("GatewayRagDataSource baseUrl must be empty or a same-origin absolute path");
  }
};

const assertIdentifier = (value, label, maximum = 200) => {
  if (typeof value !== "string" || value.trim().length < 1 || value.length > maximum) {
    throw new TypeError(`GatewayRagDataSource ${label} must contain 1 to ${maximum} characters`);
  }
  return value.trim();
};

const assertFiniteRange = (value, label, minimum, maximum, { integer = false } = {}) => {
  if (typeof value !== "number" || !Number.isFinite(value) || (integer && !Number.isInteger(value))) {
    throw new TypeError(`GatewayRagDataSource ${label} must be a finite${integer ? " integer" : ""} number`);
  }
  if (value < minimum || value > maximum) {
    throw new TypeError(`GatewayRagDataSource ${label} is outside the supported range`);
  }
  return value;
};

const assertHttpsUrl = (value) => {
  const sourceUrl = assertIdentifier(value, "sourceUrl", 2_048);
  let parsed;
  try {
    parsed = new URL(sourceUrl);
  } catch {
    throw new TypeError("GatewayRagDataSource sourceUrl must be HTTPS");
  }
  if (
    parsed.protocol !== "https:"
    || !parsed.hostname
    || parsed.username
    || parsed.password
    || parsed.hash
  ) {
    throw new TypeError("GatewayRagDataSource sourceUrl must be HTTPS");
  }
  return sourceUrl;
};

const assertExactInput = (value, label, allowed) => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(`GatewayRagDataSource ${label} must be an object`);
  }
  const keys = new Set(allowed);
  for (const key of Object.keys(value)) {
    if (!keys.has(key)) throw new TypeError(`GatewayRagDataSource ${label}.${key} is not allowed`);
  }
};

const STATUS_ERRORS = Object.freeze({
  404: ["not_found", "O recurso RAG solicitado não está disponível."],
  409: ["conflict", "A operação conflita com o estado atual do corpus."],
  413: ["payload_too_large", "O PDF excede o limite permitido de 25 MB."],
  422: ["invalid_request", "Os dados enviados não atendem ao contrato RAG."],
  503: ["service_unavailable", "O serviço RAG está temporariamente indisponível."],
});

export class RagGatewayError extends Error {
  constructor(code, message, status = null) {
    super(message);
    this.name = "RagGatewayError";
    this.code = code;
    this.status = status;
  }
}

const responseError = (status) => {
  const [code, message] = STATUS_ERRORS[status] ?? [
    "request_failed",
    "A operação RAG não pôde ser concluída.",
  ];
  return new RagGatewayError(code, message, Number.isInteger(status) ? status : null);
};

const assetAssistantPath = (assetId) =>
  `/api/v2/assets/${encodeURIComponent(assetId)}/assistant/query`;
const corpusPath = (corpusId, operation = "") =>
  `/api/v2/admin/rag/corpora/${encodeURIComponent(corpusId)}${operation ? `/${operation}` : ""}`;

export function createGatewayRagDataSource({ baseUrl = "", fetchImpl = fetch } = {}) {
  assertBaseUrl(baseUrl);
  if (typeof fetchImpl !== "function") {
    throw new TypeError("GatewayRagDataSource fetchImpl must be a function");
  }
  const root = baseUrl.replace(/\/$/, "");

  const request = async (path, options, validate) => {
    let response;
    try {
      response = await fetchImpl(`${root}${path}`, options);
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw new RagGatewayError(
        "service_unavailable",
        "Não foi possível alcançar o serviço RAG.",
      );
    }
    if (!response?.ok) throw responseError(response?.status);
    try {
      return validate(await response.json());
    } catch (error) {
      if (error instanceof RagGatewayError) throw error;
      throw new RagGatewayError(
        "invalid_response",
        "O serviço RAG retornou uma resposta inválida.",
        Number.isInteger(response?.status) ? response.status : null,
      );
    }
  };

  const jsonRequest = (path, method, body, signal, validate) => request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }, validate);

  const activationRequest = (corpusId, operation, signal) => request(
    corpusPath(assertIdentifier(corpusId, "corpusId"), operation),
    { method: "POST", signal },
    assertRagActivation,
  );

  return Object.freeze({
    async query(assetId, input, { signal } = {}) {
      const normalizedAssetId = assertIdentifier(assetId, "assetId");
      return jsonRequest(
        assetAssistantPath(normalizedAssetId),
        "POST",
        createAssistantQueryRequest(input),
        signal,
        assertAssistantQueryResponse,
      );
    },

    async createDraft(input, { signal } = {}) {
      assertExactInput(input, "createDraft", [
        "assetId", "chunkTargetTokens", "chunkOverlapTokens", "minRelevanceScore",
      ]);
      const body = {
        assetId: assertIdentifier(input.assetId, "assetId"),
        chunkTargetTokens: assertFiniteRange(input.chunkTargetTokens, "chunkTargetTokens", 200, 2_000, { integer: true }),
        chunkOverlapTokens: assertFiniteRange(input.chunkOverlapTokens, "chunkOverlapTokens", 0, 500, { integer: true }),
        minRelevanceScore: assertFiniteRange(input.minRelevanceScore, "minRelevanceScore", 0, 1),
      };
      if (body.chunkOverlapTokens >= body.chunkTargetTokens) {
        throw new TypeError("GatewayRagDataSource chunkOverlapTokens must be lower than chunkTargetTokens");
      }
      return jsonRequest("/api/v2/admin/rag/corpora", "POST", body, signal, assertRagCorpus);
    },

    async uploadDocument(corpusId, input, { signal } = {}) {
      const normalizedCorpusId = assertIdentifier(corpusId, "corpusId");
      assertExactInput(input, "uploadDocument", [
        "file", "manufacturer", "equipmentModel", "revision", "language", "sourceUrl",
      ]);
      if (!(input.file instanceof Blob) || input.file.size < 1 || input.file.size > MAX_PDF_BYTES) {
        throw new TypeError("GatewayRagDataSource file must be a PDF of at most 25 MB");
      }
      if (input.file.type !== "application/pdf") {
        throw new TypeError("GatewayRagDataSource file must use application/pdf");
      }
      const filename = typeof input.file.name === "string" && input.file.name.trim()
        ? input.file.name
        : "manual.pdf";
      const form = new FormData();
      form.append("file", input.file, filename);
      form.append("manufacturer", assertIdentifier(input.manufacturer, "manufacturer"));
      form.append("equipmentModel", assertIdentifier(input.equipmentModel, "equipmentModel"));
      form.append("revision", assertIdentifier(input.revision, "revision"));
      form.append("language", assertIdentifier(input.language, "language"));
      form.append("sourceUrl", assertHttpsUrl(input.sourceUrl));
      return request(corpusPath(normalizedCorpusId, "documents"), {
        method: "POST",
        body: form,
        signal,
      }, assertRagUploadResult);
    },

    async getCorpus(corpusId, { signal } = {}) {
      return request(corpusPath(assertIdentifier(corpusId, "corpusId")), {
        method: "GET",
        signal,
      }, assertRagCorpusCoverage);
    },

    async testRetrieval(corpusId, input, { signal } = {}) {
      assertExactInput(input, "testRetrieval", ["query", "limit"]);
      const query = assertIdentifier(input.query, "query", 500);
      const limit = assertFiniteRange(input.limit ?? 6, "limit", 1, 6, { integer: true });
      return jsonRequest(
        corpusPath(assertIdentifier(corpusId, "corpusId"), "retrieval-test"),
        "POST",
        { query, limit },
        signal,
        assertRagRetrievalResults,
      );
    },

    async publish(corpusId, { signal } = {}) {
      return activationRequest(corpusId, "publish", signal);
    },

    async reactivate(corpusId, { signal } = {}) {
      return activationRequest(corpusId, "reactivate", signal);
    },
  });
}
