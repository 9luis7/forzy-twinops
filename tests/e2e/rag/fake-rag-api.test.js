import { describe, expect, it } from "vitest";

import { createStrictRagFake } from "./fake-rag-api.js";


const ORIGIN = "http://127.0.0.1:4175";
const corpus = {
  corpusId: "corpus-final-1", assetId: "forzy-motor-01", manufacturer: "WEG",
  equipmentModel: "W22", status: "draft",
  embeddingModel: "google/text-multilingual-embedding-002", embeddingDimensions: 768,
  chunkTargetTokens: 700, chunkOverlapTokens: 100, minRelevanceScore: 0.2,
};
const coverage = {
  corpusId: corpus.corpusId, documentCount: 1, pageCount: 10,
  coveragePages: 9, chunkCount: 18,
};

const request = async (path, { method = "GET", body, headers = {} } = {}) => ({
  url: `${ORIGIN}${path}`,
  method,
  headers,
  body: body == null ? null : Buffer.from(body),
});

const jsonRequest = async (path, value) => request(path, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(value),
});

const multipartRequest = async () => {
  const form = new FormData();
  form.append("file", new Blob(["%PDF-1.7"], { type: "application/pdf" }), "manual.pdf");
  form.append("manufacturer", "WEG");
  form.append("equipmentModel", "W22");
  form.append("revision", "2026-01");
  form.append("language", "pt-BR");
  form.append("sourceUrl", "https://manufacturer.example/manual.pdf");
  const encoded = new Request(`${ORIGIN}/upload`, { method: "POST", body: form });
  return request(`/api/v2/admin/rag/corpora/${corpus.corpusId}/documents`, {
    method: "POST",
    headers: { "content-type": encoded.headers.get("content-type") },
    body: await encoded.arrayBuffer(),
  });
};


describe("strict stateful RAG fake", () => {
  it("validates the complete admin transport and flips capability only on empty publish POST", async () => {
    const fake = createStrictRagFake({
      origin: ORIGIN, corpus, coverage, assistantResponse: { answer: "grounded" },
    });
    await fake.handle(await jsonRequest("/api/v2/admin/rag/corpora", {
      assetId: "forzy-motor-01", chunkTargetTokens: 700,
      chunkOverlapTokens: 100, minRelevanceScore: 0.2,
    }));
    await fake.handle(await multipartRequest());
    await fake.handle(await request(`/api/v2/admin/rag/corpora/${corpus.corpusId}`));
    await fake.handle(await jsonRequest(
      `/api/v2/admin/rag/corpora/${corpus.corpusId}/retrieval-test`,
      { query: "Como aterrar o motor?", limit: 6 },
    ));
    const before = await fake.handle(await request("/api/v2/assets/forzy-motor-01/snapshot"));

    expect(before.body.capabilities.copilot).toBe(false);
    expect(fake.state.publishCalls).toBe(0);

    await fake.handle(await request(
      `/api/v2/admin/rag/corpora/${corpus.corpusId}/publish`,
      { method: "POST", body: Buffer.alloc(0) },
    ));
    const after = await fake.handle(await request("/api/v2/assets/forzy-motor-01/snapshot"));
    const publicRequest = {
      question: "O que o manual orienta e qual é o estado atual?",
      history: [],
    };
    const assistant = await fake.handle(await jsonRequest(
      "/api/v2/assets/forzy-motor-01/assistant/query",
      publicRequest,
    ));

    expect(after.body.capabilities.copilot).toBe(true);
    expect(assistant.body).toEqual({ answer: "grounded" });
    expect(fake.state.assistantRequest).toEqual(publicRequest);
    expect(JSON.stringify(fake.state.assistantRequest)).not.toMatch(
      /assessment|telemetry|operationalState/i,
    );
    expect(fake.state.publishCalls).toBe(1);
    expect(fake.state.coverageReads).toBe(1);

    await expect(fake.handle(await jsonRequest(
      "/api/v2/assets/forzy-motor-01/assistant/query",
      { ...publicRequest, assessment: { status: "normal" } },
    ))).rejects.toThrow(/strict contract/);
  });

  it.each([
    ["cross origin", { url: "https://evil.invalid/api/v2/admin/rag/corpora", method: "POST", headers: {}, body: null }],
    ["wrong method", { url: `${ORIGIN}/api/v2/admin/rag/corpora`, method: "PUT", headers: {}, body: null }],
  ])("rejects %s before mutating state", async (_label, invalid) => {
    const fake = createStrictRagFake({ origin: ORIGIN, corpus, coverage });

    await expect(fake.handle(invalid)).rejects.toThrow();
    expect(fake.state).toMatchObject({ created: false, uploaded: false, published: false });
  });
});
