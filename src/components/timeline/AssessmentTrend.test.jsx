import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import emptyFixture from "../../../contracts/timeline/v1/fixtures/assessment-overview-empty.valid.json";
import filteredEmptyFixture from "../../../contracts/timeline/v1/fixtures/assessment-overview-filter-empty.valid.json";
import materializedFixture from "../../../contracts/timeline/v1/fixtures/assessment-overview-materialized.valid.json";

afterEach(cleanup);

describe("AssessmentTrend", () => {
  it("states that an unmaterialized batch has no inferred or zero-filled score", async () => {
    const modulePath = "./AssessmentTrend.jsx";
    const { default: AssessmentTrend } = await import(/* @vite-ignore */ modulePath);
    render(<AssessmentTrend overview={structuredClone(emptyFixture)} />);

    expect(screen.getByText(
      "Avalia\u00e7\u00f5es causais ainda n\u00e3o foram materializadas para este lote. Nenhum score foi inferido nem preenchido com zero.",
    )).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /scores relativos/i })).not.toBeInTheDocument();
  });

  it("distinguishes an empty filter from an unmaterialized batch", async () => {
    const modulePath = "./AssessmentTrend.jsx";
    const { default: AssessmentTrend } = await import(/* @vite-ignore */ modulePath);
    render(<AssessmentTrend overview={structuredClone(filteredEmptyFixture)} />);

    expect(screen.getByText(
      "Nenhuma avalia\u00e7\u00e3o materializada corresponde ao intervalo ou filtro selecionado. Nenhum score foi preenchido com zero.",
    )).toBeInTheDocument();
    expect(screen.queryByText(/ainda n\u00e3o foram materializadas/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /scores relativos/i })).not.toBeInTheDocument();
  });

  it("summarizes persisted evidence without rendering a second score chart", async () => {
    const modulePath = "./AssessmentTrend.jsx";
    const { default: AssessmentTrend } = await import(/* @vite-ignore */ modulePath);
    render(<AssessmentTrend overview={structuredClone(materializedFixture)} />);

    const evidence = screen.getByTestId("assessment-trend");
    const summary = within(evidence).getByRole("list", { name: "Resumo da evidência persistida" });

    expect(within(evidence).queryByRole("img", { name: /scores relativos/i })).not.toBeInTheDocument();
    expect(within(summary).getByText("Avaliações")).toBeVisible();
    expect(within(summary).getByText("4 de 4")).toBeVisible();
    expect(within(summary).getByText("Episódios candidatos")).toBeVisible();
    expect(within(summary).getByText("2 não confirmados")).toBeVisible();
    expect(within(summary).getByText("revisão humana obrigatória")).toBeVisible();
    expect(within(summary).getByText("S1 e S2")).toBeVisible();
    expect(within(summary).getByText("2 janelas causais")).toBeVisible();
  });

  it("publishes bounded evidence without percent or positive claims", async () => {
    const modulePath = "./AssessmentTrend.jsx";
    const { default: AssessmentTrend } = await import(/* @vite-ignore */ modulePath);
    const { container } = render(
      <AssessmentTrend overview={structuredClone(materializedFixture)} />,
    );

    expect(screen.getByRole("heading", { name: "Resumo dos scores históricos" })).toBeVisible();
    expect(screen.queryByRole("img", { name: /scores relativos/i })).not.toBeInTheDocument();
    expect(container).not.toHaveTextContent("%");
    expect(container).not.toHaveTextContent("Probabilidade de falha confirmada");
    expect(container).not.toHaveTextContent("Confian\u00e7a calibrada confirmada");
    expect(container).not.toHaveTextContent("RUL estimado");
    expect(container).not.toHaveTextContent("Diagn\u00f3stico confirmado");
  });

  it("publishes the exact model limits and candidate warning", async () => {
    const modulePath = "./AssessmentTrend.jsx";
    const { default: AssessmentTrend } = await import(/* @vite-ignore */ modulePath);
    render(<AssessmentTrend overview={structuredClone(materializedFixture)} />);

    expect(screen.getByText(
      "Score relativo ao baseline hist\u00f3rico (escala 0\u2013100). N\u00e3o \u00e9 probabilidade de falha, confian\u00e7a calibrada, RUL nem diagn\u00f3stico.",
    )).toBeInTheDocument();
    expect(screen.getByText(
      "Candidato n\u00e3o confirmado para revis\u00e3o humana. Este desvio n\u00e3o confirma falha, causa ou componente.",
    )).toBeInTheDocument();
    expect(screen.getByText(/Modelo robust-baseline 1\.0\.1/)).toBeInTheDocument();
    expect(screen.getByText(
      "O conjunto de dados n\u00e3o cont\u00e9m r\u00f3tulos de falha confirmada.",
    )).toBeInTheDocument();
    expect(screen.getByText(
      "Valida\u00e7\u00e3o humana obrigat\u00f3ria antes de qualquer a\u00e7\u00e3o operacional.",
    )).toBeInTheDocument();
  });

  it("compacts repeated model provenance alongside the evidence summary", async () => {
    const modulePath = "./AssessmentTrend.jsx";
    const { default: AssessmentTrend } = await import(/* @vite-ignore */ modulePath);
    render(<AssessmentTrend overview={structuredClone(materializedFixture)} />);

    const models = screen.getByRole("list", { name: /modelos causais/i });
    expect(within(models).getAllByRole("listitem")).toHaveLength(1);
    expect(models).toHaveTextContent("2 janelas causais");
    expect(models).toHaveTextContent(
      "cortes de treinamento de 2026-08-22T11:30:00.000Z a 2026-08-22T12:30:00.000Z",
    );
    expect(models).toHaveTextContent(`sha256:${"d".repeat(64)}`);
    expect(within(screen.getByRole("list", { name: "Resumo da evidência persistida" }))
      .getAllByRole("listitem")).toHaveLength(4);
  });

  it("does not show a candidate warning when all points are normal or insufficient", async () => {
    const modulePath = "./AssessmentTrend.jsx";
    const { default: AssessmentTrend } = await import(/* @vite-ignore */ modulePath);
    const overview = structuredClone(materializedFixture);
    overview.series = [overview.series[0]];
    overview.series[0].points = [overview.series[0].points[0], overview.series[0].points[2]];
    overview.series[0].aggregation.originalAssessmentCount = 2;
    overview.series[0].aggregation.returnedAssessmentCount = 2;
    overview.materialization.assessmentCount = 2;
    overview.aggregationSummary.originalAssessmentCount = 2;
    overview.aggregationSummary.returnedAssessmentCount = 2;

    render(<AssessmentTrend overview={overview} />);

    expect(screen.queryByText(/Candidato n\u00e3o confirmado/i)).not.toBeInTheDocument();
  });
});
