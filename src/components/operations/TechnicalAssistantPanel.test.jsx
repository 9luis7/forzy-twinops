import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createGatewayRagDataSource } from "../../dataSources/GatewayRagDataSource.js";
import TechnicalAssistantPanel from "./TechnicalAssistantPanel.jsx";
import CopilotDock from "../assistant/CopilotDock.jsx";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const ID = "00000000-0000-4000-8000-000000000001";
const groundedResponse = () => ({
  answer: {
    manual: "O manual orienta inspecionar a lubrificação antes da partida.",
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
      assessmentId: ID,
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
  limitations: ["Não diagnostica causa raiz nem estima probabilidade de falha ou RUL."],
  humanValidationRequired: true,
  conversationId: ID,
  traceId: "00000000-0000-4000-8000-000000000002",
  latencyMs: 850,
});

describe("TechnicalAssistantPanel availability", () => {
  it("does not expose or call the assistant unless the backend capability is exactly true", () => {
    const dataSource = { query: vi.fn() };

    render(
      <TechnicalAssistantPanel
        assetId="forzy-motor-01"
        enabled={false}
        dataSource={dataSource}
      />
    );

    expect(screen.getByRole("heading", { name: "Assistente técnico" })).toBeInTheDocument();
    expect(screen.getByText(/manual do equipamento ou o serviço de consulta está indisponível/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(dataSource.query).not.toHaveBeenCalled();
  });

  it.each(["capability", "asset", "datasource"])(
    "invalidates non-cooperative in-flight work when the %s context changes",
    async (transition) => {
      let resolveOld;
      let oldSignal;
      const oldSource = {
        query: vi.fn((assetId, input, options) => {
          if (oldSource.query.mock.calls.length === 1) {
            oldSignal = options.signal;
            return new Promise((resolve) => { resolveOld = resolve; });
          }
          const fresh = groundedResponse();
          fresh.answer.manual = "Resposta do contexto novo";
          return Promise.resolve(fresh);
        }),
      };
      const newSource = {
        query: vi.fn().mockImplementation(() => {
          const fresh = groundedResponse();
          fresh.answer.manual = "Resposta do contexto novo";
          return Promise.resolve(fresh);
        }),
      };
      const view = render(
        <TechnicalAssistantPanel assetId="asset-old" enabled dataSource={oldSource} />
      );
      const submitQuestion = (value) => {
        const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
        fireEvent.change(within(form).getByLabelText("Pergunta técnica"), {
          target: { value },
        });
        fireEvent.submit(form);
      };
      submitQuestion("Pergunta antiga");
      await waitFor(() => expect(oldSource.query).toHaveBeenCalledTimes(1));

      if (transition === "capability") {
        view.rerender(
          <TechnicalAssistantPanel assetId="asset-old" enabled={false} dataSource={oldSource} />
        );
        expect(screen.queryByRole("form", { name: "Consultar o assistente técnico" })).not.toBeInTheDocument();
        view.rerender(
          <TechnicalAssistantPanel assetId="asset-old" enabled dataSource={oldSource} />
        );
      } else if (transition === "asset") {
        view.rerender(
          <TechnicalAssistantPanel assetId="asset-new" enabled dataSource={oldSource} />
        );
      } else {
        view.rerender(
          <TechnicalAssistantPanel assetId="asset-old" enabled dataSource={newSource} />
        );
      }

      expect(oldSignal.aborted).toBe(true);
      const obsolete = groundedResponse();
      obsolete.answer.manual = "Resposta obsoleta não pode reaparecer";
      await act(async () => resolveOld(obsolete));
      expect(screen.queryByText("Resposta obsoleta não pode reaparecer")).not.toBeInTheDocument();
      expect(screen.queryByText(/Perguntas anteriores/)).not.toBeInTheDocument();

      submitQuestion("Pergunta do contexto novo");
      expect(await screen.findByText("Resposta do contexto novo")).toBeInTheDocument();
      const activeSource = transition === "datasource" ? newSource : oldSource;
      const requestInput = activeSource.query.mock.calls.at(-1)[1];
      expect(requestInput).toEqual({ question: "Pergunta do contexto novo", history: [] });
    }
  );
});

describe("TechnicalAssistantPanel grounded answer", () => {
  it("sends contextual suggestions immediately and blocks duplicate requests", async () => {
    let resolve;
    const dataSource = { query: vi.fn(() => new Promise((done) => { resolve = done; })) };
    render(<TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} suggestionContext={{ status: "watch", sensor: "s1" }} />);
    expect(dataSource.query).not.toHaveBeenCalled();
    const chip = screen.getByRole("button", { name: "Por que o motor pede atenção?" });
    fireEvent.click(chip);
    fireEvent.click(chip);
    expect(dataSource.query).toHaveBeenCalledTimes(1);
    expect(dataSource.query.mock.calls[0][1].question).toBe("Quais evidências justificam a atenção do motor S1 neste instante?");
    expect(chip).toBeDisabled();
    await act(async () => resolve(groundedResponse()));
    expect(screen.getByText("IA + manual · fontes validadas")).toBeVisible();
    expect(screen.getByRole("button", { name: "Verificar lubrificação" })).toBeEnabled();
    expect(dataSource.query).toHaveBeenCalledTimes(1);
  });

  it("formats narrative and citation timestamps for Sao Paulo without changing the response", async () => {
    const response = groundedResponse();
    response.answer.currentState = "Janela de 2026-05-19T14:49:01.524000+00:00 a 2026-05-19T14:50:01.633000+00:00.";
    const before = JSON.stringify(response);
    const dataSource = { query: vi.fn().mockResolvedValue(response) };
    render(<TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} />);
    fireEvent.click(screen.getByRole("button", { name: "Entender os dados do motor" }));
    expect(await screen.findByText(/Janela de 19\/05\/2026, 11:49:01 \(São Paulo\) a 19\/05\/2026, 11:50:01/)).toBeVisible();
    fireEvent.click(screen.getByText("Fontes e evidências"));
    fireEvent.click(screen.getByText("Sensor · Vibração média recente"));
    expect(screen.getByText("03/09/2026, 09:00:00")).toBeVisible();
    expect(screen.getByText("03/09/2026, 09:00:00")).toHaveAttribute("datetime", "2026-09-03T12:00:00+00:00");
    expect(JSON.stringify(response)).toBe(before);
  });

  it("keeps unvalidated fallback excerpts out of the main answer while preserving them in sources", async () => {
    const response = groundedResponse();
    response.fallbackUsed = true;
    response.groundingStatus = "degraded_fallback";
    response.answer.manual = "Trecho de contingência extraído do documento, sem orientação gerada validada.";
    const dataSource = { query: vi.fn().mockResolvedValue(response) };
    render(<TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} />);
    fireEvent.click(screen.getByRole("button", { name: "Entender os dados do motor" }));
    expect(await screen.findByText(/A IA não entregou uma orientação validada/)).toBeVisible();
    expect(screen.getByText(response.answer.manual)).not.toBeVisible();
    expect(screen.queryByText("IA + manual · fontes validadas")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Fontes e evidências"));
    fireEvent.click(screen.getByText("Texto de contingência"));
    expect(screen.getByText(response.answer.manual)).toBeVisible();
  });

  it("renders a complete response with separate provenance and accessible citations", async () => {
    const dataSource = { query: vi.fn().mockResolvedValue(groundedResponse()) };

    render(
      <TechnicalAssistantPanel
        assetId="forzy-motor-01"
        enabled
        dataSource={dataSource}
      />
    );

    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
    const question = within(form).getByLabelText("Pergunta técnica");
    fireEvent.change(question, { target: { value: "Como verificar o rolamento?" } });
    fireEvent.submit(form);

    expect(await screen.findByText(groundedResponse().answer.manual)).toBeInTheDocument();
    const answer = screen.getByTestId("assistant-answer");
    expect(within(answer).getByRole("heading", { name: "Segundo o manual" })).toBeInTheDocument();
    expect(within(answer).getByRole("heading", { name: "Estado atual" })).toBeInTheDocument();
    expect(within(answer).getByText(groundedResponse().answer.currentState)).toBeInTheDocument();
    expect(answer).toHaveFocus();

    const sources = screen.getByText("Fontes e evidências").closest("details");
    expect(sources).not.toHaveAttribute("open");
    expect(screen.getByText(/Inspect bearing lubrication/)).not.toBeVisible();
    fireEvent.click(screen.getByText("Fontes e evidências"));
    const manualSummary = screen.getByText(/Manual · WEG W22 · p. 4–5/);
    const manualDetails = manualSummary.closest("details");
    fireEvent.click(manualSummary);
    expect(manualDetails).toHaveAttribute("open");
    expect(within(manualDetails).getByText("MAINTENANCE · revisão 2026-01")).toBeInTheDocument();
    expect(within(manualDetails).getByText(/Inspect bearing lubrication/)).toBeInTheDocument();
    expect(within(manualDetails).getByText(`SHA-256 ${"a".repeat(64)}`)).toBeInTheDocument();
    expect(within(manualDetails).getByRole("link", { name: "Abrir fonte oficial" })).toHaveAttribute(
      "href",
      "https://manufacturer.example/manual.pdf"
    );

    const telemetrySummary = screen.getByText(/Sensor · Vibração média recente/);
    const telemetryDetails = telemetrySummary.closest("details");
    fireEvent.click(telemetrySummary);
    expect(within(telemetryDetails).getByText("2,4 mm/s")).toBeInTheDocument();
    expect(within(telemetryDetails).getByText(`Assessment ${ID}`)).toBeInTheDocument();
    expect(within(telemetryDetails).getByText(/Frescor 1\.000 ms · qualidade ok/)).toBeInTheDocument();
    expect(screen.getByText(/Validação humana obrigatória/)).toBeInTheDocument();
    expect(screen.getByText(groundedResponse().limitations[0])).toBeInTheDocument();
  });

  it("renders repeated chunks with nullable sections without duplicate-key diagnostics", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const response = groundedResponse();
    const repeatedChunk = {
      ...response.citations[0],
      section: null,
    };
    response.citations = [
      repeatedChunk,
      {
        ...repeatedChunk,
        excerpt: "Verify the bearing lubrication interval before operation.",
      },
    ];
    const dataSource = { query: vi.fn().mockResolvedValue(response) };

    render(
      <TechnicalAssistantPanel
        assetId="forzy-motor-01"
        enabled
        dataSource={dataSource}
      />
    );

    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
    fireEvent.change(within(form).getByLabelText("Pergunta técnica"), {
      target: { value: "Quais trechos tratam da lubrificação?" },
    });
    fireEvent.submit(form);

    expect(await screen.findByText(repeatedChunk.excerpt)).toBeInTheDocument();
    expect(screen.getByText("Verify the bearing lubrication interval before operation.")).toBeInTheDocument();
    expect(screen.getAllByText(/Seção não identificada/)).toHaveLength(2);
    expect(consoleError).not.toHaveBeenCalled();
    expect(consoleWarn).not.toHaveBeenCalled();
  });

  it("survives the StrictMode effect replay and reveals only the complete validated answer", async () => {
    let resolveQuery;
    const dataSource = {
      query: vi.fn(() => new Promise((resolve) => { resolveQuery = resolve; })),
    };

    render(
      <React.StrictMode>
        <TechnicalAssistantPanel
          assetId="forzy-motor-01"
          enabled
          dataSource={dataSource}
        />
      </React.StrictMode>
    );

    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
    fireEvent.change(within(form).getByLabelText("Pergunta técnica"), {
      target: { value: "Como verificar o rolamento?" },
    });
    fireEvent.submit(form);

    expect(screen.getByRole("status", { name: "Consultando fontes validadas" })).toHaveTextContent(
      "As citações serão validadas antes de aparecer."
    );
    expect(screen.queryByTestId("assistant-answer")).not.toBeInTheDocument();

    resolveQuery(groundedResponse());

    expect(await screen.findByTestId("assistant-answer")).toHaveTextContent(
      groundedResponse().answer.manual
    );
  });

  it("aborts on cancel, suppresses stale completions and keeps the newest response", async () => {
    const pending = [];
    const dataSource = {
      query: vi.fn((assetId, input, options) => new Promise((resolve) => {
        pending.push({ assetId, input, options, resolve });
      })),
    };
    render(
      <TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} />
    );
    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
    const textbox = within(form).getByLabelText("Pergunta técnica");

    fireEvent.change(textbox, { target: { value: "Primeira pergunta" } });
    fireEvent.submit(form);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar consulta" }));
    expect(pending[0].options.signal.aborted).toBe(true);

    fireEvent.change(textbox, { target: { value: "Pergunta mais recente" } });
    fireEvent.submit(form);
    const newest = groundedResponse();
    newest.answer.manual = "Resposta mais recente";
    await act(async () => pending[1].resolve(newest));
    expect(await screen.findByText("Resposta mais recente")).toBeInTheDocument();

    const stale = groundedResponse();
    stale.answer.manual = "Resposta antiga que não pode aparecer";
    await act(async () => pending[0].resolve(stale));
    expect(screen.queryByText("Resposta antiga que não pode aparecer")).not.toBeInTheDocument();
    expect(screen.getByText("Resposta mais recente")).toBeInTheDocument();
  });

  it("aborts an in-flight query when unmounted", () => {
    let signal;
    const dataSource = {
      query: vi.fn((assetId, input, options) => {
        signal = options.signal;
        return new Promise(() => {});
      }),
    };
    const view = render(
      <TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} />
    );
    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
    fireEvent.change(within(form).getByLabelText("Pergunta técnica"), {
      target: { value: "Consulta pendente" },
    });
    fireEvent.submit(form);

    view.unmount();

    expect(signal.aborted).toBe(true);
  });

  it("reuses the server conversation id and sends only the four latest completed turns", async () => {
    const responses = Array.from({ length: 6 }, (_, index) => ({
      ...groundedResponse(),
      answer: {
        ...groundedResponse().answer,
        manual: `Resposta documental ${index + 1}`,
      },
    }));
    const dataSource = { query: vi.fn().mockImplementation(() => Promise.resolve(
      responses[dataSource.query.mock.calls.length - 1]
    )) };

    render(
      <TechnicalAssistantPanel
        assetId="forzy-motor-01"
        enabled
        dataSource={dataSource}
      />
    );

    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
    for (let index = 0; index < 6; index += 1) {
      fireEvent.change(within(form).getByLabelText("Pergunta técnica"), {
        target: { value: `Pergunta ${index + 1}` },
      });
      fireEvent.submit(form);
      await waitFor(() => expect(dataSource.query).toHaveBeenCalledTimes(index + 1));
      await screen.findByText(`Resposta documental ${index + 1}`);
    }

    expect(dataSource.query.mock.calls[0][1]).toEqual({
      question: "Pergunta 1",
      history: [],
    });
    expect(dataSource.query.mock.calls[5][1].conversationId).toBe(ID);
    expect(dataSource.query.mock.calls[5][1].history).toHaveLength(4);
    expect(dataSource.query.mock.calls[5][1].history.map((turn) => turn.question)).toEqual([
      "Pergunta 2",
      "Pergunta 3",
      "Pergunta 4",
      "Pergunta 5",
    ]);
    expect(dataSource.query.mock.calls[5][1].history[0].answer).toMatch(
      /Segundo o manual:\nResposta documental 2\nEstado atual:/
    );
    expect(screen.getByText("Pergunta 3")).toBeInTheDocument();
    expect(screen.getByText("Pergunta 5")).toBeInTheDocument();
    expect(screen.queryByText("Pergunta 2")).not.toBeInTheDocument();
    expect(screen.getByText("Pergunta 5")).not.toBeVisible();
    fireEvent.click(screen.getByText("Perguntas anteriores (3)"));
    expect(screen.getByText("Pergunta 5")).toBeVisible();
  });

  it("serializes two 6000-character answer sections within the real history contract", async () => {
    const fetchImpl = vi.fn().mockImplementation(async () => {
      const response = groundedResponse();
      const callNumber = fetchImpl.mock.calls.length;
      response.answer = callNumber === 1
        ? { manual: "M".repeat(6_000), currentState: "C".repeat(6_000) }
        : { manual: `Manual ${callNumber}`, currentState: `Estado ${callNumber}` };
      response.traceId = `00000000-0000-4000-8000-${String(callNumber + 1).padStart(12, "0")}`;
      return { ok: true, status: 200, json: async () => response };
    });
    const dataSource = createGatewayRagDataSource({ fetchImpl });
    render(
      <TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} />
    );
    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });

    for (let index = 1; index <= 6; index += 1) {
      fireEvent.change(within(form).getByLabelText("Pergunta técnica"), {
        target: { value: `Pergunta limite ${index}` },
      });
      fireEvent.submit(form);
      await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(index));
      await waitFor(() => expect(within(form).getByLabelText("Pergunta técnica")).toBeEnabled());
    }

    const secondBody = JSON.parse(fetchImpl.mock.calls[1][1].body);
    expect(secondBody.conversationId).toBe(ID);
    expect(secondBody.history).toHaveLength(1);
    expect(secondBody.history[0].answer.length).toBeLessThanOrEqual(6_000);
    expect(secondBody.history[0].answer).toMatch(/^Segundo o manual:\nM+/);
    expect(secondBody.history[0].answer).toMatch(/\nEstado atual:\nC+/);

    const sixthBody = JSON.parse(fetchImpl.mock.calls[5][1].body);
    expect(sixthBody.conversationId).toBe(ID);
    expect(sixthBody.history).toHaveLength(4);
    expect(sixthBody.history.map((turn) => turn.question)).toEqual([
      "Pergunta limite 2",
      "Pergunta limite 3",
      "Pergunta limite 4",
      "Pergunta limite 5",
    ]);
  });
});

