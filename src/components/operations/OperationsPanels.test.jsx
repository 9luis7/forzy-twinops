import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
    constructor(callback) {
      this.callback = callback;
    }
    observe(target) {
      this.callback([{ target, contentRect: { width: 640, height: 180 } }]);
    }
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

it("exposes the Agora and Histórico switch as one keyboard-focusable radio group", () => {
  const onShowHistory = vi.fn();
  const onShowNow = vi.fn();
  const { rerender } = render(
    <AssetHeader
      asset={snapshot.asset}
      onShowHistory={onShowHistory}
      onShowNow={onShowNow}
      operationalState={snapshot.operationalState}
      viewMode="now"
    />,
  );

  expect(screen.getByRole("group", { name: "Contexto temporal" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Agora" })).toBeChecked();
  const history = screen.getByRole("radio", { name: "Histórico" });
  history.focus();
  expect(history).toHaveFocus();
  fireEvent.click(history);
  expect(onShowHistory).toHaveBeenCalledTimes(1);

  rerender(
    <AssetHeader
      asset={snapshot.asset}
      onShowHistory={onShowHistory}
      onShowNow={onShowNow}
      operationalState="historical_context"
      viewMode="historical"
    />,
  );
  expect(screen.getByRole("radio", { name: "Histórico" })).toBeChecked();
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

it("draws independent interleaved sensor series while preserving a real null gap", () => {
  const frame = (sensorId, timestamp, value) => {
    const channel = structuredClone(
      snapshot.channels.find((candidate) => candidate.sensorId === sensorId)
    );
    channel.receivedAt = timestamp;
    channel.observedAt = timestamp;
    channel.measurements.vibrationVelocityRms = value === null
      ? null
      : { ...channel.measurements.vibrationVelocityRms, value };
    return channel;
  };
  const history = [
    frame("s1", "2026-08-12T15:00:00.000Z", 1),
    frame("s2", "2026-08-12T15:00:01.000Z", 10),
    frame("s1", "2026-08-12T15:00:02.000Z", null),
    frame("s2", "2026-08-12T15:00:03.000Z", 11),
    frame("s1", "2026-08-12T15:00:04.000Z", 2),
    frame("s2", "2026-08-12T15:00:05.000Z", 12),
    frame("s1", "2026-08-12T15:00:06.000Z", 3),
  ];

  render(<TelemetryTrend history={history} />);

  const s1 = screen.getByTestId("trend-series-s1");
  const s2 = screen.getByTestId("trend-series-s2");
  expect([...within(s1).getAllByRole("listitem")].map((item) => item.dataset.value)).toEqual([
    "1", "unavailable", "2", "3",
  ]);
  expect([...within(s2).getAllByRole("listitem")].map((item) => item.dataset.value)).toEqual([
    "10", "11", "12",
  ]);
  expect(s1.querySelector(".recharts-line-curve")?.getAttribute("d")).toMatch(/L/);
  expect(s2.querySelector(".recharts-line-curve")?.getAttribute("d")).toMatch(/L/);
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

it("does not turn nullable historical scores into zero", () => {
  const assessment = {
    schemaVersion: "1.0",
    status: "insufficient_data",
    anomalyScore: null,
    deteriorationScore: null,
    persistence: { persistenceSeconds: 0 },
    evidence: [],
    modelFamily: "robust-baseline",
    modelVersion: "1.0",
  };

  render(<AssessmentPanel assessment={assessment} historical />);

  expect(screen.getByText("Score de anomalia relativo").nextElementSibling).toHaveTextContent(
    "Indisponível",
  );
  expect(screen.getByText("Score de deterioração relativo").nextElementSibling).toHaveTextContent(
    "Indisponível",
  );
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
