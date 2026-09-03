import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RagAdminPanel from "./RagAdminPanel.jsx";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const corpus = (overrides = {}) => ({
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
  ...overrides,
});

const coverage = (corpusId = "corpus-1") => ({
  corpusId,
  documentCount: 1,
  pageCount: 10,
  coveragePages: 9,
  chunkCount: 18,
});

const activation = (corpusId = "corpus-1") => ({
  assetId: "forzy-motor-01",
  corpusId,
  previousCorpusId: null,
  activatedAt: "2026-09-03T12:00:00+00:00",
});

describe("RagAdminPanel", () => {
  it("supports draft, upload, coverage, retrieval, explicit publish/reactivate and corpus switch", async () => {
    const dataSource = {
      createDraft: vi.fn().mockResolvedValue(corpus()),
      uploadDocument: vi.fn().mockResolvedValue({
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
        coverage: coverage(),
      }),
      getCorpus: vi.fn().mockResolvedValue({
        corpus: corpus({ corpusId: "corpus-previous", status: "published" }),
        coverage: coverage("corpus-previous"),
      }),
      testRetrieval: vi.fn().mockResolvedValue({ items: [{
        chunkId: "chunk-1",
        documentId: "document-1",
        pageStart: 2,
        pageEnd: 3,
        section: "INSTALLATION",
        excerpt: "Ground the motor before energizing it.",
        contentHash: "c".repeat(64),
      }] }),
      publish: vi.fn().mockResolvedValue(activation()),
      reactivate: vi.fn().mockResolvedValue(activation("corpus-previous")),
    };
    render(<RagAdminPanel dataSource={dataSource} assetId="forzy-motor-01" />);

    expect(screen.getByRole("heading", { name: "Administração do RAG" })).toBeInTheDocument();
    const createForm = screen.getByRole("form", { name: "Criar corpus draft" });
    fireEvent.change(within(createForm).getByLabelText("Relevância mínima"), {
      target: { value: "0.25" },
    });
    fireEvent.submit(createForm);
    expect(await screen.findByText("Corpus corpus-1")).toBeInTheDocument();
    expect(dataSource.createDraft).toHaveBeenCalledWith({
      assetId: "forzy-motor-01",
      chunkTargetTokens: 700,
      chunkOverlapTokens: 100,
      minRelevanceScore: 0.25,
    }, expect.objectContaining({ signal: expect.any(AbortSignal) }));

    const uploadForm = screen.getByRole("form", { name: "Enviar manual pesquisável" });
    const file = new File(["%PDF-1.7"], "manual.pdf", { type: "application/pdf" });
    fireEvent.change(within(uploadForm).getByLabelText("Manual PDF"), {
      target: { files: [file] },
    });
    for (const [label, value] of [
      ["Fabricante", "WEG"],
      ["Modelo do equipamento", "W22"],
      ["Revisão", "2026-01"],
      ["Idioma", "pt-BR"],
      ["URL oficial", "https://manufacturer.example/manual.pdf"],
    ]) {
      fireEvent.change(within(uploadForm).getByLabelText(label), { target: { value } });
    }
    fireEvent.submit(uploadForm);

    expect(await screen.findByText("9 de 10 páginas com texto")).toBeInTheDocument();
    expect(screen.getByText("18 chunks · 1 documento")).toBeInTheDocument();
    expect(dataSource.uploadDocument).toHaveBeenCalledWith(
      "corpus-1",
      expect.objectContaining({ file, manufacturer: "WEG", equipmentModel: "W22" }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    const retrievalForm = screen.getByRole("form", { name: "Testar recuperação do corpus" });
    fireEvent.change(within(retrievalForm).getByLabelText("Consulta de teste"), {
      target: { value: "grounding" },
    });
    fireEvent.submit(retrievalForm);
    expect(await screen.findByText("Ground the motor before energizing it.")).toBeInTheDocument();
    expect(screen.getByText("Páginas 2–3 · INSTALLATION")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Publicar corpus" }));
    expect(dataSource.publish).not.toHaveBeenCalled();
    expect(screen.getByText(/confirme a publicação do corpus corpus-1/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar publicação de corpus-1" }));
    await waitFor(() => expect(dataSource.publish).toHaveBeenCalledWith(
      "corpus-1",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));

    const switchForm = screen.getByRole("form", { name: "Carregar outra versão de corpus" });
    fireEvent.change(within(switchForm).getByLabelText("ID do corpus"), {
      target: { value: "corpus-previous" },
    });
    fireEvent.submit(switchForm);
    expect(await screen.findByText("Corpus corpus-previous")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reativar corpus" }));
    expect(dataSource.reactivate).not.toHaveBeenCalled();
    expect(screen.getByText(/confirme a reativação do corpus corpus-previous/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar reativação de corpus-previous" }));
    await waitFor(() => expect(dataSource.reactivate).toHaveBeenCalledWith(
      "corpus-previous",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
  });

  it("shows a stable error state without exposing backend or uploaded content", async () => {
    const dataSource = {
      createDraft: vi.fn().mockRejectedValue(new Error("postgres://user:secret@example.invalid")),
      uploadDocument: vi.fn(),
      getCorpus: vi.fn(),
      testRetrieval: vi.fn(),
      publish: vi.fn(),
      reactivate: vi.fn(),
    };
    render(<RagAdminPanel dataSource={dataSource} assetId="forzy-motor-01" />);
    fireEvent.submit(screen.getByRole("form", { name: "Criar corpus draft" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A operação administrativa não pôde ser concluída"
    );
    expect(screen.queryByText(/secret/)).not.toBeInTheDocument();
  });

  it("keeps the two-step publication confirmation described and keyboard-focusable", async () => {
    const dataSource = {
      createDraft: vi.fn().mockResolvedValue(corpus()),
      uploadDocument: vi.fn(),
      getCorpus: vi.fn(),
      testRetrieval: vi.fn(),
      publish: vi.fn().mockResolvedValue(activation()),
      reactivate: vi.fn(),
    };
    render(<RagAdminPanel dataSource={dataSource} assetId="forzy-motor-01" />);
    fireEvent.submit(screen.getByRole("form", { name: "Criar corpus draft" }));
    const publishTrigger = await screen.findByRole("button", { name: "Publicar corpus" });

    publishTrigger.focus();
    fireEvent.click(publishTrigger);
    const dialog = screen.getByRole("alertdialog", {
      name: "Confirme a publicação do corpus corpus-1",
    });
    const descriptionId = dialog.getAttribute("aria-describedby");
    expect(descriptionId).toBeTruthy();
    expect(document.getElementById(descriptionId)).toHaveTextContent("corpus-1");
    const confirmButton = within(dialog).getByRole("button", {
      name: "Confirmar publicação de corpus-1",
    });
    expect(confirmButton).toHaveFocus();

    const cancelButton = within(dialog).getByRole("button", { name: "Manter corpus atual" });
    cancelButton.focus();
    fireEvent.click(cancelButton);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(publishTrigger).toHaveFocus();
  });

  it("restores confirmation focus after failure and permits a keyboard retry", async () => {
    let rejectFirstPublish;
    const dataSource = {
      createDraft: vi.fn().mockResolvedValue(corpus()),
      uploadDocument: vi.fn(),
      getCorpus: vi.fn(),
      testRetrieval: vi.fn(),
      publish: vi.fn()
        .mockImplementationOnce(() => new Promise((resolve, reject) => {
          rejectFirstPublish = reject;
        }))
        .mockResolvedValueOnce(activation()),
      reactivate: vi.fn(),
    };
    render(<RagAdminPanel dataSource={dataSource} assetId="forzy-motor-01" />);
    fireEvent.submit(screen.getByRole("form", { name: "Criar corpus draft" }));
    const publishTrigger = await screen.findByRole("button", { name: "Publicar corpus" });
    fireEvent.click(publishTrigger);
    const confirmButton = screen.getByRole("button", {
      name: "Confirmar publicação de corpus-1",
    });
    expect(confirmButton).toHaveFocus();
    fireEvent.click(confirmButton);
    within(screen.getByRole("form", { name: "Criar corpus draft" }))
      .getByLabelText("Relevância mínima")
      .focus();

    await act(async () => rejectFirstPublish(new Error("provider unavailable")));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A operação administrativa não pôde ser concluída"
    );
    await waitFor(() => expect(confirmButton).toHaveFocus());

    fireEvent.click(confirmButton);
    await waitFor(() => expect(dataSource.publish).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Corpus corpus-1 ativado em/)).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(publishTrigger).toHaveFocus();
  });
});