describe("TechnicalAssistantPanel explicit safety states", () => {
  it.each([
    ["manual_insufficient", false, "não traz evidência suficiente"],
    ["operational_unavailable", false, "dados atuais estão indisponíveis"],
    ["out_of_scope", false, "fora do escopo seguro"],
    ["degraded_fallback", true, "orientação de contingência disponível"],
  ])("renders %s as a first-class state", async (groundingStatus, fallbackUsed, expected) => {
    const response = groundedResponse();
    response.groundingStatus = groundingStatus;
    response.fallbackUsed = fallbackUsed;
    response.citations = [];
    const dataSource = { query: vi.fn().mockResolvedValue(response) };
    render(
      <TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} />
    );
    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
    fireEvent.change(within(form).getByLabelText("Pergunta técnica"), {
      target: { value: "Explique o estado" },
    });
    fireEvent.submit(form);

    expect(await screen.findByText(new RegExp(expected, "i"))).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Segundo o manual" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Estado atual" })).toBeInTheDocument();
  });

  it.each([
    ["O dado operacional está antigo e deve ser atualizado.", /dado operacional está antigo/i],
    ["Este é o último estado conhecido e não uma medição recebida agora.", /último estado conhecido/i],
    ["O equipamento está fora da janela operacional.", /fora da janela operacional/i],
  ])("surfaces the server-owned operational warning: %s", async (currentState, expected) => {
    const response = groundedResponse();
    response.answer.currentState = currentState;
    const dataSource = { query: vi.fn().mockResolvedValue(response) };
    render(
      <TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} />
    );
    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
    fireEvent.change(within(form).getByLabelText("Pergunta técnica"), {
      target: { value: "Qual é o contexto operacional?" },
    });
    fireEvent.submit(form);

    expect(await screen.findByText(expected)).toBeInTheDocument();
  });

  it("sanitizes an unreachable service instead of fabricating or echoing detail", async () => {
    const dataSource = {
      query: vi.fn().mockRejectedValue(new Error("postgres://user:secret@example.invalid")),
    };
    render(
      <TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} />
    );
    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
    fireEvent.change(within(form).getByLabelText("Pergunta técnica"), {
      target: { value: "Qual é o estado?" },
    });
    fireEvent.submit(form);

    expect(await screen.findByRole("alert")).toHaveTextContent(/temporariamente indisponível/);
    expect(screen.queryByText(/secret/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-answer")).not.toBeInTheDocument();
  });

  it.each([
    ["with manual evidence", true],
    ["without manual evidence", false],
  ])("uses neutral degraded copy %s", async (_, withManualCitation) => {
    const response = groundedResponse();
    response.groundingStatus = "degraded_fallback";
    response.fallbackUsed = true;
    response.citations = withManualCitation
      ? response.citations.filter((citation) => citation.type === "manual")
      : [];
    const dataSource = { query: vi.fn().mockResolvedValue(response) };
    render(
      <TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} />
    );
    const form = screen.getByRole("form", { name: "Consultar o assistente técnico" });
    fireEvent.change(within(form).getByLabelText("Pergunta técnica"), {
      target: { value: "Consulte o manual" },
    });
    fireEvent.submit(form);

    expect(await screen.findByText(/resposta completa não pôde ser validada/i)).toBeInTheDocument();
    if (withManualCitation) {
      expect(screen.getByText(/Manual · WEG W22/)).toBeInTheDocument();
    } else {
      expect(screen.getByText("Nenhuma citação documental sustentou esta resposta.")).toBeInTheDocument();
    }
    expect(screen.queryByText(/serviço de geração/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/fallback extrativo/i)).not.toBeInTheDocument();
  });
});

