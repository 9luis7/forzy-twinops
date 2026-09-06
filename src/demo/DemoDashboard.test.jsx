import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import DemoDashboard from "./DemoDashboard.jsx";
import { buildTrendPoints } from "./DemoTrends.jsx";
import { context, dataset, deferred, event, frame, time } from "./testFixtures.js";
import { demoSuggestions } from "./demoSuggestions.js";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); sessionStorage.clear(); });
it("prepares the real gateway session and offers keyboard controls with static 3D fallback", async () => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const source = { datasets: vi.fn(async () => [dataset]), create: vi.fn(async () => ({ runId: "test-run", token: "test", context: context() })), control: vi.fn(async () => context(1)) };
  render(<DemoDashboard dataSource={source} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Preparar replay" })).toBeEnabled());
  expect(screen.getByRole("heading", { name: "Escolha um roteiro e prepare a demonstração." })).toBeVisible();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.queryByText(/Uma demonstração orientada por evidências/)).not.toBeInTheDocument();
  expect(screen.getByText(/A avaliação dos sensores é automática/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Preparar replay" }));
  await screen.findByRole("button", { name: "Avançar 1 par" });
  expect(screen.getByLabelText("Sensores na prévia estática")).toBeVisible();
  fireEvent.keyDown(screen.getByRole("main"), { code: "ArrowRight" });
  await waitFor(() => expect(source.control).toHaveBeenCalled()); expect(source.control.mock.calls[0][1].action).toBe("step");
  await waitFor(() => expect(screen.getByRole("button", { name: "Avançar 1 par" })).toBeEnabled());
  fireEvent.keyDown(screen.getByRole("main"), { code: "Space" });
  await waitFor(() => expect(source.control).toHaveBeenCalledTimes(2)); expect(source.control.mock.calls[1][1].action).toBe("play");
});

const readyContext = (extra = {}) => context(1, {
  replay: { ...context().replay, cursor: 1, sourceRow: 141, sourceTime: time, arrivalTime: time },
  ...extra,
});
const recommendation = {
  answer: { currentState: "A vibração merece acompanhamento humano.", manual: "O manual orienta verificar a lubrificação dos rolamentos." },
  citations: [{ type: "manual", sourceUrl: "https://manufacturer.example/manual.pdf", manufacturer: "WEG", equipmentModel: "W22", pageStart: 4, pageEnd: 5, excerpt: "Verificar a lubrificação dos rolamentos." }],
  limitations: ["O score não representa probabilidade de falha."],
  fallbackUsed: false,
};
const readyEvent = () => event({ status: "ready", sourceRow: 141, recommendation });
const demoSource = (extra = {}) => ({
  datasets: vi.fn(async () => [dataset]),
  create: vi.fn(async () => ({ runId: "test-run", token: "test", context: readyContext() })),
  query: vi.fn(),
  recommend: vi.fn(),
  control: vi.fn(async () => readyContext()),
  ...extra,
});
const prepare = async (source) => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
  const view = render(<DemoDashboard dataSource={source} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Preparar replay" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Preparar replay" }));
  await screen.findByRole("button", { name: "Avançar 1 par" });
  return view;
};

