import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

import { createStrictRagFake, fulfillStrictRagRoute } from "./fake-rag-api.js";


const ORIGIN = "http://127.0.0.1:4175";
const snapshot = JSON.parse(readFileSync(
  new URL("../../../contracts/v2/fixtures/snapshot-received-now.valid.json", import.meta.url),
  "utf8",
));
snapshot.capabilities.copilot = false;

const corpus = {
  corpusId: "corpus-final-1",
  assetId: "forzy-motor-01",
  manufacturer: "WEG",
  equipmentModel: "W22",
  status: "draft",
  embeddingModel: "google/text-multilingual-embedding-002",
  embeddingDimensions: 768,
  chunkTargetTokens: 700,
  chunkOverlapTokens: 100,
  minRelevanceScore: 0.2,
};
const coverage = {
  corpusId: corpus.corpusId,
  documentCount: 1,
  pageCount: 10,
  coveragePages: 9,
  chunkCount: 18,
};
const assistantResponse = {
  answer: {
    manual: "Segundo o manual, o aterramento deve preceder a energização.",
    currentState: "O assessment atual está normal e foi calculado pelo backend.",
  },
  groundingStatus: "grounded",
  citations: [
    {
      type: "manual", chunkId: "chunk-1", documentId: "document-1",
      manufacturer: "WEG", equipmentModel: "W22", revision: "2026-01",
      sourceUrl: "https://manufacturer.example/manual.pdf", pageStart: 2,
      pageEnd: 3, section: "INSTALLATION",
      excerpt: "Aterre o motor antes da energização.", contentHash: "c".repeat(64),
    },
    {
      type: "telemetry", assessmentId: "00000000-0000-4000-8000-000000000003",
      evidenceId: "ev-vibration", feature: "vibration", value: 1.2, unit: "mm/s",
      windowStart: "2026-08-12T15:00:00.000Z", windowEnd: "2026-08-12T15:00:00.000Z",
      receivedAt: "2026-08-12T15:00:00.000Z", freshnessMs: 0,
      windowSeconds: 60, qualityStatus: "ok",
    },
  ],
  corpus: {
    corpusId: corpus.corpusId, manufacturer: "WEG", equipmentModel: "W22",
    embeddingModel: corpus.embeddingModel, embeddingDimensions: 768,
    minRelevanceScore: 0.2,
  },
  models: { embedding: corpus.embeddingModel, generation: "openai/gpt-5.6-luna" },
  fallbackUsed: false,
  limitations: ["Não diagnostica causa raiz nem executa manutenção."],
  humanValidationRequired: true,
  conversationId: "00000000-0000-4000-8000-000000000010",
  traceId: "00000000-0000-4000-8000-000000000011",
  latencyMs: 850,
};


test("Preview draft to explicit publish and grounded public answer", async ({ page }) => {
  const fake = createStrictRagFake({
    origin: ORIGIN,
    corpus,
    coverage,
    snapshot,
    assistantResponse,
  });
  await page.route("**/api/v2/**", (route) => fulfillStrictRagRoute(route, fake));

  await page.goto("/rag-admin");
  await page.getByRole("form", { name: "Criar corpus draft" }).getByRole("button").click();
  await expect(page.getByRole("heading", { name: `Corpus ${corpus.corpusId}` })).toBeVisible();

  const upload = page.getByRole("form", { name: "Enviar manual pesquisável" });
  await upload.getByLabel("Manual PDF").setInputFiles({
    name: "manual.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7"),
  });
  for (const [label, value] of [
    ["Fabricante", "WEG"], ["Modelo do equipamento", "W22"],
    ["Revisão", "2026-01"], ["Idioma", "pt-BR"],
    ["URL oficial", "https://manufacturer.example/manual.pdf"],
  ]) await upload.getByLabel(label).fill(value);
  await upload.getByRole("button", { name: "Enviar e criar chunks" }).click();
  await expect(page.getByText("9 de 10 páginas com texto")).toBeVisible();
  expect(fake.state.publishCalls).toBe(0);

  const load = page.getByRole("form", { name: "Carregar outra versão de corpus" });
  await load.getByLabel("ID do corpus").fill(corpus.corpusId);
  await load.getByRole("button", { name: "Carregar corpus" }).click();
  await expect.poll(() => fake.state.coverageReads).toBe(1);
  await expect(page.getByText("9 de 10 páginas com texto")).toBeVisible();

  const retrieval = page.getByRole("form", { name: "Testar recuperação do corpus" });
  await retrieval.getByLabel("Consulta de teste").fill("Como aterrar o motor?");
  await retrieval.getByRole("button", { name: "Testar recuperação" }).click();
  await expect(page.getByText("Score absoluto de relevância: 0.820")).toBeVisible();
  await expect(page.getByText("Score de ranking híbrido: 1.000")).toBeVisible();
  expect(fake.state.publishCalls).toBe(0);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Assistente técnico" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("exige um corpus técnico ativo");
  await expect(page.getByRole("form", { name: "Consultar o assistente técnico" })).toHaveCount(0);
  expect(fake.state.published).toBe(false);

  await page.goto("/rag-admin");
  const reload = page.getByRole("form", { name: "Carregar outra versão de corpus" });
  await reload.getByLabel("ID do corpus").fill(corpus.corpusId);
  await reload.getByRole("button", { name: "Carregar corpus" }).click();
  await expect.poll(() => fake.state.coverageReads).toBe(2);

  await page.getByRole("button", { name: "Publicar corpus" }).click();
  expect(fake.state.publishCalls).toBe(0);
  await page.getByRole("button", { name: `Confirmar publicação de ${corpus.corpusId}` }).click();
  await expect.poll(() => fake.state.publishCalls).toBe(1);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Assistente técnico" })).toBeVisible();
  const assistant = page.getByRole("form", { name: "Consultar o assistente técnico" });
  await assistant.getByLabel("Pergunta técnica").fill(
    "O que o manual orienta e qual é o estado atual?",
  );
  await assistant.getByRole("button", { name: "Consultar manual e estado" }).click();

  await expect(page.getByRole("heading", { name: "Segundo o manual" })).toBeVisible();
  await expect(page.getByText(
    "Segundo o manual, o aterramento deve preceder a energização.",
  )).toBeVisible();
  await expect(page.getByRole("heading", { name: "Estado atual" })).toBeVisible();
  await expect(page.getByText(
    "O assessment atual está normal e foi calculado pelo backend.",
  )).toBeVisible();
  await expect(page.getByText("Manual · WEG W22 · revisão 2026-01")).toBeVisible();
  await expect(page.getByText("Telemetria · vibration")).toBeVisible();
  expect(fake.state.assistantRequest).toEqual({
    question: "O que o manual orienta e qual é o estado atual?",
    history: [],
  });
  expect(JSON.stringify(fake.state.assistantRequest)).not.toMatch(
    /assessment|telemetry|operationalState/i,
  );
});
