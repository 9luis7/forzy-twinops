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

  it("renders discontinuous bounded evidence without percent or positive claims", async () => {
    const modulePath = "./AssessmentTrend.jsx";
    const { default: AssessmentTrend } = await import(/* @vite-ignore */ modulePath);
    const { container } = render(
      <AssessmentTrend overview={structuredClone(materializedFixture)} />,
    );

    const chart = screen.getByRole("img", { name: /scores relativos.*0 a 100/i });
    expect(within(chart).getByText("100")).toBeInTheDocument();
    expect(within(chart).getByText("50")).toBeInTheDocument();
    expect(within(chart).getByText("0")).toBeInTheDocument();
    expect(chart.querySelectorAll('[data-score-kind="anomaly"]')).toHaveLength(2);
    expect(chart.querySelectorAll('[data-score-kind="deterioration"]')).toHaveLength(2);
    expect(container).not.toHaveTextContent("%");
    expect(container).not.toHaveTextContent("Probabilidade de falha confirmada");
    expect(container).not.toHaveTextContent("Confian\u00e7a calibrada confirmada");
    expect(container).not.toHaveTextContent("RUL estimado");
    expect(container).not.toHaveTextContent("Diagn\u00f3stico confirmado");
  });

  it("does not bridge either score trace across a multi-point insufficient-data run", async () => {
    const modulePath = "./AssessmentTrend.jsx";
    const { default: AssessmentTrend } = await import(/* @vite-ignore */ modulePath);
    const overview = structuredClone(materializedFixture);
    const scoredStart = structuredClone(overview.series[0].points[0]);
    const scoredBeforeGap = structuredClone(scoredStart);
    const nullStart = structuredClone(overview.series[0].points[2]);
    const nullEnd = structuredClone(nullStart);
    const scoredAfterGap = structuredClone(overview.series[0].points[1]);
    const scoredEnd = structuredClone(scoredAfterGap);
    Object.assign(scoredBeforeGap, {
      assessmentId: "00000000-0000-5000-8000-000000000024",
      anchorPointId: "00000000-0000-5000-8000-000000000044",
      eventAt: "2026-08-22T12:05:00.000Z",
    });
    Object.assign(nullStart, { eventAt: "2026-08-22T12:10:00.000Z" });
    Object.assign(nullEnd, {
      assessmentId: "00000000-0000-5000-8000-000000000025",
      anchorPointId: "00000000-0000-5000-8000-000000000045",
      eventAt: "2026-08-22T12:15:00.000Z",
    });
    Object.assign(scoredAfterGap, { eventAt: "2026-08-22T12:20:00.000Z" });
    Object.assign(scoredEnd, {
      assessmentId: "00000000-0000-5000-8000-000000000026",
      anchorPointId: "00000000-0000-5000-8000-000000000046",
      eventAt: "2026-08-22T12:25:00.000Z",
    });
    overview.series = [overview.series[0]];
    overview.series[0].points = [
      scoredStart,
      scoredBeforeGap,
      nullStart,
      nullEnd,
      scoredAfterGap,
      scoredEnd,
    ];
    overview.series[0].aggregation.originalAssessmentCount = 6;
    overview.series[0].aggregation.returnedAssessmentCount = 6;
    overview.materialization.assessmentCount = 6;
    overview.aggregationSummary.originalAssessmentCount = 6;
    overview.aggregationSummary.returnedAssessmentCount = 6;

    const { container } = render(<AssessmentTrend overview={overview} />);

    for (const kind of ["anomaly", "deterioration"]) {
      const trace = container.querySelector(`[data-score-kind="${kind}"]`);
      expect(trace.querySelectorAll("polyline")).toHaveLength(2);
      expect(trace.querySelectorAll("circle")).toHaveLength(0);
    }
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
    expect(screen.getByText(
      "Modelo robust-baseline 1.0.1 \u00b7 treinamento causal encerrado em 2026-08-22T11:30:00.000Z.",
    )).toBeInTheDocument();
    expect(screen.getByText(
      "O conjunto de dados n\u00e3o cont\u00e9m r\u00f3tulos de falha confirmada.",
    )).toBeInTheDocument();
    expect(screen.getByText(
      "Valida\u00e7\u00e3o humana obrigat\u00f3ria antes de qualquer a\u00e7\u00e3o operacional.",
    )).toBeInTheDocument();
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
