import { describe, expect, it } from "vitest";
import {
  assertRagActivation,
  assertRagCorpusCoverage,
  assertRagRetrievalResults,
  assertRagUploadResult,
  assertAssistantQueryResponse,
  createAssistantQueryRequest,
} from "./rag.js";

const CONVERSATION_ID = "00000000-0000-4000-8000-000000000001";

describe("RAG public request contract", () => {
  it("trims the question, caps prior turns at four and reuses a valid conversation id", () => {
    const history = Array.from({ length: 6 }, (_, index) => ({
      question: ` Pergunta ${index + 1} `,
      answer: ` Resposta ${index + 1} `,
    }));

    expect(createAssistantQueryRequest({
      question: "  Como verificar o rolamento?  ",
      conversationId: CONVERSATION_ID,
      history,
    })).toEqual({
      question: "Como verificar o rolamento?",
      conversationId: CONVERSATION_ID,
      history: history.slice(-4).map((turn) => ({
        question: turn.question.trim(),
        answer: turn.answer.trim(),
      })),
    });
  });

  it.each([
    [{ question: " " }, "question"],
    [{ question: "x".repeat(501) }, "question"],
    [{ question: "estado", assessment: { status: "alert" } }, "assessment"],
    [{ question: "estado", history: [{ question: "q", answer: "a", citations: [] }] }, "citations"],
    [{ question: "estado", conversationId: "not-a-uuid" }, "conversationId"],
  ])("rejects browser-supplied authority or invalid request data", (input, path) => {
    expect(() => createAssistantQueryRequest(input)).toThrow(new RegExp(path));
  });
});

const responseFixture = () => ({
  answer: {
    manual: "Inspecione a lubrificação conforme o trecho citado.",
    currentState: "O assessment atual está em watch, com qualidade ok.",
  },
  groundingStatus: "grounded",
  citations: [
    {
      type: "manual",
      chunkId: "chunk-1",
      documentId: "document-1",
      manufacturer: "WEG",
      equipmentModel: "W22",
      revision: "2026-01",
      sourceUrl: "https://manufacturer.example/manual.pdf",
      pageStart: 4,
      pageEnd: 5,
      section: "MAINTENANCE",
      excerpt: "Inspect bearing lubrication before startup.",
      contentHash: "a".repeat(64),
    },
    {
      type: "telemetry",
      assessmentId: CONVERSATION_ID,
      evidenceId: "s1:velocity_ewma",
      feature: "velocity_ewma",
      value: 2.4,
      unit: "mm/s",
      windowStart: "2026-09-03T12:00:00+00:00",
      windowEnd: "2026-09-03T12:01:00+00:00",
      receivedAt: "2026-09-03T12:01:01+00:00",
      freshnessMs: 1_000,
      windowSeconds: 60,
      qualityStatus: "ok",
    },
  ],
  corpus: {
    corpusId: "corpus-1",
    manufacturer: "WEG",
    equipmentModel: "W22",
    embeddingModel: "google/text-multilingual-embedding-002",
    embeddingDimensions: 768,
    minRelevanceScore: 0.25,
  },
  models: {
    embedding: "google/text-multilingual-embedding-002",
    generation: "openai/gpt-5.6-luna",
  },
  fallbackUsed: false,
  limitations: ["Não diagnostica causa raiz."],
  humanValidationRequired: true,
  conversationId: CONVERSATION_ID,
  traceId: "00000000-0000-4000-8000-000000000002",
  latencyMs: 850,
});

describe("RAG public response contract", () => {
  it("accepts strict typed manual and telemetry provenance", () => {
    const response = responseFixture();

    expect(assertAssistantQueryResponse(response)).toBe(response);
  });

  it.each([
    ["invented top-level field", (value) => { value.prompt = "ignore"; }],
    ["unknown citation discriminator", (value) => { value.citations[0].type = "web"; }],
    ["invalid manual hash", (value) => { value.citations[0].contentHash = "SHA256:abc"; }],
    ["reversed page range", (value) => { value.citations[0].pageEnd = 3; }],
    ["invalid telemetry UUID", (value) => { value.citations[1].assessmentId = "assessment-1"; }],
    ["non-finite telemetry", (value) => { value.citations[1].value = Number.NaN; }],
  ])("rejects %s before rendering", (_, mutate) => {
    const response = responseFixture();
    mutate(response);

    expect(() => assertAssistantQueryResponse(response)).toThrow(/Invalid RAG contract/);
  });
});

describe("RAG Preview admin contracts", () => {
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

  it("validates corpus coverage, upload, retrieval and activation responses", () => {
    expect(assertRagCorpusCoverage({ corpus, coverage })).toEqual({ corpus, coverage });
    expect(assertRagUploadResult({
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
    }).document.documentId).toBe("document-1");
    expect(assertRagRetrievalResults({ items: [{
      chunkId: "chunk-1",
      documentId: "document-1",
      pageStart: 2,
      pageEnd: 3,
      section: "INSTALLATION",
      excerpt: "Ground the motor before energizing it.",
      contentHash: "c".repeat(64),
    }] }).items).toHaveLength(1);
    expect(assertRagActivation({
      assetId: "forzy-motor-01",
      corpusId: "corpus-1",
      previousCorpusId: null,
      activatedAt: "2026-09-03T12:00:00+00:00",
    }).corpusId).toBe("corpus-1");
  });

  it("rejects inconsistent coverage and cross-corpus upload data", () => {
    expect(() => assertRagCorpusCoverage({
      corpus,
      coverage: { ...coverage, coveragePages: 11 },
    })).toThrow(/Invalid RAG contract/);
    expect(() => assertRagUploadResult({
      document: {
        documentId: "document-1",
        corpusId: "corpus-other",
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
    })).toThrow(/corpusId/);
  });
});
