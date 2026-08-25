import Ajv from "ajv";
import addFormats from "ajv-formats";
import assetConditionAssessmentSchema from "../../contracts/v2/asset-condition-assessment.schema.json";
import collectionPolicySchema from "../../contracts/timeline/v1/collection-policy.schema.json";
import historicalAssessmentSchema from "../../contracts/timeline/v1/historical-assessment.schema.json";
import historicalSensorReadingSchema from "../../contracts/timeline/v1/historical-sensor-reading.schema.json";
import timelineContextSchema from "../../contracts/timeline/v1/timeline-context.schema.json";
import timelineAssessmentOverviewSchema from "../../contracts/timeline/v1/timeline-assessment-overview.schema.json";
import timelineDecisionFactsSchema from "../../contracts/timeline/v1/timeline-decision-facts.schema.json";
import timelineEventCandidateSchema from "../../contracts/timeline/v1/timeline-event-candidate.schema.json";
import timelineOverviewSchema from "../../contracts/timeline/v1/timeline-overview.schema.json";
import timelinePageSchema from "../../contracts/timeline/v1/timeline-page.schema.json";
import timelinePointSchema from "../../contracts/timeline/v1/timeline-point.schema.json";

export const TIMELINE_SCHEMA_VERSION_V1 = "1.0";
export const PUBLIC_UTC_MILLIS_RE = /^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d\.\d{3}Z$/;

const TIMELINE_SCHEMA_PREFIX = "forzy://contracts/timeline/v1/";
const defaultTimelineSchemas = [
  historicalSensorReadingSchema,
  timelinePointSchema,
  historicalAssessmentSchema,
  collectionPolicySchema,
  timelineEventCandidateSchema,
  timelineOverviewSchema,
  timelinePageSchema,
  timelineDecisionFactsSchema,
  timelineContextSchema,
  timelineAssessmentOverviewSchema,
];
const defaultAssetAssessmentSchema = assetConditionAssessmentSchema;

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

const textEncoder = new TextEncoder();
const utf8Bytes = (value) => textEncoder.encode(value);
const concatenateBytes = (...arrays) => {
  const output = new Uint8Array(arrays.reduce((total, array) => total + array.length, 0));
  let offset = 0;
  for (const array of arrays) {
    output.set(array, offset);
    offset += array.length;
  }
  return output;
};
const paddedHashInput = (input) => {
  const output = new Uint8Array(Math.ceil((input.length + 9) / 64) * 64);
  output.set(input);
  output[input.length] = 0x80;
  const bitLength = input.length * 8;
  const view = new DataView(output.buffer);
  view.setUint32(output.length - 8, Math.floor(bitLength / 0x100000000));
  view.setUint32(output.length - 4, bitLength >>> 0);
  return output;
};
const leftRotate = (value, count) => ((value << count) | (value >>> (32 - count))) >>> 0;
const rightRotate = (value, count) => ((value >>> count) | (value << (32 - count))) >>> 0;
const wordsToBytes = (words) => {
  const output = new Uint8Array(words.length * 4);
  const view = new DataView(output.buffer);
  words.forEach((word, index) => view.setUint32(index * 4, word >>> 0));
  return output;
};
const bytesToHex = (bytes) => [...bytes]
  .map((byte) => byte.toString(16).padStart(2, "0"))
  .join("");