it("keeps the demo optional, exposes history clocks and collapses processing details", async () => {
  await prepare(demoSource());
  expect(screen.getByRole("heading", { name: "Reprodução do histórico" })).toBeVisible();
  expect(screen.getByText("DEMONSTRAÇÃO")).toBeVisible();
  expect(screen.getByRole("link", { name: "Voltar à visão geral" })).toHaveAttribute("href", "/");
  expect(screen.getByText(/Medição histórica/)).toBeVisible();
  expect(screen.getByText(/Chegada na reprodução/)).toBeVisible();
  expect(screen.getByText(/Fonte: Histórico de teste/)).toBeVisible();
  const processing = screen.getByText("Detalhes do processamento e da origem").closest("details");
  expect(processing).not.toHaveAttribute("open");
  expect(within(processing).getByText("Pares recebidos")).not.toBeVisible();
  expect(screen.getByText(/Não representa probabilidade de falha nem comprovação/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Copiloto" })).toHaveAttribute("aria-expanded", "false");
});

it("preserves the manual draft and pending request when closing the dock, without moving focus on completion", async () => {
  const pending = deferred();
  const source = demoSource({ query: vi.fn(() => pending.promise) });
  const view = await prepare(source);
  const launcher = screen.getByRole("button", { name: "Copiloto" });
  fireEvent.click(launcher);
  expect(view.container.querySelector("main")).toHaveClass("has-copilot-open");
  const textbox = screen.getByRole("textbox", { name: "Pergunta" });
  fireEvent.change(textbox, { target: { value: "O que verificar no motor?" } });
  fireEvent.click(screen.getByRole("button", { name: "Fechar copiloto" }));
  expect(view.container.querySelector("main")).not.toHaveClass("has-copilot-open");
  fireEvent.click(launcher);
  expect(screen.getByRole("textbox", { name: "Pergunta" })).toBe(textbox);
  expect(textbox).toHaveValue("O que verificar no motor?");
  fireEvent.submit(screen.getByRole("form", { name: "Perguntar ao copiloto da demonstração" }));
  expect(source.query).toHaveBeenCalledTimes(1);
  expect(source.query.mock.calls[0][1]).toEqual({ question: "O que verificar no motor?", contextRevision: 1 });
  const signal = source.query.mock.calls[0][2].signal;
  fireEvent.click(screen.getByRole("button", { name: "Fechar copiloto" }));
  expect(signal.aborted).toBe(false);
  expect(launcher).toHaveFocus();
  await act(async () => { pending.resolve({ contextRevision: 1, sourceRow: 141, observedAt: time, response: recommendation }); await pending.promise; });
  expect(launcher).toHaveFocus();
  expect(signal.aborted).toBe(false);
  expect(screen.getByText(recommendation.answer.manual)).not.toBeVisible();
  fireEvent.click(launcher);
  expect(screen.getByText(recommendation.answer.manual)).toBeVisible();
  expect(textbox).toHaveValue("O que verificar no motor?");
  expect(screen.getByRole("button", { name: "Fechar copiloto" })).toHaveFocus();
  expect(source.query).toHaveBeenCalledTimes(1);
  source.query.mockResolvedValueOnce({ contextRevision: 1, sourceRow: 141, observedAt: time, response: recommendation });
  fireEvent.change(textbox, { target: { value: "E a lubrificação?" } });
  fireEvent.submit(screen.getByRole("form", { name: "Perguntar ao copiloto da demonstração" }));
  await waitFor(() => expect(screen.getByRole("article", { name: "Resposta: E a lubrificação?" })).toHaveFocus());
});

it("opens an existing event orientation without another query and ignores replay shortcuts from the chat portal", async () => {
  const source = demoSource({ create: vi.fn(async () => ({ runId: "test-run", token: "test", context: readyContext({ events: [readyEvent()] }) })) });
  await prepare(source);
  const launcher = screen.getByRole("button", { name: "Copiloto" });
  expect(launcher).toHaveAttribute("aria-expanded", "false");
  expect(launcher).toHaveAccessibleDescription("1 orientações disponíveis.");
  fireEvent.click(screen.getByRole("button", { name: /Ver orientação: Atenção sustentada/ }));
  const answer = screen.getByRole("article", { name: "Orientação do evento selecionado" });
  expect(answer).toHaveFocus();
  expect(within(answer).getByText(recommendation.answer.manual)).toBeVisible();
  const sourceLink = within(answer).getByRole("link", { name: "Abrir fonte oficial", hidden: true });
  expect(sourceLink).toHaveAttribute("href", "https://manufacturer.example/manual.pdf");
  expect(sourceLink).not.toBeVisible();
  expect(source.query).not.toHaveBeenCalled();
  expect(source.recommend).not.toHaveBeenCalled();
  fireEvent.keyDown(answer, { code: "Space" });
  fireEvent.keyDown(answer, { code: "ArrowRight" });
  fireEvent.keyDown(screen.getByRole("complementary", { name: "Copiloto" }), { code: "Space" });
  expect(source.control).not.toHaveBeenCalled();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(launcher).toHaveFocus();
  expect(launcher).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(launcher);
  fireEvent.click(screen.getByRole("button", { name: "Fechar orientação do evento" }));
  expect(screen.getByRole("textbox", { name: "Pergunta" })).toHaveFocus();
  expect(source.query).not.toHaveBeenCalled();
  fireEvent.keyDown(screen.getByRole("main"), { code: "ArrowRight" });
  await waitFor(() => expect(source.control).toHaveBeenCalledTimes(1));
});

it("clears selected event and draft on a new generation, suppressing an obsolete manual completion", async () => {
  const pending = deferred();
  const source = demoSource({
    create: vi.fn(async () => ({ runId: "test-run", token: "test", context: readyContext({ events: [readyEvent()] }) })),
    control: vi.fn(async () => context(2, { replay: { ...context().replay, generation: 1 } })),
    query: vi.fn(() => pending.promise),
  });
  await prepare(source);
  fireEvent.click(screen.getByRole("button", { name: /Ver orientação: Atenção sustentada/ }));
  fireEvent.change(screen.getByRole("textbox", { name: "Pergunta" }), { target: { value: "Consulta da geração anterior" } });
  fireEvent.submit(screen.getByRole("form", { name: "Perguntar ao copiloto da demonstração" }));
  const signal = source.query.mock.calls[0][2].signal;
  fireEvent.click(screen.getByRole("button", { name: "Reiniciar" }));
  await waitFor(() => expect(screen.getByRole("textbox", { name: "Pergunta" })).toHaveValue(""));
  expect(signal.aborted).toBe(true);
  expect(screen.queryByRole("article", { name: "Orientação do evento selecionado" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copiloto" })).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText(/Prepare a reprodução e avance uma leitura/)).toBeVisible();
  await act(async () => { pending.resolve({ contextRevision: 1, sourceRow: 141, observedAt: time, response: recommendation }); await pending.promise; });
  expect(screen.queryByText(recommendation.answer.manual)).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Consulta da geração anterior" })).not.toBeInTheDocument();
});

it("clears an event selection even when a new session reuses its event id", async () => {
  const source = demoSource({ create: vi.fn()
    .mockResolvedValueOnce({ runId: "test-run", token: "test", context: readyContext({ events: [readyEvent()] }) })
    .mockResolvedValueOnce({ runId: "new-run", token: "new", context: readyContext({ replay: { ...readyContext().replay, runId: "new-run" }, events: [readyEvent()] }) }) });
  await prepare(source);
  fireEvent.click(screen.getByRole("button", { name: /Ver orientação: Atenção sustentada/ }));
  fireEvent.change(screen.getByRole("textbox", { name: "Pergunta" }), { target: { value: "Rascunho antigo" } });
  fireEvent.click(screen.getByRole("button", { name: "Nova sessão" }));
  await waitFor(() => expect(source.create).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.getByRole("textbox", { name: "Pergunta" })).toBeEnabled());
  expect(screen.queryByRole("article", { name: "Orientação do evento selecionado" })).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Pergunta" })).toHaveValue("");
});
it("preserves source order and repetitions, inserting null at a gap without interpolation", () => {
  const rows = [frame(), frame("s2"), frame("s1", 142), frame("s2", 142), frame("s1", 143, { gapBefore: true }), frame("s2", 143, { gapBefore: true })];
  const points = buildTrendPoints(rows, "temperature");
  expect(points.map((p) => p.row)).toEqual([141, 142, "gap-143", 143]);
  expect(points[2]).toMatchObject({ s1: null, s2: null, break: true }); expect(points[1].s1).toBe(points[0].s1);
});
it("keeps pause/restart clickable during advance and acknowledges the queued pause", async () => {
  vi.useFakeTimers(); vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const pending = deferred();
  const running = context(1, { replay: { ...context().replay, state: "running" } });
  const source = { datasets: vi.fn(async () => [dataset]), create: vi.fn(async () => ({ runId: "test-run", token: "test", context: running })), advance: vi.fn(() => pending.promise), control: vi.fn(async () => context(3)) };
  await act(async () => { render(<DemoDashboard dataSource={source} />); });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Preparar replay" })); });
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(source.advance).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Ⅱ Pausar" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Reiniciar" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Ⅱ Pausar" }));
  expect(screen.getByRole("button", { name: "Pausa solicitada…" })).toBeDisabled();
  expect(screen.getByText(/Aguardando a confirmação do avanço em curso/)).toBeVisible();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); }); expect(source.advance).toHaveBeenCalledTimes(1);
  await act(async () => { pending.resolve(context(2)); await pending.promise; });
  expect(source.control.mock.calls[0][1]).toMatchObject({ action: "pause", expectedRevision: 2 });
});
it.each(["ready", "degraded"])("shows request feedback across advances and preserves a %s event before POST finishes", async (status) => {
  vi.useFakeTimers(); vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const pending = deferred();
  const events = [event(), event({ eventId: "waiting-event", kind: "recovery" })];
  const running = (revision, nextEvents = events) => context(revision, {
    events: nextEvents, replay: { ...context().replay, state: "running", cursor: revision },
  });
  const source = {
    datasets: vi.fn(async () => [dataset]), create: vi.fn(async () => ({ runId: "test-run", token: "test", context: running(1) })),
    advance: vi.fn().mockResolvedValueOnce(running(2)).mockResolvedValueOnce(running(3, [event({ status, attempts: 1 }), events[1]])),
    recommend: vi.fn(() => pending.promise),
  };
  const view = render(<DemoDashboard dataSource={source} />);
  await act(async () => {});
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Preparar replay" })); });
  expect(screen.getAllByText("Na fila")).toHaveLength(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(view.container.querySelector(".demo-twin-grid")).toHaveAttribute("data-revision", "2");
  expect(screen.getByText("Consultando manual")).toHaveAttribute("title", "Consulta enviada; aguardando resposta do serviço.");
  expect(screen.getAllByText("Na fila")).toHaveLength(1);
  expect(events[0].status).toBe("pending");
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(view.container.querySelector(".demo-twin-grid")).toHaveAttribute("data-revision", "3");
  expect(source.recommend).toHaveBeenCalledTimes(1); expect(source.advance).toHaveBeenCalledTimes(2);
  expect(screen.queryByText("Consultando manual")).not.toBeInTheDocument();
  expect(screen.getByText(status === "ready" ? "Recomendação disponível" : "Resposta limitada")).toBeVisible();
  await act(async () => { pending.resolve(event({ status: "processing" })); await pending.promise; });
  expect(screen.queryByText("Consultando manual")).not.toBeInTheDocument();
});

const attentionContext = (revision = 1, playback = "paused", extra = {}) => readyContext({
  revision, status: "watch",
  replay: { ...readyContext().replay, state: playback, cursor: revision },
  sensors: {
    ...context().sensors,
    s1: { ...context().sensors.s1, assessment: { assessment: { status: "watch" }, evidence: [] } },
  },
  ...extra,
});

it("offers contextual prompt chips that send once immediately and disable while a response is pending", async () => {
  const pending = deferred();
  const source = demoSource({
    create: vi.fn(async () => ({ runId: "test-run", token: "test", context: attentionContext() })),
    query: vi.fn(() => pending.promise),
  });
  await prepare(source);
  expect(screen.getByRole("heading", { name: "Motor (S1) exige atenção" })).toBeVisible();
  expect(source.query).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Analisar este instante" }));
  const chip = screen.getByRole("button", { name: "Por que o motor exige atenção?" });
  expect(chip).toBeEnabled();
  expect(source.query).not.toHaveBeenCalled();
  fireEvent.click(chip);
  fireEvent.click(chip);
  expect(source.query).toHaveBeenCalledTimes(1);
  expect(source.query.mock.calls[0][1]).toEqual({ question: demoSuggestions(attentionContext())[0].question, contextRevision: 1 });
  expect(screen.getByRole("textbox", { name: "Pergunta" })).toHaveValue(demoSuggestions(attentionContext())[0].question);
  expect(chip).toBeDisabled();
  expect(screen.getByRole("button", { name: "O que verificar no motor?" })).toBeDisabled();
  await act(async () => { pending.resolve({ contextRevision: 1, sourceRow: 141, observedAt: time, response: recommendation }); await pending.promise; });
  expect(chip).toBeEnabled();
  expect(source.control).not.toHaveBeenCalled();
});

it("waits for the in-flight advance and confirmed pause before opening analysis, then sends the confirmed revision", async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const advance = deferred(), pause = deferred();
  const source = demoSource({
    create: vi.fn(async () => ({ runId: "test-run", token: "test", context: attentionContext(1, "running") })),
    advance: vi.fn(() => advance.promise), control: vi.fn(() => pause.promise), query: vi.fn(() => new Promise(() => {})),
  });
  await act(async () => { render(<DemoDashboard dataSource={source} />); });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Preparar replay" })); });
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  const analyze = screen.getByRole("button", { name: "Pausar e analisar" });
  expect(analyze).toBeEnabled();
  fireEvent.click(analyze);
  fireEvent.click(analyze);
  expect(screen.getByRole("button", { name: "Copiloto" })).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("button", { name: "Aguardando pausa…" })).toBeDisabled();
  expect(source.control).not.toHaveBeenCalled();
  expect(source.query).not.toHaveBeenCalled();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(source.advance).toHaveBeenCalledTimes(1);
  await act(async () => { advance.resolve(attentionContext(2, "running")); await advance.promise; });
  expect(source.control).toHaveBeenCalledTimes(1);
  expect(source.control.mock.calls[0][1]).toMatchObject({ action: "pause", expectedRevision: 2 });
  expect(screen.getByRole("button", { name: "Copiloto" })).toHaveAttribute("aria-expanded", "false");
  await act(async () => { pause.resolve(attentionContext(3)); await pause.promise; });
  expect(screen.getByRole("button", { name: "Copiloto" })).toHaveAttribute("aria-expanded", "true");
  expect(source.query).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Por que o motor exige atenção?" }));
  expect(source.query).toHaveBeenCalledTimes(1);
  expect(source.query.mock.calls[0][1].contextRevision).toBe(3);
});

