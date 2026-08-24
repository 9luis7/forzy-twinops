import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import Ajv from "ajv";
import addFormats from "ajv-formats";

export const TIMELINE_SCHEMA_VERSION_V1 = "1.0";
export const PUBLIC_UTC_MILLIS_RE = /^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d\.\d{3}Z$/;

const TIMELINE_SCHEMA_PREFIX = "forzy://contracts/timeline/v1/";
const schemaNames = [
  "historical-sensor-reading",
  "timeline-point",
  "historical-assessment",
  "collection-policy",
  "timeline-event-candidate",
  "timeline-overview",
  "timeline-page",
  "timeline-decision-facts",
  "timeline-context",
];
const json = (url) => JSON.parse(readFileSync(url, "utf8"));
const defaultTimelineSchemas = schemaNames.map((name) => json(
  new URL(`../../contracts/timeline/v1/${name}.schema.json`, import.meta.url),
));
const defaultAssetAssessmentSchema = json(
  new URL("../../contracts/v2/asset-condition-assessment.schema.json", import.meta.url),
);

const fail = (message) => { throw new TypeError(message); };

const externalReferences = (value, output = new Set()) => {
  if (Array.isArray(value)) {
    value.forEach((child) => externalReferences(child, output));
  } else if (value && typeof value === "object") {
    Object.entries(value).forEach(([key, child]) => {
      if (key === "$ref" && typeof child === "string" && !child.startsWith("#")) {
        output.add(child.split("#", 1)[0]);
      } else {
        externalReferences(child, output);
      }
    });
  }
  return output;
};

