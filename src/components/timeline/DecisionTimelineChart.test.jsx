import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DecisionTimelineChart from "./DecisionTimelineChart.jsx";

afterEach(cleanup);

const HOUR = 60 * 60 * 1000;
const MINUTE = 60 * 1000;
const fullDomain = [
  Date.parse("2026-08-24T00:00:00.000Z"),
  Date.parse("2026-08-25T00:00:00.000Z"),
];

const point = (index, timeMs) => ({
  pointId: `00000000-0000-5000-8000-${String(index).padStart(12, "0")}`,
  eventAt: new Date(timeMs).toISOString(),
  timeMs,
  value: 0.04 + index / 1000,
});

const clusteredModel = {
  domain: fullDomain,
  gaps: [],
  series: [{
    segmentId: "segment-live",
    sensorId: "s1",
    points: [
      point(1, fullDomain[0]),
      point(2, fullDomain[1] - 5 * MINUTE),
      point(3, fullDomain[1] - 4 * MINUTE),
      point(4, fullDomain[1] - 3 * MINUTE),
      point(5, fullDomain[1] - 2 * MINUTE),
      point(6, fullDomain[1] - MINUTE),
    ],
  }],
};

describe("DecisionTimelineChart zoom viewport", () => {
  it("auto-frames dense readings and navigates directly by wheel, drag and reset", () => {
    render(
      <DecisionTimelineChart
        assessmentOverview={null}
        model={clusteredModel}
        onSelectPoint={vi.fn()}
        selectedAt={null}
        selectedPointId={null}
        visibleSensors={new Set(["s1", "s2"])}
      />,
    );

    const telemetry = screen.getByRole("img", { name: "Telemetria histórica sincronizada" });
    const autoFrom = Number(telemetry.dataset.domainFrom);
    const autoTo = Number(telemetry.dataset.domainTo);
    expect(autoFrom).toBeGreaterThan(fullDomain[0] + 20 * HOUR);
    expect(autoTo).toBe(fullDomain[1]);
    expect(screen.queryByRole("slider", { name: "Nível de zoom" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Período anterior" })).not.toBeInTheDocument();
    expect(screen.getByText(/Arraste para navegar · roda\/trackpad para zoom/i)).toBeVisible();

    const canvas = telemetry.closest(".decision-chart__canvas");
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({
      bottom: 310,
      height: 310,
      left: 0,
      right: 1000,
      top: 0,
      width: 1000,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    fireEvent.wheel(canvas, { clientX: 500, deltaY: -100 });
    const zoomedFrom = Number(telemetry.dataset.domainFrom);
    const zoomedTo = Number(telemetry.dataset.domainTo);
    expect(zoomedTo - zoomedFrom).toBeLessThan(autoTo - autoFrom);

    fireEvent(canvas, new MouseEvent("pointerdown", { bubbles: true, button: 0, clientX: 500 }));
    fireEvent(canvas, new MouseEvent("pointermove", { bubbles: true, clientX: 650 }));
    fireEvent(canvas, new MouseEvent("pointerup", { bubbles: true, clientX: 650 }));
    expect(Number(telemetry.dataset.domainFrom)).toBeLessThan(zoomedFrom);

    fireEvent.click(screen.getByRole("button", { name: "Reenquadrar" }));
    expect(Number(telemetry.dataset.domainFrom)).toBe(autoFrom);
    expect(Number(telemetry.dataset.domainTo)).toBe(autoTo);
  });
});
