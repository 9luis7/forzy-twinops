import "@testing-library/jest-dom/vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import HistoricalWorkspace, { brasiliaInputToIso } from "./HistoricalWorkspace.jsx";
import { HistoryGatewayError } from "./GatewayHistoryDataSource.js";

const at = (row) => new Date(Date.UTC(2026, 7, 12, 15, 0, row)).toISOString();
const historyDataset = { datasetId: "history-real", label: "Histórico preservado", sourceFormat: "OOXML", pairCount: 4, readingCount: 8, startAt: at(1), endAt: at(4) };
function historicalContext(endRow = 4) {
  const history = [endRow - 1, endRow].flatMap((sourceRow) => ["s1", "s2"].map((sensorId) => ({
    frameId: `${sensorId}-${sourceRow}`, sensorId, sourceRow, observedAt: at(sourceRow), receivedAt: null, gapBefore: false, preloaded: false, qualityFlags: [],
    measurements: { vibrationVelocityRms: { value: sourceRow / 10, unit: "mm/s" }, temperature: { value: 32, unit: "degC" }, vibrationAcceleration: { value: 0, unit: "g" } },
  })));
  return {
    schemaVersion: "historical-1.0", mode: "historical", assetId: "forzy-motor-01", revision: `history-${endRow}`, dataset: historyDataset,
    selection: { from: null, to: null, endRow, limit: 300, observedAt: at(endRow), totalPairs: 4, returnedPairs: 2, hasPrevious: endRow > 2, previousEndRow: endRow > 2 ? 2 : null, hasNext: endRow < 4, nextEndRow: endRow < 4 ? 4 : null },
    sensors: Object.fromEntries(["s1", "s2"].map((id) => [id, { latest: history.findLast((frame) => frame.sensorId === id), assessment: null, assessmentState: "unavailable", newInformation: false }])),
    history, status: "insufficient_data", generatedAt: at(4), capabilities: { twin3d: true, copilot: false, replayControls: false },
  };
}

vi.mock("../demo/DemoTrends.jsx", () => ({
  METRICS: [{ key: "vibrationVelocityRms", label: "Velocidade RMS", unit: "mm/s" }],
  default: ({ context, selected }) => <div data-testid="history-trends" data-revision={context.revision} data-sensor={selected}>Gráficos históricos</div>,
}));
const FakeTwin = ({ snapshot, selectedSensor }) => <div data-testid="history-twin" data-mode={snapshot.mode} data-revision={snapshot.revision} data-sensor={selectedSensor}>Equipamento 3D</div>;
const deferred = () => { let resolve, reject; const promise = new Promise((res, rej) => { resolve = res; reject = rej; }); return { promise, resolve, reject }; };
const source = () => ({ datasets: vi.fn().mockResolvedValue([historyDataset]), context: vi.fn().mockResolvedValue(historicalContext()), create: vi.fn(), query: vi.fn(), advance: vi.fn() });
afterEach(cleanup);

it("opens the latest historical window with synchronized sensors and no replay or AI calls", async () => {
  const dataSource = source();
  render(<HistoricalWorkspace dataSource={dataSource} Twin3DComponent={FakeTwin} compact liveUnavailable />);
  await screen.findByTestId("history-twin");
  expect(dataSource.context).toHaveBeenCalledWith("history-real", { from: null, to: null, endRow: null, limit: 300 }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  expect(screen.getByText(/A coleta atual está indisponível/)).toBeVisible();
  expect(screen.getByText(/Análise retrospectiva · score relativo/)).toBeVisible();
  expect(screen.getByRole("link", { name: /Consultar histórico/ })).toHaveAttribute("href", "/history");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.queryByRole("form", { name: "Filtros do histórico" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /reproduzir|preparar replay|continuar/i })).not.toBeInTheDocument();
  expect(screen.getByTestId("history-twin")).toHaveAttribute("data-mode", "historical");
  expect(screen.getByTestId("history-trends")).toHaveAttribute("data-revision", "history-4");
  const instant = screen.getByText("12/08/2026, 12:00:04");
  expect(instant).toHaveAttribute("datetime", "2026-08-12T15:00:04.000Z");
  expect(instant.closest("h3")).toHaveTextContent("São Paulo");
  expect(dataSource.create).not.toHaveBeenCalled(); expect(dataSource.query).not.toHaveBeenCalled(); expect(dataSource.advance).not.toHaveBeenCalled();
});

