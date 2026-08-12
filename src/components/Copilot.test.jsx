import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CopilotView } from "./Copilot.jsx";

afterEach(cleanup);

const assessment = {
  assessmentId: "assessment-1",
  assetTag: "MOTOR-01",
  quality: { status: "ok" },
  assessment: { status: "watch" },
  evidence: [{ id: "ev-1", feature: "velocity", value: 0.08, unit: "mm/s" }],
  limitations: ["Sem rótulos de falha."],
};

function snapshot(overrides = {}) {
  return {
    assetTag: "MOTOR-01",
    assessment,
    capabilities: { copilot: true },
    ...overrides,
  };
}

describe("CopilotView", () => {
  it("renders a provider response with evidence refs", async () => {
    const client = {
      explain: vi.fn().mockResolvedValue({
        answer: "A vibração mudou.",
        evidenceRefs: ["ev-1"],
        provider: "local",
        limitations: [],
        humanValidationRequired: true,
      }),
    };
    render(<CopilotView tag="MOTOR-01" snapshot={snapshot()} client={client} />);

    fireEvent.click(screen.getByText("O que mudou nesta avaliação?"));

    expect(await screen.findByText("A vibração mudou.")).toBeTruthy();
    expect(screen.getByText("ev-1")).toBeTruthy();
    expect(client.explain).toHaveBeenCalledTimes(1);
  });

  it("uses the evidence-bound fallback when the request fails", async () => {
    const client = { explain: vi.fn().mockRejectedValue(new Error("offline")) };
    render(<CopilotView tag="MOTOR-01" snapshot={snapshot()} client={client} />);

    fireEvent.click(screen.getByText("Qual ação é segura agora?"));

    expect(await screen.findByText(/Estado watch, qualidade ok/)).toBeTruthy();
    expect(screen.getByText("ev-1")).toBeTruthy();
  });

  it("resets conversation when the assessment changes", async () => {
    const client = {
      explain: vi.fn().mockResolvedValue({
        answer: "Resposta anterior",
        evidenceRefs: ["ev-1"],
        provider: "local",
        limitations: [],
        humanValidationRequired: true,
      }),
    };
    const view = render(<CopilotView tag="MOTOR-01" snapshot={snapshot()} client={client} />);
    fireEvent.click(screen.getByText("O que mudou nesta avaliação?"));
    expect(await screen.findByText("Resposta anterior")).toBeTruthy();

    view.rerender(
      <CopilotView
        tag="MOTOR-01"
        snapshot={snapshot({ assessment: { ...assessment, assessmentId: "assessment-2" } })}
        client={client}
      />
    );

    await waitFor(() => expect(screen.queryByText("Resposta anterior")).toBeNull());
  });

  it("never calls the backend when capability is disabled", async () => {
    const client = { explain: vi.fn() };
    render(
      <CopilotView
        tag="MOTOR-01"
        snapshot={snapshot({ capabilities: { copilot: false } })}
        client={client}
      />
    );

    fireEvent.click(screen.getByText("Quais evidências sustentam esse estado?"));

    expect(await screen.findByText(/Estado watch, qualidade ok/)).toBeTruthy();
    expect(client.explain).not.toHaveBeenCalled();
  });
});
