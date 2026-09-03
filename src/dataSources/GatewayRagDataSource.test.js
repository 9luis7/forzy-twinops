import { describe, expect, it, vi } from "vitest";
import {
  RagGatewayError,
  createGatewayRagDataSource,
} from "./GatewayRagDataSource.js";

const ID = "00000000-0000-4000-8000-000000000001";

const validResponse = () => ({
  answer: {
    manual: "Não posso determinar causa raiz.",
    currentState: "O assessment operacional atual está indisponível.",
  },
  groundingStatus: "out_of_scope",
  citations: [],
  corpus: null,
  models: { embedding: "unavailable", generation: "openai/gpt-5.6-luna" },
  fallbackUsed: false,
  limitations: ["Requer validação humana."],
  humanValidationRequired: true,
  conversationId: ID,
  traceId: "00000000-0000-4000-8000-000000000002",
  latencyMs: 12,
});

describe("GatewayRagDataSource public query", () => {
  it("posts only the bounded conversation contract with an AbortSignal", async () => {
    const response = validResponse();
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => response });
    const source = createGatewayRagDataSource({ baseUrl: "/gateway/", fetchImpl });
    const controller = new AbortController();

    await expect(source.query("forzy-motor-01", {
      question: "  Qual é o estado?  ",
      conversationId: ID,
      history: Array.from({ length: 5 }, (_, index) => ({
        question: `q${index}`,
        answer: `a${index}`,
      })),
    }, { signal: controller.signal })).resolves.toBe(response);

    expect(fetchImpl).toHaveBeenCalledWith(
      "/gateway/api/v2/assets/forzy-motor-01/assistant/query",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: "Qual é o estado?",
          conversationId: ID,
          history: [
            { question: "q1", answer: "a1" },
            { question: "q2", answer: "a2" },
            { question: "q3", answer: "a3" },
            { question: "q4", answer: "a4" },
          ],
        }),
        signal: controller.signal,
      }
    );
  });

  it.each(["https://evil.example", "//evil.example", "\\evil", "/ok\nheader"])(
    "rejects non same-origin base URL %s",
    (baseUrl) => {
      expect(() => createGatewayRagDataSource({ baseUrl, fetchImpl: vi.fn() })).toThrow(
        /same-origin/
      );
    }
  );

  it("returns stable sanitized failures without reading or echoing response bodies", async () => {
    const text = vi.fn().mockResolvedValue("postgres://user:secret@example.invalid");
    const source = createGatewayRagDataSource({
      fetchImpl: vi.fn().mockResolvedValue({ ok: false, status: 503, text }),
    });

    await expect(source.query("forzy-motor-01", { question: "estado" })).rejects.toMatchObject({
      name: "RagGatewayError",
      code: "service_unavailable",
      status: 503,
      message: "O serviço RAG está temporariamente indisponível.",
    });
    expect(text).not.toHaveBeenCalled();
    expect(RagGatewayError).toBeTypeOf("function");
  });

  it("treats an unreachable service as degraded and preserves AbortError", async () => {
    const unreachable = createGatewayRagDataSource({
      fetchImpl: vi.fn().mockRejectedValue(new Error("secret network detail")),
    });
    await expect(unreachable.query("forzy-motor-01", { question: "estado" })).rejects.toMatchObject({
      code: "service_unavailable",
      message: "Não foi possível alcançar o serviço RAG.",
    });

    const aborted = new DOMException("aborted", "AbortError");
    const cancelled = createGatewayRagDataSource({
      fetchImpl: vi.fn().mockRejectedValue(aborted),
    });
    await expect(cancelled.query("forzy-motor-01", { question: "estado" })).rejects.toBe(aborted);
  });
});

describe("GatewayRagDataSource Preview administration", () => {
  const corpus = {
    corpusId: "corpus-1",
    assetId: "forzy-motor-01",
    manufacturer: "WEG",
    equipmentModel: "W22",
    status: "draft",
    embeddingModel: "google/text-multilingual-embedding-002",
    embeddingDimensions: 768,
    chunkTargetTokens: 700,
    chunkOverlapTokens: 100,
    minRelevanceScore: 0.25,
  };
  const coverage = {
    corpusId: "corpus-1",
    documentCount: 1,
    pageCount: 10,
    coveragePages: 9,
    chunkCount: 18,
  };
  const activation = {
    assetId: "forzy-motor-01",
    corpusId: "corpus-1",
    previousCorpusId: null,
    activatedAt: "2026-09-03T12:00:00+00:00",
  };

  it("uses only the six backend-supported admin calls and keeps PDF content in FormData", async () => {
    const upload = {
      document: {
        documentId: "document-1",
        corpusId: "corpus-1",
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
    };
    const retrieval = { items: [{
      chunkId: "chunk-1",
      documentId: "document-1",
      pageStart: 2,
      pageEnd: 2,
      section: null,
      excerpt: "Ground the motor before energizing it.",
      contentHash: "c".repeat(64),
    }] };
    const payloads = [corpus, upload, { corpus, coverage }, retrieval, activation, activation];
    const fetchImpl = vi.fn().mockImplementation(() => Promise.resolve({
      ok: true,
      json: async () => payloads[fetchImpl.mock.calls.length - 1],
    }));
    const source = createGatewayRagDataSource({ fetchImpl });
    const file = new Blob(["%PDF-1.7"], { type: "application/pdf" });
    Object.defineProperty(file, "name", { value: "manual.pdf" });

    await source.createDraft({
      assetId: "forzy-motor-01",
      chunkTargetTokens: 700,
      chunkOverlapTokens: 100,
      minRelevanceScore: 0.25,
    });
    await source.uploadDocument("corpus-1", {
      file,
      manufacturer: "WEG",
      equipmentModel: "W22",
      revision: "2026-01",
      language: "pt-BR",
      sourceUrl: "https://manufacturer.example/manual.pdf",
    });
    await source.getCorpus("corpus-1");
    await source.testRetrieval("corpus-1", { query: "grounding", limit: 6 });
    await source.publish("corpus-1");
    await source.reactivate("corpus-1");

    expect(fetchImpl.mock.calls.map(([path, options]) => [path, options.method])).toEqual([
      ["/api/v2/admin/rag/corpora", "POST"],
      ["/api/v2/admin/rag/corpora/corpus-1/documents", "POST"],
      ["/api/v2/admin/rag/corpora/corpus-1", "GET"],
      ["/api/v2/admin/rag/corpora/corpus-1/retrieval-test", "POST"],
      ["/api/v2/admin/rag/corpora/corpus-1/publish", "POST"],
      ["/api/v2/admin/rag/corpora/corpus-1/reactivate", "POST"],
    ]);
    const uploadRequest = fetchImpl.mock.calls[1][1];
    expect(uploadRequest.body).toBeInstanceOf(FormData);
    expect(uploadRequest.headers).toBeUndefined();
    expect(uploadRequest.body.get("manufacturer")).toBe("WEG");
    expect(uploadRequest.body.get("equipmentModel")).toBe("W22");
    expect(uploadRequest.body.get("file").name).toBe("manual.pdf");
  });
});