const sha1Bytes = (input) => {
  const padded = paddedHashInput(input);
  const view = new DataView(padded.buffer);
  const hash = new Uint32Array([
    0x67452301,
    0xefcdab89,
    0x98badcfe,
    0x10325476,
    0xc3d2e1f0,
  ]);
  const schedule = new Uint32Array(80);
  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      schedule[index] = view.getUint32(offset + index * 4);
    }
    for (let index = 16; index < 80; index += 1) {
      schedule[index] = leftRotate(
        schedule[index - 3] ^ schedule[index - 8] ^ schedule[index - 14] ^ schedule[index - 16],
        1,
      );
    }
    let [a, b, c, d, e] = hash;
    for (let index = 0; index < 80; index += 1) {
      let f;
      let k;
      if (index < 20) {
        f = (b & c) | (~b & d);
        k = 0x5a827999;
      } else if (index < 40) {
        f = b ^ c ^ d;
        k = 0x6ed9eba1;
      } else if (index < 60) {
        f = (b & c) | (b & d) | (c & d);
        k = 0x8f1bbcdc;
      } else {
        f = b ^ c ^ d;
        k = 0xca62c1d6;
      }
      const next = (leftRotate(a, 5) + f + e + k + schedule[index]) >>> 0;
      e = d;
      d = c;
      c = leftRotate(b, 30);
      b = a;
      a = next;
    }
    hash[0] = (hash[0] + a) >>> 0;
    hash[1] = (hash[1] + b) >>> 0;
    hash[2] = (hash[2] + c) >>> 0;
    hash[3] = (hash[3] + d) >>> 0;
    hash[4] = (hash[4] + e) >>> 0;
  }
  return wordsToBytes([...hash]);
};

const SHA256_CONSTANTS = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

const sha256Bytes = (input) => {
  const padded = paddedHashInput(input);
  const view = new DataView(padded.buffer);
  const hash = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  const schedule = new Uint32Array(64);
  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      schedule[index] = view.getUint32(offset + index * 4);
    }
    for (let index = 16; index < 64; index += 1) {
      const s0 = rightRotate(schedule[index - 15], 7)
        ^ rightRotate(schedule[index - 15], 18)
        ^ (schedule[index - 15] >>> 3);
      const s1 = rightRotate(schedule[index - 2], 17)
        ^ rightRotate(schedule[index - 2], 19)
        ^ (schedule[index - 2] >>> 10);
      schedule[index] = (schedule[index - 16] + s0 + schedule[index - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const sigma1 = rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25);
      const choice = (e & f) ^ (~e & g);
      const first = (h + sigma1 + choice + SHA256_CONSTANTS[index] + schedule[index]) >>> 0;
      const sigma0 = rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const second = (sigma0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + first) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (first + second) >>> 0;
    }
    hash[0] = (hash[0] + a) >>> 0;
    hash[1] = (hash[1] + b) >>> 0;
    hash[2] = (hash[2] + c) >>> 0;
    hash[3] = (hash[3] + d) >>> 0;
    hash[4] = (hash[4] + e) >>> 0;
    hash[5] = (hash[5] + f) >>> 0;
    hash[6] = (hash[6] + g) >>> 0;
    hash[7] = (hash[7] + h) >>> 0;
  }
  return wordsToBytes([...hash]);
};

