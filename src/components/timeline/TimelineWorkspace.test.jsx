import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import overviewFixture from "../../../contracts/timeline/v1/fixtures/overview-unified.valid.json";
import pageFixture from "../../../contracts/timeline/v1/fixtures/page.valid.json";
import contextFixture from "../../../contracts/timeline/v1/fixtures/context-historical-candidate.valid.json";
import gapContextFixture from "../../../contracts/timeline/v1/fixtures/context-historical-gap.valid.json";
import AssessmentPanel from "../operations/AssessmentPanel.jsx";
import SensorCard from "../operations/SensorCard.jsx";
import HistoricalContextEvidence from "./HistoricalContextEvidence.jsx";

afterEach(cleanup);

describe("TimelineWorkspace", () => {
  it("renders broken evidence coverage and selects only an original point", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");
    const timelinePage = {
      ...structuredClone(pageFixture),
      activeHistoricalBatchId: contextFixture.provenance.activeHistoricalBatchId,
      items: [
        structuredClone(contextFixture.channels.s1),
        structuredClone(contextFixture.channels.s2),
      ],
      limit: 200,
    };
    const selectTimelinePoint = vi.fn();
    const timelineOverview = structuredClone(overviewFixture);

    const { rerender } = render(
      <TimelineWorkspace
        context={null}
        errors={{ overview: null, page: null, context: null }}
        loading={{ overview: false, page: false, context: false }}
        overview={timelineOverview}
        page={timelinePage}
        pendingSelection={null}
        selectTimelinePoint={selectTimelinePoint}
      />,
    );

    const overview = screen.getByRole("img", { name: /cobertura temporal proporcional/i });
    expect(within(overview).getAllByTestId("timeline-segment")).toHaveLength(4);
    expect(within(overview).getAllByTestId("timeline-gap")).toHaveLength(3);
    expect(within(overview).queryByRole("button")).not.toBeInTheDocument();
    expect(within(screen.getByRole("list", {
      name: "Lacunas sem cobertura na linha temporal",
    })).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByRole("group", { name: "Séries reduzidas por canal" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Legenda da linha de evidência" })).toBeInTheDocument();
    expect(screen.getByRole("table", {
      name: "Pontos originais disponíveis para inspeção histórica",
    })).toBeInTheDocument();

    const s2Row = screen.getByRole("row", { name: /S2/i });
    fireEvent.click(within(s2Row).getByRole("button", { name: /inspecionar ponto/i }));
    expect(selectTimelinePoint).toHaveBeenCalledTimes(1);
    expect(selectTimelinePoint).toHaveBeenCalledWith(contextFixture.channels.s2.pointId);

    rerender(
      <TimelineWorkspace
        context={null}
        errors={{ overview: null, page: null, context: null }}
        loading={{ overview: true, page: true, context: false }}
        overview={timelineOverview}
        page={timelinePage}
        pendingSelection={null}
        selectTimelinePoint={selectTimelinePoint}
      />,
    );
    expect(screen.getByText(
      "Atualizando a cobertura; a última linha válida continua visível.",
    )).toBeInTheDocument();
    expect(screen.getByText(
      "Atualizando os pontos; a última lista válida continua visível.",
    )).toBeInTheDocument();
    expect(screen.getAllByTestId("timeline-segment")).toHaveLength(4);
    expect(screen.getAllByRole("button", { name: /inspecionar ponto/i })).toHaveLength(2);
  });
});

describe("historical gap presentation", () => {
  it("clears channels and assessment without inferring the asset state", () => {
    const context = structuredClone(gapContextFixture);

    render(
      <>
        <HistoricalContextEvidence context={context} />
        <SensorCard channel={context.channels.s1} historical sensorId="s1" />
        <SensorCard channel={context.channels.s2} historical sensorId="s2" />
        <AssessmentPanel assessment={context.assessment} historical />
      </>,
    );

    const evidence = screen.getByTestId("historical-context-evidence");
    expect(evidence).toHaveAttribute("data-context-kind", "gap");
    expect(within(evidence).getByText(
      /não implica que o ativo estava parado, normal ou sem anomalias/i,
    )).toBeInTheDocument();
    expect(within(evidence).getByText("Política de coleta").nextElementSibling).toHaveTextContent(
      "Indisponível",
    );
    expect(within(evidence).getByText("Disponibilidade dos dados").nextElementSibling).toHaveTextContent(
      "Sem cobertura no intervalo",
    );
    expect(within(screen.getByTestId("sensor-card-s1")).getAllByText("Indisponível")).toHaveLength(3);
    expect(within(screen.getByTestId("sensor-card-s2")).getAllByText("Indisponível")).toHaveLength(3);

    const assessment = screen.getByTestId("assessment-panel");
    expect(within(assessment).getByText(
      "Avaliação causal indisponível para este ponto",
    )).toBeInTheDocument();
    expect(assessment).not.toHaveTextContent(
      /score|diagnóstico|probabilidade|RUL|causa\b|checklist|recomendação/i,
    );
  });
});
