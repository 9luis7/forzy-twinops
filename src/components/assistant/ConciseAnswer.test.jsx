import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import ConciseAnswer, { responseOrigin } from "./ConciseAnswer.jsx";

afterEach(cleanup);
const response = () => ({
  answer: { currentState: "S2 tem score 99, com desvio sustentado em relação ao baseline.", manual: "Não há procedimento documental aplicável à bomba." },
  citations: [], limitations: ["Hipótese, sem diagnóstico confirmado."], fallbackUsed: false,
  groundingStatus: "manual_insufficient", traceId: "trace-test",
  models: { generation: "configured-model" },
});

it("does not infer a generated answer from citations or a configured model", () => {
  const value = response();
  value.citations = [{ type: "manual" }];
  expect(responseOrigin(value)).toBe("Resposta anterior · geração não confirmada");
  value.generation = { status: "not_called", model: null, invocationId: null, latencyMs: null, toolCalls: 0 };
  expect(responseOrigin(value)).toBe("Resumo automático · sem consulta à IA");
});

it("shows confirmed operational generation without requiring manual citations", () => {
  const value = response();
  value.generation = { status: "generated", model: "gemini-test", invocationId: "invocation-test", latencyMs: 243, toolCalls: 1 };
  render(<ConciseAnswer response={value} />);
  expect(screen.getByText("Análise da IA · contexto operacional")).toBeVisible();
  expect(screen.getByText(value.answer.currentState)).toBeVisible();
  expect(screen.getByText(/Modelo utilizado: gemini-test/)).not.toBeVisible();
  fireEvent.click(screen.getByText("Detalhes técnicos da resposta"));
  expect(screen.getByText(/Modelo utilizado: gemini-test · geração em 243 ms/)).toBeVisible();
});

it("clearly identifies a fallback without presenting it as AI generation", () => {
  const value = response(); value.fallbackUsed = true;
  value.generation = { status: "fallback", model: "gemini-test", invocationId: "failed-attempt", latencyMs: 1000, toolCalls: 0 };
  render(<ConciseAnswer response={value} />);
  expect(screen.getByText("Resumo automático · IA indisponível")).toBeVisible();
  expect(screen.queryByText(/Análise da IA/)).not.toBeInTheDocument();
});