it("navigates windows and keeps the current context until the next response arrives", async () => {
  const dataSource = source(), previous = deferred();
  dataSource.context.mockResolvedValueOnce(historicalContext()).mockReturnValueOnce(previous.promise);
  render(<HistoricalWorkspace dataSource={dataSource} Twin3DComponent={FakeTwin} />);
  await screen.findByTestId("history-twin");
  fireEvent.click(screen.getByRole("button", { name: "Anterior" }));
  expect(dataSource.context.mock.calls[1][1].endRow).toBe(2);
  expect(screen.getByTestId("history-twin")).toHaveAttribute("data-revision", "history-4");
  expect(screen.getByText(/A última seleção válida permanece abaixo/)).toBeVisible();
  await act(async () => previous.resolve(historicalContext(2)));
  expect(screen.getByTestId("history-twin")).toHaveAttribute("data-revision", "history-2");
  expect(screen.getByTestId("history-trends")).toHaveAttribute("data-revision", "history-2");
  expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Próximo" })).toBeEnabled();
});

it("applies explicit Brasilia filters atomically and ignores an older response", async () => {
  const dataSource = source(), first = deferred(), latest = deferred();
  dataSource.context.mockResolvedValueOnce(historicalContext()).mockReturnValueOnce(first.promise).mockReturnValueOnce(latest.promise);
  render(<HistoricalWorkspace dataSource={dataSource} Twin3DComponent={FakeTwin} />);
  await screen.findByTestId("history-twin");
  fireEvent.change(screen.getByLabelText("Início — São Paulo"), { target: { value: "2026-08-12T12:00:01" } });
  fireEvent.change(screen.getByLabelText("Sensor"), { target: { value: "s1" } });
  expect(screen.getByTestId("history-trends")).toHaveAttribute("data-sensor", "all");
  fireEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));
  expect(dataSource.context.mock.calls[1][1].from).toBe("2026-08-12T12:00:01-03:00");
  fireEvent.change(screen.getByLabelText("Sensor"), { target: { value: "s2" } });
  fireEvent.change(screen.getByLabelText("Fim — São Paulo"), { target: { value: "2026-08-12T12:00:02" } });
  fireEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));
  expect(dataSource.context.mock.calls[1][2].signal.aborted).toBe(true);
  await act(async () => latest.resolve(historicalContext(2)));
  expect(screen.getByTestId("history-twin")).toHaveAttribute("data-revision", "history-2");
  expect(screen.getByTestId("history-trends")).toHaveAttribute("data-sensor", "s2");
  await act(async () => first.resolve(historicalContext(4)));
  expect(screen.getByTestId("history-twin")).toHaveAttribute("data-revision", "history-2");
  expect(screen.getByTestId("history-trends")).toHaveAttribute("data-sensor", "s2");
  expect(dataSource.query).not.toHaveBeenCalled();
});

it("keeps an empty or failed filter distinct from the last valid selection", async () => {
  const dataSource = source();
  dataSource.context.mockResolvedValueOnce(historicalContext()).mockRejectedValueOnce(new HistoryGatewayError(400, "historical_selection_empty", "Nenhum registro encontrado para o período selecionado."));
  render(<HistoricalWorkspace dataSource={dataSource} Twin3DComponent={FakeTwin} />);
  await screen.findByTestId("history-twin");
  fireEvent.change(screen.getByLabelText("Início — São Paulo"), { target: { value: "2026-08-13T12:00:00" } });
  fireEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("o novo período não foi aplicado"));
  expect(screen.getByTestId("history-twin")).toHaveAttribute("data-revision", "history-4");
  expect(screen.getByText(/Período aplicado: Início do conjunto/)).toBeVisible();
});

it("states that the catalogue is empty without inventing data", async () => {
  const dataSource = source(); dataSource.datasets.mockResolvedValue([]);
  render(<HistoricalWorkspace dataSource={dataSource} Twin3DComponent={FakeTwin} />);
  expect(await screen.findByText("Nenhum conjunto histórico está disponível para consulta.")).toBeVisible();
  expect(dataSource.context).not.toHaveBeenCalled();
});

it("rejects nonexistent dates and converts inputs without using the computer timezone", () => {
  expect(brasiliaInputToIso("2026-08-12T12:00")).toBe("2026-08-12T12:00:00-03:00");
  expect(brasiliaInputToIso("")).toBeNull();
  expect(() => brasiliaInputToIso("2026-02-30T12:00")).toThrow(/válidas/);
});