it("keeps analysis closed and makes no query when pause cannot be confirmed", async () => {
  const source = demoSource({
    create: vi.fn(async () => ({ runId: "test-run", token: "test", context: attentionContext(1, "running") })),
    control: vi.fn(async () => { throw new Error("Não foi possível confirmar a pausa."); }),
  });
  await prepare(source);
  fireEvent.click(screen.getByRole("button", { name: "Pausar e analisar" }));
  await screen.findByText("Não foi possível confirmar a pausa.");
  expect(screen.getByRole("button", { name: "Copiloto" })).toHaveAttribute("aria-expanded", "false");
  expect(source.query).not.toHaveBeenCalled();
});

it("does not open a prepared question from an obsolete generation after awaiting pause", async () => {
  const pause = deferred();
  const source = demoSource({
    create: vi.fn(async () => ({ runId: "test-run", token: "test", context: attentionContext(1, "running") })),
    control: vi.fn(() => pause.promise),
  });
  await prepare(source);
  fireEvent.click(screen.getByRole("button", { name: "Pausar e analisar" }));
  await act(async () => { pause.resolve(attentionContext(2, "paused", { replay: { ...readyContext().replay, generation: 1 } })); await pause.promise; });
  expect(screen.getByRole("button", { name: "Copiloto" })).toHaveAttribute("aria-expanded", "false");
  expect(source.query).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Copiloto" }));
  expect(screen.getByRole("textbox", { name: "Pergunta" })).toHaveValue("");
});

