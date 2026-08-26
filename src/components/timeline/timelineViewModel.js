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

const liveDayFormatter = new Intl.DateTimeFormat("en-US", {
  day: "2-digit",
  month: "2-digit",
  timeZone: "America/Sao_Paulo",
  year: "numeric",
});

const localDayKey = (timeMs) => {
  const parts = Object.fromEntries(
    liveDayFormatter.formatToParts(new Date(timeMs)).map(({ type, value }) => [type, value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
};

const comparePoints = (left, right) => (
  left.timeMs - right.timeMs || left.pointId.localeCompare(right.pointId)
);

function buildDisplaySeries(series) {
  const passthrough = series
    .filter((item) => item.sourceKind !== "live_collection")
    .map((item) => ({
      ...item,
      displayKey: `source:${item.segmentId}:${item.sensorId}`,
    }));
  const livePoints = series
    .filter((item) => item.sourceKind === "live_collection")
    .flatMap((item) => item.points.map((point) => ({ item, point })))
    .sort((left, right) => comparePoints(left.point, right.point));
  const activeRuns = new Map();
  const liveRuns = [];

  for (const entry of livePoints) {
    const { item, point } = entry;
    const day = localDayKey(point.timeMs);
    const aggregationKey = `${item.aggregation.method}:${item.aggregation.requestedMaxPoints}`;
    const groupKey = [item.sensorId, item.metric, aggregationKey, day].join(":");
    const active = activeRuns.get(groupKey);
    if (active !== undefined) {
      active.points.push(point);
      continue;
    }

    const run = {
      ...item,
      displayKey: `live:${groupKey}:${point.pointId}`,
      points: [point],
      showSinglePointMarker: true,
    };
    activeRuns.set(groupKey, run);
    liveRuns.push(run);
  }

  return [...passthrough, ...liveRuns].sort((left, right) => {
    const leftPoint = left.points[0];
    const rightPoint = right.points[0];
    if (leftPoint === undefined) return rightPoint === undefined ? 0 : 1;
    if (rightPoint === undefined) return -1;
    return comparePoints(leftPoint, rightPoint)
      || left.sensorId.localeCompare(right.sensorId)
      || left.sourceKind.localeCompare(right.sourceKind);
  });
}

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
    displaySeries: [],
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

  const series = overview.series.map((item) => {
    const points = item.points.map((point) => {
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
      segmentId: item.segmentId,
      sensorId: item.sensorId,
      sourceKind: item.sourceKind,
      metric: item.metric,
      aggregation: item.aggregation,
      points,
      showSinglePointMarker: points.length === 1,
    };
  });

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
    series,
    displaySeries: buildDisplaySeries(series),
  };
}
