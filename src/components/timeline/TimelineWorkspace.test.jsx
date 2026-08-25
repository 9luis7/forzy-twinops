import "@testing-library/jest-dom/vitest";
import React from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
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

  it("places committed context before a 200-point page and announces only the commit", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");
    const basePoints = [contextFixture.channels.s1, contextFixture.channels.s2];
    const timelinePage = {
      ...structuredClone(pageFixture),
      items: Array.from({ length: 200 }, (_, index) => ({
        ...structuredClone(basePoints[index % basePoints.length]),
        pointId: `original-point-${index.toString().padStart(3, "0")}`,
      })),
      limit: 200,
    };
    const props = {
      errors: { overview: null, page: null, context: null },
      loading: { overview: false, page: false, context: false },
      overview: structuredClone(overviewFixture),
      page: timelinePage,
      pendingSelection: null,
      selectTimelinePoint: vi.fn(),
    };
    const contextualPanels = (
      <section aria-label="Painéis do contexto exibido" data-testid="contextual-panels">
        <button type="button">Controle contextual preservado</button>
      </section>
    );

    const { rerender } = render(
      <TimelineWorkspace {...props} context={null}>
        {contextualPanels}
      </TimelineWorkspace>,
    );

    expect(screen.queryByText(/Contexto histórico confirmado para/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /inspecionar ponto/i })).toHaveLength(200);
    const overview = screen.getByRole("img", { name: /cobertura temporal proporcional/i });
    const panels = screen.getByTestId("contextual-panels");
    const samples = screen.getByRole("table", {
      name: "Pontos originais disponíveis para inspeção histórica",
    });
    expect(overview.compareDocumentPosition(panels) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
    expect(panels.compareDocumentPosition(samples) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);

    const preservedControl = screen.getByRole("button", { name: "Controle contextual preservado" });
    preservedControl.focus();
    rerender(
      <TimelineWorkspace {...props} context={structuredClone(contextFixture)}>
        {contextualPanels}
      </TimelineWorkspace>,
    );

    expect(screen.getByText(/Contexto histórico confirmado para/i)).toHaveAttribute(
      "role",
      "status",
    );
    expect(preservedControl).toHaveFocus();
  });

  it("keeps the 200-point mobile list bounded and scrollable", () => {
    const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");
    const mobileStyles = styles
      .split("@media (max-width: 700px)")[1]
      ?.split("@media (max-width: 600px)")[0] ?? "";
    const scrollRule = mobileStyles.match(/\.timeline-table-scroll\s*\{([^}]*)\}/)?.[1] ?? "";

    expect(scrollRule).not.toBe("");
    expect(scrollRule).not.toMatch(/max-height\s*:\s*none/i);
    expect(scrollRule).toMatch(/max-height\s*:\s*(?!none)[^;]+;/i);
    expect(scrollRule).toMatch(/overflow-y\s*:\s*auto/i);
  });

  it("describes every coverage segment outside hover-only titles", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");
    render(
      <TimelineWorkspace
        context={null}
        errors={{ overview: null, page: null, context: null }}
        loading={{ overview: false, page: false, context: false }}
        overview={structuredClone(overviewFixture)}
        page={null}
        pendingSelection={null}
        selectTimelinePoint={vi.fn()}
      />,
    );

    const rail = screen.getByRole("img", { name: /cobertura temporal proporcional/i });
    const descriptionIds = rail.getAttribute("aria-describedby")?.split(/\s+/) ?? [];
    expect(descriptionIds).toHaveLength(overviewFixture.segments.length);
    const segmentRegister = screen.getByRole("list", {
      name: "Trechos com cobertura na linha temporal",
    });
    expect(segmentRegister).not.toHaveClass("visually-hidden");

    const items = within(segmentRegister).getAllByRole("listitem");
    expect(items).toHaveLength(overviewFixture.segments.length);
    overviewFixture.segments.forEach((segment, index) => {
      expect(document.getElementById(descriptionIds[index])).toBe(items[index]);
      expect(items[index]).toHaveTextContent("Arquivo hist\u00f3rico");
      expect(items[index]).toHaveTextContent(`${segment.totalPoints} pontos originais`);
      const times = items[index].querySelectorAll("time");
      expect(times).toHaveLength(2);
      expect(times[0]).toHaveAttribute("dateTime", segment.startAt);
      expect(times[1]).toHaveAttribute("dateTime", segment.endAt);
    });
    expect(rail).toHaveAccessibleDescription(/Arquivo hist\u00f3rico/i);
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