it("offers a review action and general suggestion even when no sensor requires attention", async () => {
  const source = demoSource();
  await prepare(source);
  expect(screen.queryByRole("region", { name: "Atenção no conjunto" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Analisar este instante" }));
  expect(screen.getByRole("button", { name: "Resumir este instante" })).toBeEnabled();
  expect(screen.getByRole("textbox", { name: "Pergunta" })).toHaveValue(demoSuggestions(readyContext())[0].question);
  expect(source.query).not.toHaveBeenCalled();
  expect(source.control).not.toHaveBeenCalled();
});

it("blocks manual queries and suggestion clicks while playback is running", async () => {
  const source = demoSource({ create: vi.fn(async () => ({ runId: "test-run", token: "test", context: attentionContext(1, "running") })) });
  await prepare(source);
  fireEvent.click(screen.getByRole("button", { name: "Copiloto" }));
  expect(screen.getByRole("button", { name: "Por que o motor exige atenção?" })).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "Pergunta" }), { target: { value: "Analise o motor" } });
  expect(screen.getByRole("button", { name: "Perguntar sobre este instante" })).toBeDisabled();
  fireEvent.submit(screen.getByRole("form", { name: "Perguntar ao copiloto da demonstração" }));
  expect(source.query).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Pausar para analisar" })).toBeEnabled();
});

it("keeps pump suggestions scoped to measured evidence and shows both sensors when each requires attention", async () => {
  const current = attentionContext();
  current.sensors.s2 = { ...current.sensors.s2, assessment: { assessment: { status: "alert" }, evidence: [] } };
  await prepare(demoSource({ create: vi.fn(async () => ({ runId: "test-run", token: "test", context: current })) }));
  expect(screen.getByRole("heading", { name: "Motor (S1) e Bomba (S2) exigem atenção" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Copiloto" }));
  expect(screen.getByRole("button", { name: "Entender a atenção da bomba" })).toBeEnabled();
  expect(demoSuggestions(current).find((suggestion) => suggestion.label.includes("bomba")).question).toContain("sem recomendar procedimentos da bomba");
});
