import "@testing-library/jest-dom/vitest";
import React, { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import HistoricalCopilot from "./HistoricalCopilot.jsx";
import { assistantScope, historicalAnswer } from "./testFixtures.js";

afterEach(cleanup);
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
function Harness({ context = assistantScope(), dataSource }) {
  const [open, setOpen] = useState(false);
  return <HistoricalCopilot context={context} dataSource={dataSource} open={open} onOpenChange={setOpen} />;
}
const ask = (question) => {
  fireEvent.change(screen.getByRole("textbox", { name: "Pergunta técnica" }), { target: { value: question } });
  fireEvent.submit(screen.getByRole("form", { name: "Consultar o assistente técnico" }));
};

it("keeps the draft and pending consultation on close, without hidden autofocus or current-time claims", async () => {
  const pending = deferred(), context = assistantScope(), dataSource = { query: vi.fn().mockReturnValue(pending.promise) };
  render(<Harness context={context} dataSource={dataSource} />);
  expect(dataSource.query).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Copiloto" }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Como avaliar este motor?" } });
  fireEvent.click(screen.getByRole("button", { name: "Fechar copiloto" }));
  fireEvent.click(screen.getByRole("button", { name: "Copiloto" }));
  expect(screen.getByRole("textbox")).toHaveValue("Como avaliar este motor?");
  fireEvent.submit(screen.getByRole("form", { name: "Consultar o assistente técnico" }));
  expect(dataSource.query).toHaveBeenCalledWith("history-test", expect.objectContaining({ question: "Como avaliar este motor?", contextRevision: context.revision, selection: { from: null, to: null, endRow: 4, limit: 300 }, history: [] }), expect.any(Object));
  const signal = dataSource.query.mock.calls[0][2].signal;
  fireEvent.click(screen.getByRole("button", { name: "Fechar copiloto" }));
  expect(signal.aborted).toBe(false);
  await act(async () => pending.resolve(historicalAnswer(context)));
  expect(screen.getByRole("button", { name: "Copiloto" })).toHaveFocus();
  fireEvent.click(screen.getByRole("button", { name: "Copiloto" }));
  expect(screen.getByRole("heading", { name: "Estado no instante histórico" })).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Estado atual" })).not.toBeInTheDocument();
  expect(screen.queryByText(/Frescor|Recebido em/)).not.toBeInTheDocument();
  expect(screen.getByText("Registro histórico 4: atenção relativa no motor.")).toBeVisible();
  expect(dataSource.query).toHaveBeenCalledTimes(1);
});

it("aborts a previous revision, clears its conversation and rejects non-cooperative old answers", async () => {
  const previous = deferred(), oldScope = assistantScope(), nextScope = assistantScope(8);
  const dataSource = { query: vi.fn().mockReturnValueOnce(previous.promise).mockResolvedValueOnce(historicalAnswer(nextScope)) };
  const view = render(<Harness context={oldScope} dataSource={dataSource} />);
  fireEvent.click(screen.getByRole("button", { name: "Copiloto" })); ask("Pergunta antiga");
  const oldSignal = dataSource.query.mock.calls[0][2].signal;
  view.rerender(<Harness context={nextScope} dataSource={dataSource} />);
  expect(oldSignal.aborted).toBe(true);
  expect(screen.getByText(/A conversa anterior foi encerrada/)).toBeVisible();
  expect(screen.getByRole("textbox")).toHaveValue("");
  await act(async () => previous.resolve(historicalAnswer(oldScope)));
  expect(screen.queryByText("Registro histórico 4: atenção relativa no motor.")).not.toBeInTheDocument();
  ask("Pergunta do novo instante");
  await screen.findByText("Registro histórico 8: atenção relativa no motor.");
  expect(dataSource.query.mock.calls[1][1]).toMatchObject({ contextRevision: nextScope.revision, history: [] });
  expect(dataSource.query.mock.calls[1][1]).not.toHaveProperty("conversationId");
});

it("keeps a conversation when the same revision is refreshed", async () => {
  const context = assistantScope(), dataSource = { query: vi.fn().mockResolvedValue(historicalAnswer(context)) };
  const view = render(<Harness context={context} dataSource={dataSource} />);
  fireEvent.click(screen.getByRole("button", { name: "Copiloto" })); ask("Primeira pergunta");
  await screen.findByText("Registro histórico 4: atenção relativa no motor.");
  view.rerender(<Harness context={structuredClone(context)} dataSource={dataSource} />);
  expect(screen.getByText("Registro histórico 4: atenção relativa no motor.")).toBeVisible();
  ask("Segunda pergunta");
  await waitFor(() => expect(dataSource.query).toHaveBeenCalledTimes(2));
  expect(dataSource.query.mock.calls[1][1].history[0].answer).toContain("Estado no instante histórico:");
  expect(dataSource.query.mock.calls[1][1].history[0].answer).not.toContain("Estado atual:");
});

it("explains manual unavailability without a dead query control", () => {
  const context = assistantScope(); context.capabilities.copilot = false;
  const dataSource = { query: vi.fn() };
  render(<Harness context={context} dataSource={dataSource} />);
  fireEvent.click(screen.getByRole("button", { name: "Copiloto" }));
  expect(screen.getByText(/manual do equipamento ou o serviço de consulta está indisponível/i)).toBeVisible();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(dataSource.query).not.toHaveBeenCalled();
});