const uuid5Url = (name) => {
  const namespace = new Uint8Array([
    0x6b, 0xa7, 0xb8, 0x11, 0x9d, 0xad, 0x11, 0xd1,
    0x80, 0xb4, 0x00, 0xc0, 0x4f, 0xd4, 0x30, 0xc8,
  ]);
  const bytes = sha1Bytes(concatenateBytes(namespace, utf8Bytes(name))).slice(0, 16);
  bytes[6] = (bytes[6] & 0x0f) | 0x50;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytesToHex(bytes);
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
  const effectiveFrom = milliseconds(value.effectiveFrom);
  if (value.effectiveTo !== null && milliseconds(value.effectiveTo) <= effectiveFrom) {
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
  const expected = `sha256:${bytesToHex(sha256Bytes(utf8Bytes(stableJson(selected))))}`;
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
  const requiredSeriesGroups = new Set(value.segments.flatMap((segment) => ["s1", "s2"]
    .filter((sensorId) => segment.sensorCounts[sensorId] > 0)
    .map((sensorId) => `${segment.segmentId}|${sensorId}|${segment.sourceKind}`)));
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
    if (aggregation.method === "none"
      && (aggregation.returnedPointCount !== aggregation.originalPointCount
        || aggregation.omittedPointCount !== 0)) {
      fail("none aggregation must retain every original point");
    }
    if (aggregation.originalPointCount !== segment.sensorCounts[row.sensorId]) {
      fail("series membership disagrees with segment sensor counts");
    }
    const pointTimes = [];
    for (const point of row.points) {
      if (seenPointIds.has(point.pointId)) fail("series cannot duplicate original point IDs");
      seenPointIds.add(point.pointId);
      if (milliseconds(point.eventAt) < milliseconds(segment.startAt)
        || milliseconds(point.eventAt) > milliseconds(segment.endAt)) {
        fail("series point does not belong to its segment");
      }
      pointTimes.push(milliseconds(point.eventAt));
    }
    if (pointTimes.some((pointTime, index) => index > 0 && pointTime < pointTimes[index - 1])) {
      fail("series points must retain chronological order");
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
  if (seenSeriesGroups.size !== requiredSeriesGroups.size
    || [...seenSeriesGroups].some((group) => !requiredSeriesGroups.has(group))) {
    fail("series must exactly cover every nonzero segment sensor group");
  }

  const summary = value.aggregationSummary;
  for (const rows of combinations.values()) {
    const ceilings = new Set(rows.map((row) => row.aggregation.requestedMaxPoints));
    const methods = new Set(rows.map((row) => row.aggregation.method));
    if (ceilings.size !== 1 || !ceilings.has(summary.requestedMaxPoints) || methods.size !== 1) {
      fail("series combination ceiling and method must agree");
    }
    const original = rows.reduce((sum, row) => sum + row.aggregation.originalPointCount, 0);
    const returned = rows.reduce((sum, row) => sum + row.aggregation.returnedPointCount, 0);
    const omitted = rows.reduce((sum, row) => sum + row.aggregation.omittedPointCount, 0);
    const expectedMethod = original <= summary.requestedMaxPoints ? "none" : "time_bucket_envelope_v1";
    if (!methods.has(expectedMethod) || returned > summary.requestedMaxPoints) {
      fail("global sensor/source aggregation budget is invalid");
    }
    if (methods.has("none") && (returned !== original || omitted !== 0)) {
      fail("none aggregation combination must retain all originals");
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
  const keys = value.items.map((item) => [
    item.eventAt,
    item.samplePairId,
    item.sensorId,
    item.pointId,
  ].join("|"));
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
  const assessmentStatus = assessment === null
    ? null
    : assessment.schemaVersion === "1.0"
      ? assessment.status
      : assessment.assessment.status;
  const suppressedNormal = assessmentStatus === "normal"
    && facts.conditionState === "normal"
    && facts.conditionTemporalScope === "none"
    && facts.conditionSource === "none"
    && facts.conditionAsOf === null
    && facts.conditionEpisodeStartedAt === null
    && (['degraded', 'insufficient'].includes(facts.dataTrust)
      || facts.dataAvailability !== "complete");
  if (assessment === null) {
    if (facts.conditionEpisodeStartedAt !== null || facts.conditionSource !== "none") {
      fail("condition evidence requires a returned matching assessment");
    }
  } else if (assessment.schemaVersion === "1.0") {
    assertHistoricalAssessment(assessment);
    if (facts.conditionState !== assessment.status
      || (!suppressedNormal
        && (facts.conditionSource !== "historical_walk_forward"
          || facts.conditionAsOf !== assessment.assessmentAt
          || facts.conditionEpisodeStartedAt !== assessment.persistence.episodeStartedAt))) {
      fail("historical condition facts do not match the assessment");
    }
    if (value.anchor !== null
      && !(value.anchor.pointId === assessment.anchorPointId
        && value.anchor.sensorId === assessment.sensorId
        && value.anchor.operatingCycleId === assessment.operatingCycleId
        && milliseconds(assessment.assessmentAt) <= milliseconds(value.anchor.eventAt))) {
      fail("historical assessment anchor facts are crossed");
    }
  } else if (facts.conditionState !== assessment.assessment.status
    || (!suppressedNormal && facts.conditionSource !== "live_assessment")) {
    fail("live condition facts do not match the assessment");
  } else {
    if (value.anchor === null) fail("live assessment requires an original anchor");
    const windowStart = milliseconds(assessment.window.start);
    const windowEnd = milliseconds(assessment.window.end);
    const windowReceived = milliseconds(assessment.window.receivedAt);
    if (!(windowStart <= windowEnd && windowEnd <= windowReceived)) {
      fail("live assessment window is not chronological");
    }
    if (assessment.window.freshnessMs !== windowReceived - windowEnd) {
      fail("live assessment freshness does not match its window");
    }
    if (milliseconds(assessment.model.trainedUntil) > windowStart) {
      fail("live assessment model was trained after its causal window");
    }
    if (assessment.assetId !== value.assetId
      || assessment.assetId !== value.anchor.assetId
      || assessment.sensorId !== value.anchor.sensorId
      || value.anchor.sourceKind !== "live_collection") {
      fail("live assessment asset, sensor, and anchor are crossed");
    }
    if (assessment.window.receivedAt !== value.anchor.eventAt
      || value.selectedAt !== value.anchor.eventAt) {
      fail("live assessment does not match anchor event and selectedAt");
    }
    if (!suppressedNormal && facts.conditionAsOf !== assessment.window.receivedAt) {
      fail("live conditionAsOf must equal assessment window receivedAt");
    }
    if (facts.conditionEpisodeStartedAt !== null) {
      fail("live v2 assessment cannot invent an episode start");
    }
    const qualityStatus = assessment.quality.status;
    if (qualityStatus === "insufficient_data" && facts.dataTrust !== "insufficient") {
      fail("live assessment quality requires insufficient trust");
    }
    if (qualityStatus === "degraded" && facts.dataTrust === "sufficient") {
      fail("live assessment trust exceeds degraded quality");
    }
    if (facts.dataAvailability !== "complete" && facts.dataTrust === "sufficient") {
      fail("live assessment trust exceeds channel availability");
    }
  }
};

const assessmentSeriesKey = (series) => stableJson([
  series.segmentId,
  series.sensorId,
  series.modelFamily,
  series.modelVersion,
  series.modelHash,
  series.foldId,
  series.foldHash,
  series.reportHash,
  series.scoreSemantics,
  series.trainingWindow,
]);

const ASSESSMENT_BASE_LIMITATIONS = Object.freeze([
  "historical_source_participated_in_baseline_construction_and_evaluation",
  "no_confirmed_failure_labels_available",
  "relative_score_not_failure_probability_confidence_rul_or_diagnosis",
]);
const ASSESSMENT_CANDIDATE_LIMITATIONS = Object.freeze([
  "candidate_not_ground_truth",
  ...ASSESSMENT_BASE_LIMITATIONS,
]);

const assertAssessmentOverview = (value) => {
  const requested = value.requestedRange;
  if (requested.from !== null) timestamp(requested.from, "requestedRange.from");
  if (requested.to !== null) timestamp(requested.to, "requestedRange.to");
  if (requested.from !== null && requested.to !== null
    && milliseconds(requested.from) >= milliseconds(requested.to)) {
    fail("assessment requestedRange must be increasing");
  }

  if (value.effectiveRange !== null) {
    timestamp(value.effectiveRange.from, "effectiveRange.from");
    timestamp(value.effectiveRange.to, "effectiveRange.to");
    if (milliseconds(value.effectiveRange.from) >= milliseconds(value.effectiveRange.to)) {
      fail("assessment effectiveRange must be increasing");
    }
  }

  const seriesIds = new Set();
  const groupKeys = new Set();
  const assessmentIds = new Set();
  const anchorIds = new Set();
  let originalCount = 0;
  let returnedCount = 0;
  let omittedCount = 0;
  let reducedSeriesCount = 0;
  let previousGroupKey = null;

  for (const series of value.series) {
    if (seriesIds.has(series.seriesId)) fail("assessment seriesId must be unique across grouping facts");
    seriesIds.add(series.seriesId);
    const groupKey = assessmentSeriesKey(series);
    if (groupKeys.has(groupKey)) fail("assessment grouping facts must map to exactly one series");
    if (previousGroupKey !== null && groupKey <= previousGroupKey) {
      fail("assessment series must be canonically ordered by grouping facts");
    }
    groupKeys.add(groupKey);
    previousGroupKey = groupKey;

    timestamp(series.trainingWindow.start, "trainingWindow.start");
    timestamp(series.trainingWindow.end, "trainingWindow.end");
    if (milliseconds(series.trainingWindow.start) > milliseconds(series.trainingWindow.end)) {
      fail("assessment trainingWindow must be chronological");
    }
    assertCanonicalStrings(series.limitations, "assessment series limitations");

    const aggregation = series.aggregation;
    if (aggregation.requestedMaxPoints !== value.aggregationSummary.requestedMaxPoints) {
      fail("assessment series budget must match the response budget");
    }
    if (aggregation.returnedAssessmentCount !== series.points.length
      || aggregation.originalAssessmentCount
        !== aggregation.returnedAssessmentCount + aggregation.omittedAssessmentCount) {
      fail("assessment series aggregation counts do not reconcile");
    }
    if ((aggregation.method === "none") !== (aggregation.omittedAssessmentCount === 0)) {
      fail("assessment series aggregation method does not match omissions");
    }
    if (aggregation.method !== "none") reducedSeriesCount += 1;
    originalCount += aggregation.originalAssessmentCount;
    returnedCount += aggregation.returnedAssessmentCount;
    omittedCount += aggregation.omittedAssessmentCount;

    let previousEventAt = null;
    let hasCandidate = false;
    for (const point of series.points) {
      timestamp(point.eventAt, "assessment point eventAt");
      if (milliseconds(series.trainingWindow.end) >= milliseconds(point.eventAt)) {
        fail("assessment series training must end before every scored point");
      }
      if (previousEventAt !== null && point.eventAt <= previousEventAt) {
        fail("assessment series points must be strictly chronological");
      }
      previousEventAt = point.eventAt;
      if (assessmentIds.has(point.assessmentId)) fail("assessmentId must be globally unique");
      if (anchorIds.has(point.anchorPointId)) fail("assessment anchorPointId must be globally unique");
      assessmentIds.add(point.assessmentId);
      anchorIds.add(point.anchorPointId);
      if (point.candidateState === "candidate_not_ground_truth") hasCandidate = true;

      if (value.effectiveRange === null
        || milliseconds(point.eventAt) < milliseconds(value.effectiveRange.from)
        || milliseconds(point.eventAt) >= milliseconds(value.effectiveRange.to)) {
        fail("assessment point falls outside effectiveRange");
      }
      if (requested.from !== null && milliseconds(point.eventAt) < milliseconds(requested.from)) {
        fail("assessment point precedes requestedRange");
      }
      if (requested.to !== null && milliseconds(point.eventAt) >= milliseconds(requested.to)) {
        fail("assessment point reaches or exceeds requestedRange");
      }
    }
    const expectedLimitations = hasCandidate
      ? ASSESSMENT_CANDIDATE_LIMITATIONS
      : ASSESSMENT_BASE_LIMITATIONS;
    if (series.limitations.length !== expectedLimitations.length
      || series.limitations.some((limitation, index) => limitation !== expectedLimitations[index])) {
      fail("assessment series candidate facts and limitations do not match");
    }
  }

  const summary = value.aggregationSummary;
  if (summary.originalAssessmentCount !== originalCount
    || summary.returnedAssessmentCount !== returnedCount
    || summary.omittedAssessmentCount !== omittedCount
    || summary.reducedSeriesCount !== reducedSeriesCount
    || summary.originalAssessmentCount !== value.materialization.assessmentCount
    || summary.returnedAssessmentCount > summary.requestedMaxPoints) {
    fail("assessment overview aggregation counts do not reconcile");
  }
  if (value.materialization.state !== "materialized"
    && (originalCount !== 0 || returnedCount !== 0 || value.effectiveRange !== null)) {
    fail("unmaterialized assessment overview cannot contain score evidence");
  }
};

export function assertTimelineInvariantsV1(value, schemaName = null) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail("timeline payload must be an object");
  assertJsonTree(value);
  let name = schemaName?.replace(TIMELINE_SCHEMA_PREFIX, "") ?? null;
  if (name === null) {
    if (Object.hasOwn(value, "materialization") && Object.hasOwn(value, "series")) {
      name = "timeline-assessment-overview";
    }
    else if (Object.hasOwn(value, "segments")) name = "timeline-overview";
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
  else if (name === "timeline-assessment-overview") assertAssessmentOverview(value);
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
export const assertTimelineAssessmentOverviewV1 = (value) => assertTimelinePayloadV1("timeline-assessment-overview", value);
