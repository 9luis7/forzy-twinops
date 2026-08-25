import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import contextFixture from "../../../contracts/timeline/v1/fixtures/context-historical-candidate.valid.json";
import AssessmentPanel from "./AssessmentPanel.jsx";

afterEach(cleanup);

const selectedAssessment = () => ({
  ...structuredClone(contextFixture.assessment),
  modelVersion: "1.0.1",
  anomalyScore: 74.5,
  deteriorationScore: 63,
});

describe("historical selected-point assessment", () => {
  it("renders only the assessment supplied by the committed context", () => {
    const assessment = selectedAssessment();
    const { container } = render(<AssessmentPanel assessment={assessment} historical />);
    const panel = screen.getByTestId("assessment-panel");

    expect(within(panel).getByText("Score de anomalia relativo").nextElementSibling)
      .toHaveTextContent("74,50");
    expect(within(panel).getByText("Score de deteriora\u00e7\u00e3o relativo").nextElementSibling)
      .toHaveTextContent("63,00");
    expect(container).not.toHaveTextContent("%");
  });

  it("shows the human-review candidate warning only for watch or alert", () => {
    const assessment = selectedAssessment();
    const { rerender } = render(<AssessmentPanel assessment={assessment} historical />);

    expect(screen.getByText(
      "Candidato n\u00e3o confirmado para revis\u00e3o humana. Este desvio n\u00e3o confirma falha, causa ou componente.",
    )).toBeInTheDocument();

    rerender(<AssessmentPanel assessment={{ ...assessment, status: "normal" }} historical />);
    expect(screen.queryByText(/Candidato n\u00e3o confirmado/i)).not.toBeInTheDocument();
  });

  it("states the bounded semantics, model training cutoff, labels, and validation gate", () => {
    render(<AssessmentPanel assessment={selectedAssessment()} historical />);

    expect(screen.getByText(
      "Score relativo ao baseline hist\u00f3rico (escala 0\u2013100). N\u00e3o \u00e9 probabilidade de falha, confian\u00e7a calibrada, RUL nem diagn\u00f3stico.",
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

  it("keeps null scores unavailable instead of filling them with zero", () => {
    const assessment = {
      ...selectedAssessment(),
      status: "insufficient_data",
      anomalyScore: null,
      deteriorationScore: null,
    };
    render(<AssessmentPanel assessment={assessment} historical />);

    expect(screen.getByText("Score de anomalia relativo").nextElementSibling)
      .toHaveTextContent("Indispon\u00edvel");
    expect(screen.getByText("Score de deteriora\u00e7\u00e3o relativo").nextElementSibling)
      .toHaveTextContent("Indispon\u00edvel");
  });
});