export function createTimelineAjvV1({
  timelineSchemas = defaultTimelineSchemas,
  assetAssessmentSchema = defaultAssetAssessmentSchema,
} = {}) {
  if (!Array.isArray(timelineSchemas) || !assetAssessmentSchema || typeof assetAssessmentSchema !== "object") {
    fail("timeline_invalid_schema_catalog");
  }
  const documents = [...timelineSchemas, assetAssessmentSchema];
  const ids = documents.map((schema) => schema?.$id);
  if (ids.some((id) => typeof id !== "string" || !/^[a-z][a-z0-9+.-]*:\/\/[^#]+$/i.test(id))) {
    fail("timeline_schema_id_must_be_absolute");
  }
  if (new Set(ids).size !== ids.length) fail("timeline_duplicate_schema_id");
  const knownIds = new Set(ids);
  for (const document of documents) {
    for (const reference of externalReferences(document)) {
      if (!knownIds.has(reference)) fail(`timeline_unresolved_schema_id:${reference}`);
    }
  }

  const ajv = new Ajv({
    allErrors: true,
    strict: true,
    coerceTypes: false,
    useDefaults: false,
    removeAdditional: false,
  });
  addFormats(ajv);
  try {
    documents.forEach((schema) => ajv.addSchema(schema));
    for (const schema of timelineSchemas) {
      if (!schema.$id.startsWith(TIMELINE_SCHEMA_PREFIX)) fail("timeline_schema_id_outside_catalog");
      if (typeof ajv.getSchema(schema.$id) !== "function") {
        fail(`timeline_unresolved_schema_id:${schema.$id}`);
      }
    }
  } catch (error) {
    if (/duplicate/i.test(String(error))) fail(`timeline_duplicate_schema_id:${error.message}`);
    if (/resolve reference|missingref|unresolved/i.test(String(error))) {
      fail(`timeline_unresolved_schema_id:${error.message}`);
    }
    throw error;
  }
  return ajv;
}

const ajv = createTimelineAjvV1();
const roots = Object.fromEntries(defaultTimelineSchemas.map((schema) => [
  schema.$id,
  ajv.getSchema(schema.$id),
]));

const isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
const daysInMonth = (year, month) => [
  31,
  isLeapYear(year) ? 29 : 28,
  31,
  30,
  31,
  30,
  31,
  31,
  30,
  31,
  30,
  31,
][month - 1];

const timestamp = (value, path = "value") => {
  if (typeof value !== "string" || !PUBLIC_UTC_MILLIS_RE.test(value)) {
    fail(`${path}: timeline_invalid_public_millisecond`);
  }
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  if (year < 1 || day > daysInMonth(year, month) || Number.isNaN(Date.parse(value))) {
    fail(`${path}: timeline_invalid_public_millisecond`);
  }
  return value;
};

const milliseconds = (value, path = "value") => Date.parse(timestamp(value, path));
const durationSeconds = (start, end) => (milliseconds(end) - milliseconds(start)) / 1000;

const assertJsonTree = (value, path = "$") => {
  if (typeof value === "number" && !Number.isFinite(value)) fail(`${path}: timeline numbers must be finite`);
  if (Array.isArray(value)) {
    if (Object.keys(value).length !== value.length) fail(`${path}: timeline arrays must be dense`);
    value.forEach((child, index) => assertJsonTree(child, `${path}[${index}]`));
  } else if (value && typeof value === "object") {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) fail(`${path}: timeline objects must be plain data`);
    Object.entries(value).forEach(([key, child]) => assertJsonTree(child, `${path}.${key}`));
  }
};

const assertCanonicalStrings = (values, label) => {
  if (!Array.isArray(values) || values.some((value) => typeof value !== "string" || value.length === 0)) {
    fail(`${label} must contain non-empty strings`);
  }
  const canonical = [...new Set(values)].sort();
  if (canonical.length !== values.length || canonical.some((value, index) => value !== values[index])) {
    fail(`${label} must be unique and canonically ordered`);
  }
};

const stableJson = (value) => {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
};

const uuid5Url = (name) => {
  const namespace = Buffer.from("6ba7b8119dad11d180b400c04fd430c8", "hex");
  const bytes = createHash("sha1").update(namespace).update(name, "utf8").digest().subarray(0, 16);
  bytes[6] = (bytes[6] & 0x0f) | 0x50;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

export function publicMillisecondSuccessorV1(value) {
  timestamp(value);
  if (value === "9999-12-31T23:59:59.999Z") throw new RangeError("timeline_range_overflow");
  const result = new Date(Date.parse(value) + 1).toISOString();
  timestamp(result, "result");
  return result;
}

const assertPoint = (value) => {
  timestamp(value.eventAt, "eventAt");
  assertCanonicalStrings(value.qualityFlags, "qualityFlags");
  const historical = value.sourceKind === "historical_archive";
  if (historical) {
    timestamp(value.provenance.ingestedAt, "provenance.ingestedAt");
    if (value.timestampQuality !== "source_without_offset_assumed_timezone"
      || value.operatingCycleId === null
      || value.provenance.sourceSystem !== "forzy-csv") {
      fail("sourceKind and provenance must describe the same source");
    }
  } else if (value.timestampQuality !== "assumed_from_retrieval"
    || value.provenance.sourceSystem !== "forzy-api"
    || milliseconds(value.provenance.scheduledAt) > milliseconds(value.provenance.receivedAt)
    || value.eventAt !== value.provenance.receivedAt) {
    fail("sourceKind and provenance must describe the same source");
  }
};

const assertHistoricalAssessment = (value) => {
  const training = value.trainingWindow;
  const assessment = value.assessmentWindow;
  if (!(milliseconds(training.start) <= milliseconds(training.end)
    && milliseconds(assessment.start) <= milliseconds(assessment.end)
    && milliseconds(training.end) < milliseconds(assessment.start)
    && milliseconds(assessment.end) <= milliseconds(value.assessmentAt))) {
    fail("historical assessment windows are not causal");
  }
  assertCanonicalStrings(value.quality.flags, "assessment quality flags");
  assertCanonicalStrings(value.limitations, "assessment limitations");
  const evidenceIds = value.evidence.map((item) => item.id);
  if (new Set(evidenceIds).size !== evidenceIds.length) fail("assessment evidence IDs must be unique");

  const persistence = value.persistence;
  if (value.status === "watch" || value.status === "alert") {
    if (persistence.episodeId === null
      || persistence.episodeStartedAt === null
      || persistence.persistenceCount < 1
      || value.anomalyScore === null
      || value.deteriorationScore === null) {
      fail("watch/alert require scores and causal episode facts");
    }
    if (!(milliseconds(training.end) < milliseconds(persistence.episodeStartedAt)
      && milliseconds(persistence.episodeStartedAt) <= milliseconds(assessment.end)
      && milliseconds(assessment.end) <= milliseconds(value.assessmentAt))) {
      fail("historical assessment episode is not causal");
    }
    if (persistence.persistenceSeconds !== durationSeconds(persistence.episodeStartedAt, assessment.end)) {
      fail("persistenceSeconds must use original causal timestamps");
    }
  } else {
    if (persistence.episodeId !== null
      || persistence.episodeStartedAt !== null
      || persistence.persistenceSeconds !== 0
      || persistence.persistenceCount !== 0) {
      fail("non-episode assessment persistence must be null/zero");
    }
    if (value.status === "insufficient_data"
      && (value.anomalyScore !== null || value.deteriorationScore !== null)) {
      fail("non-evaluable assessments require null scores");
    }
    if (value.status === "normal"
      && (value.anomalyScore === null || value.deteriorationScore === null)) {
      fail("evaluable normal assessments require scores");
    }
  }
};

const assertCollectionPolicy = (value) => {
  if (JSON.stringify(value.activeWeekdays) !== JSON.stringify(["monday", "tuesday", "wednesday"])) {
    fail("activeWeekdays must be ordered and complete");
  }
  if (value.effectiveTo !== null && milliseconds(value.effectiveTo) <= milliseconds(value.effectiveFrom)) {
    fail("effectiveTo must be later than effectiveFrom");
  }
  const selected = Object.fromEntries([
    "schemaVersion",
    "collectionPolicyId",
    "assetId",
    "timezone",
    "activeWeekdays",
    "windowStartLocal",
    "windowEndLocal",
    "pollIntervalSeconds",
    "gapThresholdSeconds",
  ].map((key) => [key, value[key]]));
  const expected = `sha256:${createHash("sha256").update(stableJson(selected), "utf8").digest("hex")}`;
  if (value.configurationHash !== expected) fail("configurationHash does not match canonical policy");
};

const assertCandidate = (value) => {
  if (milliseconds(value.episodeStartedAt) > milliseconds(value.eventAt)) {
    fail("episodeStartedAt must not follow eventAt");
  }
  assertCanonicalStrings(value.quality.flags, "candidate quality flags");
  const historical = value.sourceKind === "historical_archive";
  if (historical) {
    if ([value.operatingCycleId, value.batchId, value.foldId].some((item) => item === null)) {
      fail("historical candidates require archive facts");
    }
  } else if (value.batchId !== null || value.foldId !== null) {
    fail("live candidate cannot claim archive facts");
  }
  if (value.quality.status === "degraded" && value.dataTrust === "sufficient") {
    fail("candidate trust is better than quality evidence");
  }
  if (value.quality.status === "insufficient_data" && value.dataTrust !== "insufficient") {
    fail("insufficient quality requires insufficient trust");
  }
  const identityName = [
    "timeline-event-candidate-v1",
    value.sourceKind,
    value.batchId ?? "none",
    value.anchorPointId,
    value.modelFamily,
    value.modelVersion,
    value.foldId ?? "none",
  ].join("|");
  if (value.candidateId !== uuid5Url(identityName)) {
    fail("candidateId does not match its frozen UUIDv5 identity");
  }
};

const assertDecisionFacts = (value) => {
  const noScope = value.conditionTemporalScope === "none";
  const noSource = value.conditionSource === "none";
  if (value.conditionAsOf !== null) timestamp(value.conditionAsOf, "conditionAsOf");
  if (value.conditionEpisodeStartedAt !== null) {
    timestamp(value.conditionEpisodeStartedAt, "conditionEpisodeStartedAt");
  }
  if (noScope !== noSource) fail("condition temporal scope and source must agree");
  if (noScope && (value.conditionAsOf !== null || value.conditionEpisodeStartedAt !== null)) {
    fail("none condition facts require null timestamps");
  }
  if (!noSource && value.conditionAsOf === null) fail("condition evidence requires conditionAsOf");
  if (value.conditionEpisodeStartedAt !== null
    && (value.conditionAsOf === null
      || milliseconds(value.conditionEpisodeStartedAt) > milliseconds(value.conditionAsOf))) {
    fail("condition episode facts are invalid");
  }
  if (value.collectionState === "historical_gap") {
    const expected = {
      conditionState: "unknown",
      conditionTemporalScope: "none",
      conditionAsOf: null,
      conditionEpisodeStartedAt: null,
      conditionSource: "none",
      collectionState: "historical_gap",
      collectionExpectation: "not_applicable",
      dataAvailability: "gap",
      dataFreshness: "historical",
      dataTrust: "insufficient",
    };
    if (Object.entries(expected).some(([key, expectedValue]) => value[key] !== expectedValue)) {
      fail("historical gap facts are crossed");
    }
  }
  if (value.collectionState === "historical_context"
    && !(value.collectionExpectation === "not_applicable"
      && ["complete", "partial"].includes(value.dataAvailability)
      && value.dataFreshness === "historical"
      && value.conditionTemporalScope !== "current")) {
    fail("historical context facts are crossed");
  }
  if (value.conditionSource === "historical_walk_forward"
    && value.conditionTemporalScope !== "historical") {
    fail("historical assessment requires historical temporal scope");
  }
  if (value.collectionState === "expected_idle"
    && value.collectionExpectation !== "expected_idle") {
    fail("expected-idle collection facts are crossed");
  }
  if (["gap", "unavailable"].includes(value.dataAvailability)
    && value.conditionTemporalScope === "current") {
    fail("gap or unavailable data cannot claim current condition");
  }
  if (value.collectionState === "unavailable" && value.dataAvailability !== "unavailable") {
    fail("unavailable collection facts are crossed");
  }
  if (value.conditionState === "normal"
    && (value.dataTrust !== "sufficient" || value.dataAvailability !== "complete")
    && !(noScope && noSource && value.conditionAsOf === null && value.conditionEpisodeStartedAt === null)) {
    fail("degraded normality must suppress temporal condition claims");
  }
};

const assertOverview = (value) => {
  const requested = value.requestedRange;
  if (requested.from !== null) timestamp(requested.from, "requestedRange.from");
  if (requested.to !== null) timestamp(requested.to, "requestedRange.to");
  if (requested.from !== null && requested.to !== null
    && milliseconds(requested.from) >= milliseconds(requested.to)) {
    fail("requestedRange must be increasing");
  }

  const segmentById = new Map();
  const segmentKeys = [];
  for (const segment of value.segments) {
    if (segmentById.has(segment.segmentId)) fail("segment IDs must be unique");
    segmentById.set(segment.segmentId, segment);
    segmentKeys.push(`${segment.startAt}|${segment.segmentId}`);
    if (milliseconds(segment.startAt) > milliseconds(segment.endAt)) fail("segment startAt must not follow endAt");
    if (segment.sensorCounts.s1 + segment.sensorCounts.s2 !== segment.totalPoints) {
      fail("segment sensor counts must equal totalPoints");
    }
    assertCanonicalStrings(segment.assumptions, "segment assumptions");
    if (segment.sourceKind === "historical_archive") {
      if (segment.batchId === null
        || segment.collectionPolicyId !== null
        || segment.timestampQuality !== "source_without_offset_assumed_timezone") {
        fail("archive segment source facts are crossed");
      }
      if (value.activeHistoricalBatchId !== segment.batchId) {
        fail("archive segment must use the active historical batch");
      }
    } else if (segment.batchId !== null || segment.timestampQuality !== "assumed_from_retrieval") {
      fail("live segment source facts are crossed");
    }
  }
  if (JSON.stringify(segmentKeys) !== JSON.stringify([...segmentKeys].sort())) {
    fail("segments must use deterministic total order");
  }

  const messageByType = {
    source_discontinuity: "timeline_gap_source_discontinuity",
    archive_sampling_gap: "timeline_gap_archive_sampling",
    live_expected_collection_gap: "timeline_gap_live_expected_collection",
    expected_idle: "timeline_gap_expected_idle",
    unclassified_coverage_gap: "timeline_gap_unclassified_coverage",
  };
  const seenGapIds = new Set();
  const gapPairs = new Set();
  const gapKeys = [];
  for (const gap of value.gaps) {
    if (seenGapIds.has(gap.gapId)) fail("gap IDs must be unique");
    seenGapIds.add(gap.gapId);
    gapKeys.push(`${gap.startAt}|${gap.endAt}|${gap.gapId}`);
    if (milliseconds(gap.startAt) >= milliseconds(gap.endAt)
      || gap.durationSeconds !== durationSeconds(gap.startAt, gap.endAt)) {
      fail("gap duration must equal its open interval");
    }
    if (gap.messageCode !== messageByType[gap.gapType]) fail("gap type and message code must agree");
    const identityName = [
      "timeline-gap-v1",
      gap.gapType,
      gap.leftSegmentId ?? "none",
      gap.rightSegmentId ?? "none",
      gap.startAt,
      gap.endAt,
      gap.ruleVersion,
    ].join("|");
    if (gap.gapId !== uuid5Url(identityName)) {
      fail("gapId does not match its frozen UUIDv5 identity");
    }
    if (gap.leftSegmentId === null && gap.rightSegmentId === null) fail("a gap must border at least one segment");
    const left = gap.leftSegmentId === null ? null : segmentById.get(gap.leftSegmentId);
    const right = gap.rightSegmentId === null ? null : segmentById.get(gap.rightSegmentId);
    if (gap.leftSegmentId !== null && (!left || left.endAt !== gap.startAt)) {
      fail("leftSegmentId does not border the gap");
    }
    if (gap.rightSegmentId !== null && (!right || right.startAt !== gap.endAt)) {
      fail("rightSegmentId does not border the gap");
    }
    if (left && right) {
      const differentSources = left.sourceKind !== right.sourceKind;
      if (differentSources !== (gap.gapType === "source_discontinuity")) {
        fail("source discontinuity gap type is crossed");
      }
      if (!differentSources && left.sourceKind === "historical_archive" && gap.gapType !== "archive_sampling_gap") {
        fail("archive segments require archive sampling gaps");
      }
      if (!differentSources && left.sourceKind === "live_collection") {
        const policies = new Set([left.collectionPolicyId, right.collectionPolicyId]);
        if (gap.gapType === "unclassified_coverage_gap" && !policies.has(null)) {
          fail("classified live policy cannot claim an unclassified gap");
        }
        if (["live_expected_collection_gap", "expected_idle"].includes(gap.gapType)
          && (policies.has(null) || policies.size !== 1)) {
          fail("classified live gaps require one persisted policy");
        }
      }
    }
    gapPairs.add(`${gap.leftSegmentId}|${gap.rightSegmentId}`);
  }
  if (JSON.stringify(gapKeys) !== JSON.stringify([...gapKeys].sort())) fail("gaps must use deterministic order");
  for (let index = 0; index + 1 < value.segments.length; index += 1) {
    const left = value.segments[index];
    const right = value.segments[index + 1];
    if (milliseconds(left.endAt) > milliseconds(right.startAt)) fail("segments must not overlap");
    if (milliseconds(left.endAt) < milliseconds(right.startAt)
      && !gapPairs.has(`${left.segmentId}|${right.segmentId}`)) {
      fail("every inter-segment coverage gap must be explicit");
    }
  }

  const candidateCounts = new Map();
  for (const candidate of value.eventCandidates) {
    assertCandidate(candidate);
    if (candidate.operatingCycleId !== null) {
      candidateCounts.set(candidate.operatingCycleId, (candidateCounts.get(candidate.operatingCycleId) ?? 0) + 1);
    }
    if (candidate.sourceKind === "historical_archive" && candidate.batchId !== value.activeHistoricalBatchId) {
      fail("historical candidate must use the active batch");
    }
  }
  const cycleKeys = [];
  const seenCycleIds = new Set();
  const cycleById = new Map();
  let previousId = null;
  let previousCycle = null;
  value.operatingCycles.forEach((cycle, index) => {
    if (seenCycleIds.has(cycle.operatingCycleId)) fail("operating cycle IDs must be unique");
    seenCycleIds.add(cycle.operatingCycleId);
    cycleById.set(cycle.operatingCycleId, cycle);
    cycleKeys.push(`${cycle.startAt}|${cycle.operatingCycleId}`);
    if (cycle.sensorCounts.s1 + cycle.sensorCounts.s2 !== cycle.totalPoints) {
      fail("cycle sensor counts must equal totalPoints");
    }
    const duration = durationSeconds(cycle.startAt, cycle.endAt);
    if (duration < 0 || cycle.durationSeconds !== duration) fail("cycle duration must equal its inclusive endpoints");
    if (cycle.batchId !== value.activeHistoricalBatchId) fail("operating cycles must use the active historical batch");
    if (cycle.previousOperatingCycleId !== previousId) {
      fail("previousOperatingCycleId must name the immediate predecessor");
    }
    if (cycle.candidateCount !== (candidateCounts.get(cycle.operatingCycleId) ?? 0)) {
      fail("cycle candidateCount must match returned candidates");
    }
    if (index === 0) {
      if (cycle.gapBeforeSeconds !== null) fail("the first cycle cannot claim a previous gap");
    } else {
      const expectedGap = durationSeconds(previousCycle.endAt, cycle.startAt);
      if (expectedGap < 0 || cycle.gapBeforeSeconds !== expectedGap) {
        fail("gapBeforeSeconds must match consecutive cycle endpoints");
      }
    }
    assertCanonicalStrings(cycle.assumptions, "cycle assumptions");
    previousId = cycle.operatingCycleId;
    previousCycle = cycle;
  });
  if (JSON.stringify(cycleKeys) !== JSON.stringify([...cycleKeys].sort())) {
    fail("operating cycles must be ordered by startAt and ID");
  }
  for (const candidate of value.eventCandidates) {
    if (candidate.sourceKind !== "historical_archive") continue;
    const cycle = cycleById.get(candidate.operatingCycleId);
    if (!cycle) fail("historical candidate references an unknown operating cycle");
    if (milliseconds(candidate.eventAt) < milliseconds(cycle.startAt)
      || milliseconds(candidate.eventAt) > milliseconds(cycle.endAt)) {
      fail("historical candidate event does not belong to its cycle");
    }
  }

  const combinations = new Map();
  const totals = { original: 0, returned: 0, omitted: 0 };
  const seenPointIds = new Set();
  const seenSeriesGroups = new Set();
  const resolvedMetrics = new Set();
  const seriesKeys = [];
  for (const row of value.series) {
    const segment = segmentById.get(row.segmentId);
    if (!segment) fail("series references an unknown segment");
    if (segment.sourceKind !== row.sourceKind) fail("series crosses segment source");
    const group = `${row.segmentId}|${row.sensorId}|${row.sourceKind}`;
    if (seenSeriesGroups.has(group)) fail("series group must be unique");
    seenSeriesGroups.add(group);
    resolvedMetrics.add(row.metric);
    const aggregation = row.aggregation;
    if (aggregation.returnedPointCount !== row.points.length
      || aggregation.omittedPointCount !== aggregation.originalPointCount - aggregation.returnedPointCount) {
      fail("series aggregation counts are invalid");
    }
    if (aggregation.originalPointCount !== segment.sensorCounts[row.sensorId]) {
      fail("series membership disagrees with segment sensor counts");
    }
    const pointKeys = [];
    for (const point of row.points) {
      if (seenPointIds.has(point.pointId)) fail("series cannot duplicate original point IDs");
      seenPointIds.add(point.pointId);
      if (milliseconds(point.eventAt) < milliseconds(segment.startAt)
        || milliseconds(point.eventAt) > milliseconds(segment.endAt)) {
        fail("series point does not belong to its segment");
      }
      pointKeys.push(`${point.eventAt}|${point.pointId}`);
    }
    if (JSON.stringify(pointKeys) !== JSON.stringify([...pointKeys].sort())) {
      fail("series points must retain total order");
    }
    const combinationKey = `${row.sensorId}|${row.sourceKind}`;
    combinations.set(combinationKey, [...(combinations.get(combinationKey) ?? []), row]);
    seriesKeys.push(`${segment.startAt}|${row.segmentId}|${row.sourceKind}|${row.sensorId}|${row.metric}`);
    totals.original += aggregation.originalPointCount;
    totals.returned += aggregation.returnedPointCount;
    totals.omitted += aggregation.omittedPointCount;
  }
  if (JSON.stringify(seriesKeys) !== JSON.stringify([...seriesKeys].sort())) {
    fail("series must use deterministic segment order");
  }
  if (resolvedMetrics.size > 1) fail("one response must resolve exactly one metric");

  const summary = value.aggregationSummary;
  for (const rows of combinations.values()) {
    const ceilings = new Set(rows.map((row) => row.aggregation.requestedMaxPoints));
    const methods = new Set(rows.map((row) => row.aggregation.method));
    if (ceilings.size !== 1 || !ceilings.has(summary.requestedMaxPoints) || methods.size !== 1) {
      fail("series combination ceiling and method must agree");
    }
    const original = rows.reduce((sum, row) => sum + row.aggregation.originalPointCount, 0);
    const returned = rows.reduce((sum, row) => sum + row.aggregation.returnedPointCount, 0);
    const expectedMethod = original <= summary.requestedMaxPoints ? "none" : "time_bucket_envelope_v1";
    if (!methods.has(expectedMethod) || returned > summary.requestedMaxPoints) {
      fail("global sensor/source aggregation budget is invalid");
    }
  }
  if (summary.originalPointCount !== totals.original
    || summary.returnedPointCount !== totals.returned
    || summary.omittedPointCount !== totals.omitted) {
    fail("aggregation summary does not equal series totals");
  }
  const reducedCount = value.series.filter((row) => row.aggregation.method !== "none").length;
  if (summary.reducedSeriesCount !== reducedCount) {
    fail("reducedSeriesCount must equal reduced segment series");
  }

  if (value.availableRange !== null
    && milliseconds(value.availableRange.from) >= milliseconds(value.availableRange.to)) {
    fail("availableRange must be increasing");
  }
  if (value.segments.length === 0) {
    if (value.effectiveRange !== null || value.series.length !== 0) {
      fail("an empty query result requires null effectiveRange and no series");
    }
  } else {
    if (value.effectiveRange === null || value.availableRange === null) {
      fail("returned coverage requires effective and available ranges");
    }
    const earliest = value.segments.map((segment) => segment.startAt).sort()[0];
    const latest = value.segments.map((segment) => segment.endAt).sort().at(-1);
    const successor = publicMillisecondSuccessorV1(latest);
    if (milliseconds(value.availableRange.from) > milliseconds(earliest)
      || milliseconds(successor) > milliseconds(value.availableRange.to)) {
      fail("availableRange must cover returned source points");
    }
    if (milliseconds(value.effectiveRange.from) >= milliseconds(value.effectiveRange.to)) {
      fail("effectiveRange must be increasing");
    }
    if (milliseconds(value.effectiveRange.from) > milliseconds(earliest)
      || milliseconds(successor) > milliseconds(value.effectiveRange.to)) {
      fail("effectiveRange must cover returned segments");
    }
    const expectedFrom = requested.from === null ? value.availableRange.from : requested.from;
    const expectedTo = requested.to === null ? value.availableRange.to : requested.to;
    if (value.effectiveRange.from !== expectedFrom || value.effectiveRange.to !== expectedTo) {
      fail("effectiveRange must preserve explicit bounds and resolve unbounded bounds");
    }
    if (requested.from === null && requested.to === null
      && (value.availableRange.from !== earliest || value.availableRange.to !== successor)) {
      fail("unbounded availableRange must minimally cover all source points");
    }
  }
};

const assertPage = (value) => {
  value.items.forEach((item) => {
    assertPoint(item);
    if (item.sourceKind === "historical_archive"
      && item.provenance.batchId !== value.activeHistoricalBatchId) {
      fail("archive page item must use the active historical batch");
    }
  });
  const keys = value.items.map((item) => `${item.eventAt}|${item.pointId}`);
  if (JSON.stringify(keys) !== JSON.stringify([...keys].sort())
    || new Set(value.items.map((item) => item.pointId)).size !== value.items.length) {
    fail("timeline page items must be unique and totally ordered");
  }
  if (value.hasMore !== (value.nextCursor !== null)) fail("nextCursor and hasMore must agree");
};

const assertContext = (value) => {
  timestamp(value.selectedAt, "selectedAt");
  const facts = value.decisionFacts;
  const provenance = value.provenance;
  const capabilities = value.capabilities;
  assertDecisionFacts(facts);
  assertCanonicalStrings(value.limitations, "context limitations");
  const returnedChannels = [];
  for (const sensorId of ["s1", "s2"]) {
    const point = value.channels[sensorId];
    if (point === null) continue;
    assertPoint(point);
    if (point.sensorId !== sensorId) fail("context channel sensorId must match its map key");
    returnedChannels.push(point);
  }
  if (value.anchor !== null) {
    assertPoint(value.anchor);
    if (!returnedChannels.some((point) => point.pointId === value.anchor.pointId)) {
      fail("context anchor must be one of the returned original channels");
    }
  } else if (returnedChannels.length > 0) {
    fail("returned context channels require an anchor");
  }
  const expectedAvailability = returnedChannels.length === 2 ? "complete" : "partial";
  if (returnedChannels.length === 0) {
    if (!["gap", "unavailable"].includes(facts.dataAvailability)) {
      fail("no channels require gap or unavailable availability");
    }
  } else if (facts.dataAvailability !== expectedAvailability) {
    fail("dataAvailability must reflect returned channels");
  }
  const paired = returnedChannels.length === 2;
  if (capabilities.pairedChannels !== paired) fail("pairedChannels must reflect returned channels");
  if (capabilities.causalAssessment !== (value.assessment !== null)) {
    fail("causalAssessment must reflect the returned assessment");
  }

  if (paired) {
    const [left, right] = returnedChannels;
    for (const key of ["samplePairId", "eventAt", "sourceKind", "operatingCycleId", "assetId"]) {
      if (left[key] !== right[key]) fail("paired context channels must share original pair facts");
    }
    if (left.provenance.sourceSystem !== right.provenance.sourceSystem) {
      fail("paired context channels cannot cross source systems");
    }
    if (left.sourceKind === "historical_archive"
      && left.provenance.batchId !== right.provenance.batchId) {
      fail("paired historical channels cannot cross batches");
    }
    if (left.sourceKind === "live_collection"
      && left.provenance.collectionPolicyId !== right.provenance.collectionPolicyId) {
      fail("paired live channels cannot cross collection policies");
    }
  }

  if (provenance.pointSourceKind === null) {
    if (provenance.pointSourceSystem !== null || provenance.collectionPolicyId !== null) {
      fail("no-point provenance cannot claim a source or policy");
    }
  } else if (provenance.pointSourceKind === "historical_archive") {
    if (provenance.pointSourceSystem !== "forzy-csv"
      || provenance.activeHistoricalBatchId === null
      || provenance.collectionPolicyId !== null
      || !["historical_walk_forward", "none"].includes(provenance.assessmentSource)) {
      fail("historical provenance facts are crossed");
    }
  } else if (provenance.pointSourceSystem !== "forzy-api"
    || !["live_assessment", "none"].includes(provenance.assessmentSource)) {
    fail("live provenance facts are crossed");
  }
  if (returnedChannels.length > 0) {
    if (value.segmentId === null) fail("returned context points require segmentId");
    if (returnedChannels.some((point) => point.sourceKind !== provenance.pointSourceKind)) {
      fail("context points and provenance source kind must agree");
    }
    if (value.anchor !== null && value.anchor.sourceKind !== provenance.pointSourceKind) {
      fail("context anchor and provenance source kind must agree");
    }
    if (provenance.pointSourceKind === "historical_archive") {
      const batches = new Set(returnedChannels.map((point) => point.provenance.batchId));
      if (batches.size !== 1 || !batches.has(provenance.activeHistoricalBatchId)) {
        fail("historical context points must use the active batch");
      }
    } else {
      const policies = new Set(returnedChannels.map((point) => point.provenance.collectionPolicyId));
      if (policies.size !== 1 || !policies.has(provenance.collectionPolicyId)) {
        fail("live context points must use the claimed collection policy");
      }
    }
  }
  if (provenance.assessmentSource !== facts.conditionSource) {
    fail("assessment source must agree across context facts");
  }
  if (provenance.collectionPolicyId === null && facts.collectionExpectation === "expected_now") {
    fail("a missing policy cannot become expected_now");
  }
  const historicalState = ["historical_context", "historical_gap"].includes(facts.collectionState);
  if (capabilities.historicalNavigation !== historicalState) {
    fail("historicalNavigation must reflect collection state");
  }
  if (historicalState
    && !(facts.dataFreshness === "historical"
      && ["historical_context", "historical_gap"].includes(facts.collectionState)
      && facts.collectionExpectation === "not_applicable"
      && facts.conditionTemporalScope !== "current")) {
    fail("historical navigation facts are crossed");
  }
  if (facts.collectionState === "historical_gap"
    && !(value.segmentId === null
      && value.anchor === null
      && value.channels.s1 === null
      && value.channels.s2 === null
      && value.assessment === null)) {
    fail("historical gap context cannot carry point facts");
  }

  const assessment = value.assessment;
  if (assessment === null) {
    if (facts.conditionEpisodeStartedAt !== null || facts.conditionSource !== "none") {
      fail("condition evidence requires a returned matching assessment");
    }
  } else if (assessment.schemaVersion === "1.0") {
    assertHistoricalAssessment(assessment);
    if (facts.conditionSource !== "historical_walk_forward"
      || facts.conditionState !== assessment.status
      || facts.conditionAsOf !== assessment.assessmentAt
      || facts.conditionEpisodeStartedAt !== assessment.persistence.episodeStartedAt) {
      fail("historical condition facts do not match the assessment");
    }
    if (value.anchor !== null
      && !(value.anchor.pointId === assessment.anchorPointId
        && value.anchor.sensorId === assessment.sensorId
        && value.anchor.operatingCycleId === assessment.operatingCycleId
        && milliseconds(assessment.assessmentAt) <= milliseconds(value.anchor.eventAt))) {
      fail("historical assessment anchor facts are crossed");
    }
  } else if (facts.conditionSource !== "live_assessment"
    || facts.conditionState !== assessment.assessment.status) {
    fail("live condition facts do not match the assessment");
  }
};

export function assertTimelineInvariantsV1(value, schemaName = null) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail("timeline payload must be an object");
  assertJsonTree(value);
  let name = schemaName?.replace(TIMELINE_SCHEMA_PREFIX, "") ?? null;
  if (name === null) {
    if (Object.hasOwn(value, "segments")) name = "timeline-overview";
    else if (Object.hasOwn(value, "configurationHash")) name = "collection-policy";
    else if (Object.hasOwn(value, "candidateId")) name = "timeline-event-candidate";
    else if (Object.hasOwn(value, "decisionFacts")) name = "timeline-context";
    else if (Object.hasOwn(value, "conditionState")) name = "timeline-decision-facts";
    else if (Object.hasOwn(value, "items") && Object.hasOwn(value, "hasMore")) name = "timeline-page";
    else if (Object.hasOwn(value, "assessmentId") && value.schemaVersion === "1.0") name = "historical-assessment";
    else if (Object.hasOwn(value, "pointId")) name = "timeline-point";
    else if (Object.hasOwn(value, "readingId") && value.sourceKind === "historical_archive") name = "historical-sensor-reading";
  }
  if (name === "historical-sensor-reading") {
    timestamp(value.eventAt, "eventAt");
    timestamp(value.provenance.ingestedAt, "provenance.ingestedAt");
    assertCanonicalStrings(value.qualityFlags, "qualityFlags");
  }
  else if (name === "timeline-point") assertPoint(value);
  else if (name === "historical-assessment") assertHistoricalAssessment(value);
  else if (name === "collection-policy") assertCollectionPolicy(value);
  else if (name === "timeline-event-candidate") assertCandidate(value);
  else if (name === "timeline-overview") assertOverview(value);
  else if (name === "timeline-page") assertPage(value);
  else if (name === "timeline-decision-facts") assertDecisionFacts(value);
  else if (name === "timeline-context") assertContext(value);
  else fail(`unknown timeline schema:${name}`);
  return value;
}

export function assertTimelinePayloadV1(schemaId, value) {
  const normalizedId = schemaId.startsWith(TIMELINE_SCHEMA_PREFIX)
    ? schemaId
    : `${TIMELINE_SCHEMA_PREFIX}${schemaId}`;
  const validator = roots[normalizedId];
  if (!validator) fail(`timeline_unresolved_schema_id:${normalizedId}`);
  if (!validator(value)) fail(ajv.errorsText(validator.errors, { separator: "; " }));
  return assertTimelineInvariantsV1(value, normalizedId);
}

export const assertHistoricalSensorReadingV1 = (value) => assertTimelinePayloadV1("historical-sensor-reading", value);
export const assertTimelinePointV1 = (value) => assertTimelinePayloadV1("timeline-point", value);
export const assertHistoricalAssessmentV1 = (value) => assertTimelinePayloadV1("historical-assessment", value);
export const assertCollectionPolicyV1 = (value) => assertTimelinePayloadV1("collection-policy", value);
export const assertTimelineEventCandidateV1 = (value) => assertTimelinePayloadV1("timeline-event-candidate", value);
export const assertTimelineOverviewV1 = (value) => assertTimelinePayloadV1("timeline-overview", value);
export const assertTimelinePageV1 = (value) => assertTimelinePayloadV1("timeline-page", value);
export const assertTimelineDecisionFactsV1 = (value) => assertTimelinePayloadV1("timeline-decision-facts", value);
export const assertTimelineContextV1 = (value) => assertTimelinePayloadV1("timeline-context", value);