describe("TechnicalAssistantPanel in a collapsible copilot", () => {
  it("preserves a draft and ongoing query across closing, without moving focus for a hidden answer", async () => {
    let finish;
    let signal;
    const dataSource = {
      query: vi.fn((assetId, input, options) => {
        signal = options.signal;
        if (dataSource.query.mock.calls.length === 1) {
          return new Promise((resolve) => { finish = resolve; });
        }
        return Promise.resolve(groundedResponse());
      }),
    };
    function Harness() {
      const [open, setOpen] = React.useState(false);
      return <CopilotDock open={open} onOpenChange={setOpen}>
        <TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} isActive={open} />
      </CopilotDock>;
    }
    render(<Harness />);
    const launcher = screen.getByRole("button", { name: "Copiloto" });
    fireEvent.click(launcher);
    fireEvent.change(screen.getByLabelText("Pergunta técnica"), { target: { value: "Como verificar o rolamento?" } });
    fireEvent.click(screen.getByRole("button", { name: "Fechar copiloto" }));
    fireEvent.click(launcher);
    expect(screen.getByLabelText("Pergunta técnica")).toHaveValue("Como verificar o rolamento?");
    fireEvent.submit(screen.getByRole("form", { name: "Consultar o assistente técnico" }));
    expect(dataSource.query).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Fechar copiloto" }));
    expect(signal.aborted).toBe(false);
    expect(launcher).toHaveFocus();

    await act(async () => { finish(groundedResponse()); });
    expect(signal.aborted).toBe(false);
    expect(launcher).toHaveFocus();
    expect(screen.getByTestId("assistant-answer")).not.toBeVisible();
    fireEvent.click(launcher);
    expect(screen.getByTestId("assistant-answer")).toBeVisible();
    expect(screen.getByRole("button", { name: "Fechar copiloto" })).toHaveFocus();
    expect(screen.getByLabelText("Pergunta técnica")).toHaveValue("");

    fireEvent.change(screen.getByLabelText("Pergunta técnica"), { target: { value: "E a lubrificação?" } });
    fireEvent.submit(screen.getByRole("form", { name: "Consultar o assistente técnico" }));
    await waitFor(() => expect(dataSource.query).toHaveBeenCalledTimes(2));
    expect(dataSource.query.mock.calls[1][1]).toMatchObject({
      conversationId: ID,
      history: [{ question: "Como verificar o rolamento?", answer: expect.stringContaining(groundedResponse().answer.manual) }],
    });
    await waitFor(() => expect(screen.getByTestId("assistant-answer")).toHaveFocus());
    const technical = screen.getByText("Detalhes técnicos da resposta").closest("details");
    expect(technical).not.toHaveAttribute("open");
    expect(within(technical).getByText(/Corpus corpus-1 · trace/)).not.toBeVisible();
  });

  it("does not refocus an existing answer just because isActive changes", async () => {
    const dataSource = { query: vi.fn().mockResolvedValue(groundedResponse()) };
    const view = render(<TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} isActive={false} />);
    fireEvent.change(screen.getByLabelText("Pergunta técnica"), { target: { value: "Consulte o manual" } });
    fireEvent.submit(screen.getByRole("form", { name: "Consultar o assistente técnico" }));
    const answer = await screen.findByTestId("assistant-answer");
    expect(answer).not.toHaveFocus();
    screen.getByLabelText("Pergunta técnica").focus();
    view.rerender(<TechnicalAssistantPanel assetId="forzy-motor-01" enabled dataSource={dataSource} isActive />);
    expect(screen.getByLabelText("Pergunta técnica")).toHaveFocus();
    expect(dataSource.query).toHaveBeenCalledTimes(1);
  });
});
