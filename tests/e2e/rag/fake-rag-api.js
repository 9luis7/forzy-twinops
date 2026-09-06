const exactJson = (actual, expected, label) => {
  const normalize = (value) => {
    if (Array.isArray(value)) return value.map(normalize);
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.keys(value).sort().map((key) => [key, normalize(value[key])]),
      );
    }
    return value;
  };
  if (JSON.stringify(normalize(actual)) !== JSON.stringify(normalize(expected))) {
    throw new Error(`${label} payload does not match the strict contract`);
  }
};

const bodyBytes = (request) => {
  if (request.body == null) return Buffer.alloc(0);
  return Buffer.isBuffer(request.body) ? request.body : Buffer.from(request.body);
};

const parseJson = (request) => {
  const contentType = request.headers?.["content-type"] ?? "";
  if (!contentType.startsWith("application/json")) {
    throw new Error("JSON request must use application/json");
  }
  return JSON.parse(bodyBytes(request).toString("utf8"));
};

const requireRequest = (request, method, path) => {
  if (request.method !== method) throw new Error(`${path} requires ${method}`);
};

const clone = (value) => JSON.parse(JSON.stringify(value));


export function createStrictRagFake({
  origin,
  corpus,
  coverage,
  snapshot = { capabilities: { copilot: false } },
  assistantResponse = null,
}) {
  const state = {
    created: false,
    uploaded: false,
    retrievalTested: false,
    published: false,
    publishCalls: 0,
    coverageReads: 0,
    assistantRequest: null,
  };
  const corpusRoot = `/api/v2/admin/rag/corpora/${corpus.corpusId}`;

  const handle = async (request) => {
    const url = new URL(request.url);
    if (url.origin !== origin || url.search || url.hash) {
      throw new Error("RAG fake accepts only the configured same origin without query data");
    }
    const path = url.pathname;

    if (path === "/api/v2/admin/rag/corpora") {
      requireRequest(request, "POST", path);
      exactJson(parseJson(request), {
        assetId: "forzy-motor-01",
        chunkTargetTokens: 700,
        chunkOverlapTokens: 100,
        minRelevanceScore: 0.2,
      }, "create draft");
      if (state.created) throw new Error("draft may be created only once");
      state.created = true;
      return { status: 201, body: corpus };
    }

    if (path === `${corpusRoot}/documents`) {
      requireRequest(request, "POST", path);
      if (!state.created || state.uploaded) throw new Error("upload sequence is invalid");
      const contentType = request.headers?.["content-type"] ?? "";
      if (!/^multipart\/form-data;\s*boundary=.+/i.test(contentType)) {
        throw new Error("upload requires a multipart boundary");
      }
      const form = await new Response(bodyBytes(request), {
        headers: { "content-type": contentType },
      }).formData();
      exactJson([...form.keys()].sort(), [
        "equipmentModel", "file", "language", "manufacturer", "revision", "sourceUrl",
      ], "upload fields");
      const file = form.get("file");
      if (
        !file
        || typeof file.arrayBuffer !== "function"
        || file.name !== "manual.pdf"
        || file.type !== "application/pdf"
        || !Buffer.from(await file.arrayBuffer()).subarray(0, 4).equals(Buffer.from("%PDF"))
      ) {
        throw new Error("upload PDF file contract is invalid");
      }
      exactJson(Object.fromEntries(
        ["manufacturer", "equipmentModel", "revision", "language", "sourceUrl"]
          .map((key) => [key, form.get(key)]),
      ), {
        manufacturer: "WEG",
        equipmentModel: "W22",
        revision: "2026-01",
        language: "pt-BR",
        sourceUrl: "https://manufacturer.example/manual.pdf",
      }, "upload metadata");
      state.uploaded = true;
      return {
        status: 201,
        body: {
          document: {
            documentId: "document-1",
            corpusId: corpus.corpusId,
            manufacturer: "WEG",
            equipmentModel: "W22",
            revision: "2026-01",
            language: "pt-BR",
            sourceUrl: "https://manufacturer.example/manual.pdf",
            sha256: "b".repeat(64),
            pageCount: 10,
            coveragePages: 9,
          },
          coverage,
        },
      };
    }

    if (path === corpusRoot) {
      requireRequest(request, "GET", path);
      if (bodyBytes(request).length) throw new Error("coverage GET must not have a body");
      if (!state.uploaded) throw new Error("coverage requires an uploaded document");
      state.coverageReads += 1;
      return { status: 200, body: { corpus, coverage } };
    }

    if (path === `${corpusRoot}/retrieval-test`) {
      requireRequest(request, "POST", path);
      if (!state.uploaded) throw new Error("retrieval requires an uploaded document");
      exactJson(parseJson(request), { query: "Como aterrar o motor?", limit: 6 }, "retrieval");
      state.retrievalTested = true;
      return {
        status: 200,
        body: { items: [{
          chunkId: "chunk-1", documentId: "document-1", pageStart: 2, pageEnd: 3,
          section: "INSTALLATION", excerpt: "Aterre o motor antes da energização.",
          contentHash: "c".repeat(64), absoluteScore: 0.82, rankScore: 1,
          vectorRank: 1, lexicalRank: 1,
        }] },
      };
    }

    if (path === `${corpusRoot}/publish`) {
      requireRequest(request, "POST", path);
      if (bodyBytes(request).length) throw new Error("publish POST must have an empty body");
      if (!state.retrievalTested || state.published) throw new Error("publish sequence is invalid");
      state.publishCalls += 1;
      state.published = true;
      return {
        status: 200,
        body: {
          assetId: "forzy-motor-01", corpusId: corpus.corpusId,
          previousCorpusId: null, activatedAt: "2026-09-03T12:00:00+00:00",
        },
      };
    }

    if (path === "/api/v2/assets/forzy-motor-01/snapshot") {
      requireRequest(request, "GET", path);
      if (bodyBytes(request).length) throw new Error("snapshot GET must not have a body");
      const body = clone(snapshot);
      body.capabilities.copilot = state.published;
      return { status: 200, body };
    }

    if (path === "/api/v2/assets/forzy-motor-01/assistant/query") {
      requireRequest(request, "POST", path);
      if (!state.published || !assistantResponse) throw new Error("assistant is unavailable");
      const body = parseJson(request);
      exactJson(body, {
        question: "O que o manual orienta e qual é o estado atual?",
        history: [],
      }, "public assistant");
      state.assistantRequest = body;
      return { status: 200, body: assistantResponse };
    }

    throw new Error(`unexpected RAG request: ${request.method} ${path}`);
  };

  return { handle, state };
}


export async function fulfillStrictRagRoute(route, fake) {
  const request = route.request();
  const result = await fake.handle({
    url: request.url(),
    method: request.method(),
    headers: request.headers(),
    body: request.postDataBuffer(),
  });
  await route.fulfill({
    status: result.status,
    contentType: "application/json",
    body: JSON.stringify(result.body),
  });
}
