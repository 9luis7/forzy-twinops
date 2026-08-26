import "@testing-library/jest-dom/vitest";
import React from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import overviewFixture from "../../../contracts/timeline/v1/fixtures/overview-unified.valid.json";
import pageFixture from "../../../contracts/timeline/v1/fixtures/page.valid.json";
import contextFixture from "../../../contracts/timeline/v1/fixtures/context-historical-candidate.valid.json";
import gapContextFixture from "../../../contracts/timeline/v1/fixtures/context-historical-gap.valid.json";
import assessmentOverviewFixture from "../../../contracts/timeline/v1/fixtures/assessment-overview-materialized.valid.json";
import AssessmentPanel from "../operations/AssessmentPanel.jsx";
import SensorCard from "../operations/SensorCard.jsx";
import HistoricalContextEvidence from "./HistoricalContextEvidence.jsx";

afterEach(cleanup);

describe("TimelineWorkspace", () => {
  it("removes redundant period filters when only live collection data exists", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");
    const liveOnlyOverview = structuredClone(overviewFixture);
    liveOnlyOverview.activeHistoricalBatchId = null;
    liveOnlyOverview.capabilities.historical = false;
    const onRangePresetChange = vi.fn();

    render(
      <TimelineWorkspace
        assessmentOverview={null}
        context={null}
        errors={{ overview: null, page: null, assessments: null, context: null }}
        loading={{ overview: false, page: false, assessments: false, context: false }}
        onRangePresetChange={onRangePresetChange}
        overview={liveOnlyOverview}
        page={structuredClone(pageFixture)}
        pendingSelection={null}
        rangePreset="24h"
        selectTimelinePoint={vi.fn()}
      />,
    );

    expect(screen.queryByRole("group", { name: "Período exibido" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "7 dias" })).not.toBeInTheDocument();
    expect(screen.getByText("Sem lote histórico ativo")).toBeInTheDocument();
    expect(screen.getByText("44 leituras ao vivo disponíveis")).toBeInTheDocument();
    expect(screen.getByText(/consulta carrega tudo o que foi publicado/i)).toBeInTheDocument();
    await waitFor(() => expect(onRangePresetChange).toHaveBeenCalledOnce());
    expect(onRangePresetChange).toHaveBeenCalledWith("all");
  });

  it("presents range controls and keeps technical evidence collapsed", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");
    const onRangePresetChange = vi.fn();

    render(
      <TimelineWorkspace
        assessmentOverview={structuredClone(assessmentOverviewFixture)}
        context={null}
        errors={{ overview: null, page: null, assessments: null, context: null }}
        loading={{ overview: false, page: false, assessments: false, context: false }}
        onRangePresetChange={onRangePresetChange}
        overview={structuredClone(overviewFixture)}
        page={structuredClone(pageFixture)}
        pendingSelection={null}
        rangePreset="7d"
        selectTimelinePoint={vi.fn()}
      >
        <section>Contexto técnico detalhado</section>
      </TimelineWorkspace>,
    );

    const rangeControls = screen.getByRole("group", { name: "Período exibido" });
    expect(within(rangeControls).getByRole("button", { name: "7 dias" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(within(rangeControls).getByRole("button", { name: "14 dias" }));
    expect(onRangePresetChange).toHaveBeenCalledWith("14d");

    const evidenceSummary = screen.getByText("Evidência técnica e leituras originais");
    expect(evidenceSummary.closest("details")).not.toHaveAttribute("open");
    expect(screen.getByRole("complementary", { name: "Ponto selecionado" })).toBeInTheDocument();
  });

  it("frames the complete published domain when Tudo is selected", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");
    const allRangeOverview = structuredClone(overviewFixture);
    const domainFrom = "2026-08-24T00:00:00.000Z";
    const domainTo = "2026-08-25T00:00:00.000Z";
    const clusteredTimes = [
      domainFrom,
      "2026-08-24T23:55:00.000Z",
      "2026-08-24T23:56:00.000Z",
      "2026-08-24T23:57:00.000Z",
      "2026-08-24T23:58:00.000Z",
      "2026-08-24T23:59:00.000Z",
    ];
    allRangeOverview.requestedRange = null;
    allRangeOverview.effectiveRange = { from: domainFrom, to: domainTo };
    allRangeOverview.availableRange = { from: domainFrom, to: domainTo };
    allRangeOverview.aggregationSummary = {
      originalPointCount: 6,
      returnedPointCount: 6,
      omittedPointCount: 0,
    };
    allRangeOverview.series = [{
      ...allRangeOverview.series[0],
      points: clusteredTimes.map((eventAt, index) => ({
        pointId: `00000000-0000-5000-8000-${String(index + 200).padStart(12, "0")}`,
        eventAt,
        value: 0.04 + index / 1000,
      })),
    }];

    render(
      <TimelineWorkspace
        assessmentOverview={null}
        context={null}
        errors={{ overview: null, page: null, assessments: null, context: null }}
        loading={{ overview: false, page: false, assessments: false, context: false }}
        onRangePresetChange={vi.fn()}
        overview={allRangeOverview}
        page={null}
        pendingSelection={null}
        rangePreset="all"
        selectTimelinePoint={vi.fn()}
      />,
    );

    const telemetry = screen.getByRole("img", { name: "Telemetria histórica sincronizada" });
    expect(Number(telemetry.dataset.domainFrom)).toBe(Date.parse(domainFrom));
    expect(Number(telemetry.dataset.domainTo)).toBe(Date.parse(domainTo));
    expect(screen.getByText("1× · 6/6 pontos visíveis")).toBeVisible();
    expect(screen.getByRole("button", { name: "Reenquadrar" })).toBeDisabled();
  });

  it("selects an original point directly from the synchronized chart", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");
    const selectTimelinePoint = vi.fn();
    const timelineOverview = structuredClone(overviewFixture);
    const pointId = timelineOverview.series[0].points[0].pointId;

    render(
      <TimelineWorkspace
        assessmentOverview={structuredClone(assessmentOverviewFixture)}
        context={null}
        errors={{ overview: null, page: null, assessments: null, context: null }}
        loading={{ overview: false, page: false, assessments: false, context: false }}
        onRangePresetChange={vi.fn()}
        overview={timelineOverview}
        page={structuredClone(pageFixture)}
        pendingSelection={null}
        rangePreset="7d"
        selectTimelinePoint={selectTimelinePoint}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: `Inspecionar ponto ${pointId}` }));
    expect(selectTimelinePoint).toHaveBeenCalledWith(pointId);
  });

  it("keeps selected sensor and model evidence in a persistent decision inspector", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");

    render(
      <TimelineWorkspace
        assessmentOverview={structuredClone(assessmentOverviewFixture)}
        context={structuredClone(contextFixture)}
        errors={{ overview: null, page: null, assessments: null, context: null }}
        loading={{ overview: false, page: false, assessments: false, context: false }}
        onRangePresetChange={vi.fn()}
        overview={structuredClone(overviewFixture)}
        page={structuredClone(pageFixture)}
        pendingSelection={null}
        rangePreset="7d"
        selectTimelinePoint={vi.fn()}
      />,
    );

    const inspector = screen.getByRole("complementary", { name: "Ponto selecionado" });
    expect(within(inspector).getByText("S1 · Velocidade RMS")).toBeInTheDocument();
    expect(within(inspector).getByText("S2 · Velocidade RMS")).toBeInTheDocument();
    expect(within(inspector).getByText("Score relativo ao baseline histórico")).toBeInTheDocument();
    expect(within(inspector).getByText("Não é probabilidade de falha")).toBeInTheDocument();
    expect(within(inspector).getByText("Candidato não confirmado")).toBeInTheDocument();
    expect(within(inspector).getByText("robust-baseline 1.0")).toBeInTheDocument();
  });

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
    const refreshedSamples = screen.getByRole("table", {
      name: "Pontos originais disponíveis para inspeção histórica",
    });
    expect(within(refreshedSamples).getAllByRole("button", {
      name: /inspecionar ponto/i,
    })).toHaveLength(2);
  });

  it("keeps the original action focused and inert while its context is pending", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");
    const timelinePage = {
      ...structuredClone(pageFixture),
      items: [
        structuredClone(contextFixture.channels.s1),
        structuredClone(contextFixture.channels.s2),
      ],
      limit: 200,
    };
    const selectTimelinePoint = vi.fn();
    const props = {
      context: null,
      errors: { overview: null, page: null, context: null },
      loading: { overview: false, page: false, context: false },
      overview: structuredClone(overviewFixture),
      page: timelinePage,
      selectTimelinePoint,
    };

    const { rerender } = render(
      <TimelineWorkspace {...props} pendingSelection={null} />,
    );
    const samplesTable = screen.getByRole("table", {
      name: "Pontos originais disponíveis para inspeção histórica",
    });
    const originalAction = within(samplesTable).getAllByRole("button", {
      name: /inspecionar ponto/i,
    })[0];
    originalAction.focus();
    fireEvent.click(originalAction);

    expect(selectTimelinePoint).toHaveBeenCalledTimes(1);
    expect(selectTimelinePoint).toHaveBeenCalledWith(timelinePage.items[0].pointId);

    rerender(
      <TimelineWorkspace
        {...props}
        pendingSelection={{ pointId: timelinePage.items[0].pointId }}
      />,
    );
    const pendingAction = within(samplesTable).getByRole("button", { name: /sincronizando/i });
    expect(pendingAction).not.toBeDisabled();
    expect(pendingAction).toHaveAttribute("aria-disabled", "true");
    expect(pendingAction).toHaveAttribute("aria-busy", "true");
    expect(pendingAction).toHaveFocus();

    fireEvent.click(pendingAction);
    expect(selectTimelinePoint).toHaveBeenCalledTimes(1);
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
      <TimelineWorkspace {...props} commitAnnouncement={null} context={null}>
        {contextualPanels}
      </TimelineWorkspace>,
    );

    expect(screen.queryByText(/Contexto histórico confirmado para/i)).not.toBeInTheDocument();
    const overview = screen.getByRole("img", { name: /cobertura temporal proporcional/i });
    const panels = screen.getByTestId("contextual-panels");
    const samples = screen.getByRole("table", {
      name: "Pontos originais disponíveis para inspeção histórica",
    });
    expect(within(samples).getAllByRole("button", { name: /inspecionar ponto/i })).toHaveLength(200);
    expect(overview.compareDocumentPosition(panels) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
    expect(panels.compareDocumentPosition(samples) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);

    const preservedControl = screen.getByRole("button", { name: "Controle contextual preservado" });
    preservedControl.focus();
    rerender(
      <TimelineWorkspace
        {...props}
        commitAnnouncement={"Contexto hist\u00f3rico confirmado para a evid\u00eancia selecionada."}
        context={structuredClone(contextFixture)}
      >
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

describe("historical assessment trend placement", () => {
  it("places persisted assessment evidence before the selected context without deriving a selection", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");
    const selectTimelinePoint = vi.fn();
    render(
      <TimelineWorkspace
        assessmentOverview={structuredClone(assessmentOverviewFixture)}
        context={structuredClone(contextFixture)}
        errors={{ overview: null, page: null, assessments: null, context: null }}
        loading={{ overview: false, page: false, assessments: false, context: false }}
        overview={structuredClone(overviewFixture)}
        page={structuredClone(pageFixture)}
        pendingSelection={null}
        selectTimelinePoint={selectTimelinePoint}
      >
        <section data-testid="selected-context">Contexto selecionado preservado</section>
      </TimelineWorkspace>,
    );

    const trend = screen.getByTestId("assessment-trend");
    const selected = screen.getByTestId("selected-context");
    expect(trend.compareDocumentPosition(selected) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
    expect(selectTimelinePoint).not.toHaveBeenCalled();
  });

  it("keeps the last valid trend visible during refresh failure", async () => {
    const { default: TimelineWorkspace } = await import("./TimelineWorkspace.jsx");
    render(
      <TimelineWorkspace
        assessmentOverview={structuredClone(assessmentOverviewFixture)}
        context={null}
        errors={{ overview: null, page: null, assessments: new Error("unavailable"), context: null }}
        loading={{ overview: false, page: false, assessments: false, context: false }}
        overview={structuredClone(overviewFixture)}
        page={null}
        pendingSelection={null}
        selectTimelinePoint={vi.fn()}
      />,
    );

    expect(screen.getByTestId("assessment-trend")).toBeInTheDocument();
    expect(screen.getByText(
      "As avalia\u00e7\u00f5es n\u00e3o puderam ser atualizadas. A \u00faltima s\u00e9rie v\u00e1lida continua vis\u00edvel.",
    )).toHaveAttribute("role", "alert");
  });
});
