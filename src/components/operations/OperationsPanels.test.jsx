import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, expect, it, vi } from "vitest";
import snapshotFixture from "../../../contracts/v2/fixtures/snapshot-received-now.valid.json";
import AssetHeader from "./AssetHeader.jsx";
import AssessmentPanel from "./AssessmentPanel.jsx";
import IntegrationHealth from "./IntegrationHealth.jsx";
import SensorCard from "./SensorCard.jsx";
import TelemetryTrend from "./TelemetryTrend.jsx";

const snapshot = structuredClone(snapshotFixture);

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
});

afterAll(() => vi.unstubAllGlobals());
afterEach(cleanup);

it("identifies the real assembly without inventing a tag", () => {
  render(
    <AssetHeader asset={snapshot.asset} operationalState={snapshot.operationalState} />
  );

  expect(screen.getByText("Conjunto motor-bomba monitorado")).toBeInTheDocument();
  expect(screen.getByText("TAG não fornecida")).toBeInTheDocument();
  expect(screen.queryByText(/MTR-BMB-042/)).not.toBeInTheDocument();
});

it("presents last-known state without calling it current", () => {
  render(<AssetHeader asset={snapshot.asset} operationalState="last_known" />);

  expect(screen.getByText("Último dado real conhecido")).toBeInTheDocument();
  expect(screen.queryByText(/tempo real/i)).not.toBeInTheDocument();
});

it("labels assumed retrieval time honestly", () => {
  render(<SensorCard channel={snapshot.channels[0]} />);

  expect(screen.getByText(/Capturado pelo TwinOps às/)).toBeInTheDocument();
  expect(screen.getByText(/Horário assumido a partir da captura/)).toBeInTheDocument();
});

it("distinguishes unavailable measurements from a valid zero", () => {
  const channel = structuredClone(snapshot.channels[0]);
  channel.measurements.vibrationVelocityRms = null;
  channel.measurements.temperature = null;

  render(<SensorCard channel={channel} />);

  expect(screen.getAllByText("Indisponível")).toHaveLength(2);
  expect(screen.getByText("0,00")).toBeInTheDocument();
});

it("renders separate sensor history and does not connect missing points", () => {
  const first = structuredClone(snapshot.channels[0]);
  const second = structuredClone(snapshot.channels[1]);
  second.receivedAt = "2026-08-12T15:00:06.000Z";
  second.observedAt = second.receivedAt;

  render(<TelemetryTrend history={[first, second]} />);

  const chart = screen.getByTestId("telemetry-trend");
  expect(within(chart).getByText("S1")).toBeInTheDocument();
  expect(within(chart).getByText("S2")).toBeInTheDocument();
  expect(chart.querySelectorAll('[data-connect-nulls="false"]')).toHaveLength(2);
});

it("states the ML limitation even when assessment is absent", () => {
  render(<AssessmentPanel assessment={null} />);

  expect(screen.getByText("Avaliação indisponível")).toBeInTheDocument();
  expect(
    screen.getByText("Desvio relativo ao histórico — não é probabilidade de falha")
  ).toBeInTheDocument();
});

it("renders contract assessment scores without turning them into percentages", () => {
  const assessment = {
    assessment: {
      status: "watch",
      anomalyScore: 0,
      deteriorationScore: 1.25,
      persistenceSeconds: 15,
    },
    quality: { status: "ok", flags: [] },
    evidence: [{ id: "ev-1", feature: "temperature", value: 34, unit: "degC" }],
    model: { name: "robust-baseline", version: "1.0.0" },
    limitations: ["Sem rótulos de falha"],
    humanValidationRequired: true,
  };

  render(<AssessmentPanel assessment={assessment} />);

  expect(screen.getByText("Atenção")).toBeInTheDocument();
  expect(screen.getByText("0,00")).toBeInTheDocument();
  expect(screen.queryByText(/%/)).not.toBeInTheDocument();
});

it("sanitizes integration errors instead of exposing arbitrary detail", () => {
  const integration = structuredClone(snapshot.integration);
  integration.sensors.s1.error = "postgres://user:secret@example.invalid";
  integration.sensors.s2.error = "invalid_payload";

  render(<IntegrationHealth integration={integration} />);

  expect(screen.getByText("Erro de integração")).toBeInTheDocument();
  expect(screen.getByText("Resposta inválida da origem")).toBeInTheDocument();
  expect(screen.queryByText(/secret/)).not.toBeInTheDocument();
});
