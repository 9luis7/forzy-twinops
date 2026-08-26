import { describe, expect, it } from "vitest";
import overviewFixture from "../../../contracts/timeline/v1/fixtures/overview-unified.valid.json";
import gapContextFixture from "../../../contracts/timeline/v1/fixtures/context-historical-gap.valid.json";
import snapshotFixture from "../../../contracts/v2/fixtures/snapshot-received-now.valid.json";

describe("buildTimelineViewModel", () => {
  it("keeps coverage segments and gaps in proportional calendar coordinates", async () => {
    const { buildTimelineViewModel } = await import("./timelineViewModel.js");
    const model = buildTimelineViewModel(structuredClone(overviewFixture));

    expect(model.domain).toEqual([
      Date.parse(overviewFixture.effectiveRange.from),
      Date.parse(overviewFixture.effectiveRange.to),
    ]);
    expect(model.segments).toHaveLength(4);
    expect(model.gaps).toHaveLength(3);
    expect(model.segments[0].startPercent).toBe(0);
    expect(model.gaps[0].startPercent).toBeCloseTo((9_000 / 189_001) * 100, 5);
    expect(model.gaps[0].widthPercent).toBeCloseTo((51_000 / 189_001) * 100, 5);
    expect(model.series).toHaveLength(4);
    expect(model.series.every((series) => typeof series.segmentId === "string")).toBe(true);
    expect(model.series.at(-1)).toMatchObject({
      points: [],
      showSinglePointMarker: false,
    });
    expect(model.series[0].points[0]).toMatchObject({
      pointId: overviewFixture.series[0].points[0].pointId,
      eventAt: overviewFixture.series[0].points[0].eventAt,
      value: overviewFixture.series[0].points[0].value,
    });
    expect(model.series[0].points[0]).not.toHaveProperty("provenance");
    expect(model.series[0].points[0]).not.toHaveProperty("qualityFlags");
  });

  it("builds honest live display runs without joining different sensors or local days", async () => {
    const { buildTimelineViewModel } = await import("./timelineViewModel.js");
    const makeSeries = (
      index,
      sensorId,
      sourceKind,
      eventAt,
      value,
      aggregation = {
        method: "none",
        omittedPointCount: 0,
        originalPointCount: 1,
        requestedMaxPoints: 4000,
        returnedPointCount: 1,
      },
      metric = "vibrationVelocityRms",
    ) => ({
      aggregation,
      metric,
      points: [{
        eventAt,
        pointId: `00000000-0000-5000-8000-${String(index).padStart(12, "0")}`,
        value,
      }],
      segmentId: `00000000-0000-5000-8000-${String(index + 100).padStart(12, "0")}`,
      sensorId,
      sourceKind,
    });
    const overview = {
      aggregationSummary: {},
      availableRange: null,
      effectiveRange: {
        from: "2026-08-24T15:00:00.000Z",
        to: "2026-08-25T15:01:00.000Z",
      },
      gaps: [],
      requestedRange: null,
      segments: [],
      series: [
        makeSeries(1, "s1", "live_collection", "2026-08-24T15:00:00.000Z", 0.04),
        makeSeries(2, "s1", "live_collection", "2026-08-24T15:01:00.000Z", 0.05),
        makeSeries(3, "s1", "live_collection", "2026-08-25T02:59:00.000Z", 0.06),
        makeSeries(4, "s2", "live_collection", "2026-08-24T15:00:30.000Z", 0.07),
        makeSeries(5, "s2", "live_collection", "2026-08-24T15:01:30.000Z", 0.08),
        makeSeries(6, "s1", "live_collection", "2026-08-25T03:01:00.000Z", 0.09),
        makeSeries(7, "s1", "historical_archive", "2026-08-24T15:00:15.000Z", 1.5),
        makeSeries(8, "s1", "live_collection", "2026-08-24T15:02:00.000Z", 0.1, {
          method: "time_bucket_envelope_v1",
          omittedPointCount: 1,
          originalPointCount: 2,
          requestedMaxPoints: 40,
          returnedPointCount: 1,
        }),
        makeSeries(
          9,
          "s1",
          "live_collection",
          "2026-08-24T15:03:00.000Z",
          38.2,
          undefined,
          "temperature",
        ),
      ],
    };

    const model = buildTimelineViewModel(overview);
    const displayRuns = model.displaySeries.map((series) => ({
      pointIds: series.points.map((point) => point.pointId),
      sensorId: series.sensorId,
      sourceKind: series.sourceKind,
    }));

    expect(displayRuns).toEqual([
      {
        pointIds: [
          "00000000-0000-5000-8000-000000000001",
          "00000000-0000-5000-8000-000000000002",
          "00000000-0000-5000-8000-000000000003",
        ],
        sensorId: "s1",
        sourceKind: "live_collection",
      },
      {
        pointIds: ["00000000-0000-5000-8000-000000000007"],
        sensorId: "s1",
        sourceKind: "historical_archive",
      },
      {
        pointIds: [
          "00000000-0000-5000-8000-000000000004",
          "00000000-0000-5000-8000-000000000005",
        ],
        sensorId: "s2",
        sourceKind: "live_collection",
      },
      {
        pointIds: ["00000000-0000-5000-8000-000000000008"],
        sensorId: "s1",
        sourceKind: "live_collection",
      },
      {
        pointIds: ["00000000-0000-5000-8000-000000000009"],
        sensorId: "s1",
        sourceKind: "live_collection",
      },
      {
        pointIds: ["00000000-0000-5000-8000-000000000006"],
        sensorId: "s1",
        sourceKind: "live_collection",
      },
    ]);
    expect(model.displaySeries.flatMap((series) => series.points)).toHaveLength(9);
    expect(model.series).toHaveLength(9);
  });
});

describe("resolveOperationsDisplay", () => {
  it("keeps Agora until commit and clears every contextual value for a committed gap", async () => {
    const timelineViewModel = await import("./timelineViewModel.js");

    expect(timelineViewModel.resolveOperationsDisplay).toBeTypeOf("function");

    const waiting = timelineViewModel.resolveOperationsDisplay({
      snapshot: structuredClone(snapshotFixture),
      viewMode: "historical",
      historicalContext: null,
      displayContext: snapshotFixture,
    });
    expect(waiting.displayViewMode).toBe("now");
    expect(waiting.channels.every(Boolean)).toBe(true);

    const gapContext = structuredClone(gapContextFixture);
    const gap = timelineViewModel.resolveOperationsDisplay({
      snapshot: structuredClone(snapshotFixture),
      viewMode: "historical",
      historicalContext: gapContext,
      displayContext: gapContext,
    });
    expect(gap).toMatchObject({
      displayViewMode: "historical",
      assessment: null,
      operationalState: "historical_gap",
      committedHistoricalContext: gapContext,
    });
    expect(gap.channels).toEqual([null, null]);
  });
});
