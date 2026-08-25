import { PUBLIC_UTC_MILLIS_RE } from "../../contracts/timelineV1.js";

function canonicalUtcMillis(value, location) {
  if (typeof value !== "string" || !PUBLIC_UTC_MILLIS_RE.test(value)) {
    throw new TypeError(`${location} must be a canonical UTC millisecond`);
  }
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds) || new Date(milliseconds).toISOString() !== value) {
    throw new TypeError(`${location} must be a canonical UTC millisecond`);
  }
  return milliseconds;
}

const percentageWithin = (milliseconds, from, span) => (
  Math.min(100, Math.max(0, ((milliseconds - from) / span) * 100))
);

export function resolveOperationsDisplay({
  snapshot,
  viewMode,
  historicalContext,
  displayContext,
}) {
  const committedHistoricalContext = viewMode === "historical"
    && historicalContext !== null
    && displayContext === historicalContext
    ? historicalContext
    : null;

  if (committedHistoricalContext === null) {
    return {
      committedHistoricalContext: null,
      displayViewMode: "now",
      channels: ["s1", "s2"].map(
        (sensorId) => snapshot.channels.find((channel) => channel.sensorId === sensorId) ?? null,
      ),
      assessment: snapshot.assessment,
      operationalState: snapshot.operationalState,
    };
  }

  return {
    committedHistoricalContext,
    displayViewMode: "historical",
    channels: [
      committedHistoricalContext.channels.s1 ?? null,
      committedHistoricalContext.channels.s2 ?? null,
    ],
    assessment: committedHistoricalContext.assessment ?? null,
    operationalState: committedHistoricalContext.decisionFacts.collectionState,
  };
}

export function buildTimelineViewModel(overview) {
  const base = {
    requestedRange: overview.requestedRange,
    effectiveRange: overview.effectiveRange,
    availableRange: overview.availableRange,
    aggregationSummary: overview.aggregationSummary,
    domain: null,
    segments: [],
    gaps: [],
    series: [],
  };

  if (overview.effectiveRange === null) return base;

  const from = canonicalUtcMillis(overview.effectiveRange.from, "effectiveRange.from");
  const to = canonicalUtcMillis(overview.effectiveRange.to, "effectiveRange.to");
  const span = to - from;
  if (span <= 0) throw new TypeError("effectiveRange must be increasing");

  const interval = (startAt, endAt, location) => {
    const startMs = canonicalUtcMillis(startAt, `${location}.startAt`);
    const endMs = canonicalUtcMillis(endAt, `${location}.endAt`);
    return {
      startMs,
      endMs,
      startPercent: percentageWithin(startMs, from, span),
      widthPercent: percentageWithin(endMs, from, span) - percentageWithin(startMs, from, span),
    };
  };

  return {
    ...base,
    domain: [from, to],
    segments: overview.segments.map((segment) => ({
      ...segment,
      ...interval(segment.startAt, segment.endAt, `segment:${segment.segmentId}`),
    })),
    gaps: overview.gaps.map((gap) => ({
      ...gap,
      ...interval(gap.startAt, gap.endAt, `gap:${gap.gapId}`),
    })),
    series: overview.series.map((series) => {
      const points = series.points.map((point) => {
        const timeMs = canonicalUtcMillis(point.eventAt, `point:${point.pointId}.eventAt`);
        return {
          pointId: point.pointId,
          eventAt: point.eventAt,
          value: point.value,
          timeMs,
          xPercent: percentageWithin(timeMs, from, span),
        };
      });
      return {
        segmentId: series.segmentId,
        sensorId: series.sensorId,
        sourceKind: series.sourceKind,
        metric: series.metric,
        aggregation: series.aggregation,
        points,
        showSinglePointMarker: points.length === 1,
      };
    }),
  };
}
