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
