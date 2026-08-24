import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { build } from "vite";
import { describe, expect, it } from "vitest";
import {
  assertCollectionPolicyV1,
  assertHistoricalAssessmentV1,
  assertHistoricalSensorReadingV1,
  assertTimelineContextV1,
  assertTimelineDecisionFactsV1,
  assertTimelineEventCandidateV1,
  assertTimelineInvariantsV1,
  assertTimelineOverviewV1,
  assertTimelinePageV1,
  assertTimelinePointV1,
  publicMillisecondSuccessorV1,
} from "./timelineV1.js";

const fixture = (name) => JSON.parse(readFileSync(
  new URL(`../../contracts/timeline/v1/fixtures/${name}`, import.meta.url),
  "utf8",
));

const liveAssessmentContext = () => {
  const point = fixture("live-point.valid.json");
  const at = point.eventAt;
  return {
    schemaVersion: "1.0",
    assetId: "forzy-motor-01",
    selectedAt: at,
    segmentId: "00000000-0000-5000-8000-000000000010",
    anchor: structuredClone(point),
    channels: { s1: structuredClone(point), s2: null },
    assessment: {
      schemaVersion: "2.0",
      assessmentId: "00000000-0000-4000-8000-000000000003",
      assetId: "forzy-motor-01",
      sensorId: "s1",
      window: { start: at, end: at, receivedAt: at, freshnessMs: 0 },
      quality: { status: "ok", flags: [] },
      operatingContext: { state: "steady", estimated: true },
      assessment: {
        status: "watch",
        anomalyScore: 0.1,
        deteriorationScore: 0.2,
        scoreSemantics: "relative_to_historical_baseline_not_failure_probability",
        episodeId: "episode-live-1",
        persistenceSeconds: 5,
      },
      componentTag: null,
      recommendation: null,
      humanValidationRequired: true,
      evidence: [{ id: "ev-1", feature: "temperature", value: 30, unit: "degC" }],
      model: {
        name: "robust-baseline",
        version: "1.0.0",
        configHash: `sha256:${"0".repeat(64)}`,
        trainedUntil: at,
      },
      limitations: [],
    },
    decisionFacts: {
      schemaVersion: "1.0",
      conditionState: "watch",
      conditionTemporalScope: "current",
      conditionAsOf: at,
      conditionEpisodeStartedAt: null,
      conditionSource: "live_assessment",
      collectionState: "received_now",
      collectionExpectation: "expected_now",
      dataAvailability: "partial",
      dataFreshness: "fresh",
      dataTrust: "degraded",
    },
    provenance: {
      pointSourceKind: "live_collection",
      pointSourceSystem: "forzy-api",
      activeHistoricalBatchId: null,
      collectionPolicyId: "forzy-live-window-v1",
      assessmentSource: "live_assessment",
    },
    capabilities: {
      historicalNavigation: false,
      pairedChannels: false,
      causalAssessment: true,
      baselineComparison: true,
      previousCycleComparison: false,
    },
    limitations: [],
  };
};

const degradedNormalContext = () => {
  const payload = liveAssessmentContext();
  Object.assign(payload.assessment.assessment, {
    status: "normal",
    episodeId: null,
    persistenceSeconds: 0,
  });
  Object.assign(payload.decisionFacts, {
    conditionState: "normal",
    conditionTemporalScope: "none",
    conditionAsOf: null,
    conditionEpisodeStartedAt: null,
    conditionSource: "none",
  });
  payload.provenance.assessmentSource = "none";
  return payload;
};

const validCases = [
  ["historical-reading.valid.json", assertHistoricalSensorReadingV1],
  ["live-point.valid.json", assertTimelinePointV1],
  ["historical-assessment.valid.json", assertHistoricalAssessmentV1],
  ["collection-policy.valid.json", assertCollectionPolicyV1],
  ["event-candidate-historical.valid.json", assertTimelineEventCandidateV1],
  ["event-candidate-live.valid.json", assertTimelineEventCandidateV1],
  ["overview-unified.valid.json", assertTimelineOverviewV1],
  ["overview-live-only.valid.json", assertTimelineOverviewV1],
  ["page.valid.json", assertTimelinePageV1],
  ["context-missing-channel.valid.json", assertTimelineContextV1],
  ["context-historical-candidate.valid.json", assertTimelineContextV1],
  ["context-historical-gap.valid.json", assertTimelineContextV1],
];

const reject = (validator, payload) => expect(() => validator(payload)).toThrow();

const policyHash = (payload) => {
  const selected = Object.fromEntries([
    "activeWeekdays",
    "assetId",
    "collectionPolicyId",
    "gapThresholdSeconds",
    "pollIntervalSeconds",
    "schemaVersion",
    "timezone",
    "windowEndLocal",
    "windowStartLocal",
  ].map((key) => [key, payload[key]]));
  const canonical = JSON.stringify(selected, Object.keys(selected).sort());
  return `sha256:${createHash("sha256").update(canonical, "utf8").digest("hex")}`;
};

const uuid5Url = (name) => {
  const namespace = Buffer.from("6ba7b8119dad11d180b400c04fd430c8", "hex");
  const bytes = createHash("sha1").update(namespace).update(name, "utf8").digest().subarray(0, 16);
  bytes[6] = (bytes[6] & 0x0f) | 0x50;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

const candidateUuid5 = (payload) => uuid5Url([
  "timeline-event-candidate-v1",
  payload.sourceKind,
  payload.batchId ?? "none",
  payload.anchorPointId,
  payload.modelFamily,
  payload.modelVersion,
  payload.foldId ?? "none",
].join("|"));

const gapUuid5 = (gap) => uuid5Url([
  "timeline-gap-v1",
  gap.gapType,
  gap.leftSegmentId ?? "none",
  gap.rightSegmentId ?? "none",
  gap.startAt,
  gap.endAt,
  gap.ruleVersion,
].join("|"));

const operatingCycles = (count = 204) => {
  const cycles = [];
  for (let index = 0; index < count; index += 1) {
    const cycleId = `00000000-0000-5000-8000-${(index + 256).toString(16).padStart(12, "0")}`;
    cycles.push({
      operatingCycleId: cycleId,
      sourceKind: "historical_archive",
      batchId: `sha256:${"a".repeat(64)}`,
      startAt: `2026-08-22T${Math.floor(index / 60).toString().padStart(2, "0")}:${(index % 60).toString().padStart(2, "0")}:00.000Z`,
      endAt: `2026-08-22T${Math.floor(index / 60).toString().padStart(2, "0")}:${(index % 60).toString().padStart(2, "0")}:00.000Z`,
      durationSeconds: 0,
      totalPoints: 2,
      sensorCounts: { s1: 1, s2: 1 },
      candidateCount: 0,
      gapBeforeSeconds: index === 0 ? null : 60,
      previousOperatingCycleId: index === 0 ? null : cycles.at(-1).operatingCycleId,
      assumptions: [],
    });
  }
  return cycles;
};

describe("Timeline v1 composed runtime contract", () => {
  it("bundles the public validator without Node built-ins while preserving pinned hashes", async () => {
    const policy = fixture("collection-policy.valid.json");
    const candidate = fixture("event-candidate-live.valid.json");
    const overview = fixture("overview-unified.valid.json");
    expect(policy.configurationHash)
      .toBe("sha256:89bde17193c7a34c80d48828f4e61fc5802caa92169d83f8a9fd8e4c282b1bce");
    expect(candidate.candidateId).toBe("7e36965b-20e4-5ce7-a37a-85357559f763");
    expect(overview.gaps[0].gapId).toBe("3374ee11-91f2-528d-b23e-198ee91b3d70");
    expect(() => assertCollectionPolicyV1(policy)).not.toThrow();
    expect(() => assertTimelineEventCandidateV1(candidate)).not.toThrow();
    expect(() => assertTimelineOverviewV1(overview)).not.toThrow();

    const result = await build({
      configFile: false,
      logLevel: "silent",
      build: {
        write: false,
        lib: {
          entry: fileURLToPath(new URL("./timelineV1.js", import.meta.url)),
          formats: ["es"],
          fileName: "timeline-v1-browser",
        },
      },
    });
    const outputs = (Array.isArray(result) ? result : [result])
      .flatMap((entry) => entry.output);
    const chunks = outputs.filter((entry) => entry.type === "chunk");
    expect(chunks.length).toBeGreaterThan(0);
    expect(chunks.flatMap((chunk) => chunk.imports).some((specifier) => specifier.startsWith("node:")))
      .toBe(false);
    const bundledCode = chunks.map((chunk) => chunk.code).join("\n");
    expect(bundledCode).not.toMatch(/node:(?:crypto|fs)|__vite-browser-external|\bBuffer\b/);
  }, 15_000);

  it.each(validCases)("accepts and byte-stably revalidates %s", (name, validate) => {
    const payload = fixture(name);
    expect(validate(payload)).toBe(payload);
    const first = JSON.stringify(payload);
    const reparsed = JSON.parse(first);
    expect(validate(reparsed)).toBe(reparsed);
    expect(JSON.stringify(reparsed)).toBe(first);
  });

  it.each([
    ["pointId", 123],
    ["pointId", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"],
    ["eventAt", 1_724_329_600],
    ["eventAt", "2026-08-22T12:00:00+00:00"],
    ["eventAt", "2026-08-22T12:00:00.123456Z"],
    ["eventAt", "2026-02-29T12:00:00.123Z"],
    ["eventAt", "0000-01-01T00:00:00.000Z"],
  ])("rejects noncanonical point %s=%j", (field, value) => {
    const payload = fixture("live-point.valid.json");
    payload[field] = value;
    reject(assertTimelinePointV1, payload);
  });

  it.each(["1.1", true, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    "rejects non-strict measurement %j",
    (value) => {
      const payload = fixture("historical-reading.valid.json");
      payload.measurements.temperature.value = value;
      reject(assertHistoricalSensorReadingV1, payload);
    },
  );

  it("parses every public calendar timestamp after structural validation", () => {
    const reading = fixture("historical-reading.valid.json");
    reading.provenance.ingestedAt = "2026-02-29T12:00:00.000Z";
    reject(assertHistoricalSensorReadingV1, reading);

    const archivePoint = fixture("context-historical-candidate.valid.json").anchor;
    archivePoint.eventAt = "2026-02-29T12:00:00.000Z";
    reject(assertTimelinePointV1, archivePoint);

    const overview = fixture("overview-live-only.valid.json");
    overview.requestedRange.from = "2026-02-29T12:00:00.000Z";
    reject(assertTimelineOverviewV1, overview);

    const facts = liveAssessmentContext().decisionFacts;
    facts.conditionAsOf = "2026-02-29T12:00:00.000Z";
    reject(assertTimelineDecisionFactsV1, facts);

    const context = fixture("context-historical-gap.valid.json");
    context.selectedAt = "2026-02-29T12:00:00.000Z";
    reject(assertTimelineContextV1, context);
  });

  it("rejects nested extra keys in every public family", () => {
    const mutations = [
      ["historical-reading.valid.json", assertHistoricalSensorReadingV1, (p) => { p.measurements.temperature.unexpected = true; }],
      ["historical-assessment.valid.json", assertHistoricalAssessmentV1, (p) => { p.quality.unexpected = true; }],
      ["overview-unified.valid.json", assertTimelineOverviewV1, (p) => { p.requestedRange.unexpected = true; }],
      ["overview-unified.valid.json", assertTimelineOverviewV1, (p) => { p.aggregationSummary.unexpected = true; }],
      ["overview-unified.valid.json", assertTimelineOverviewV1, (p) => { p.segments[0].sensorCounts.unexpected = true; }],
      ["context-missing-channel.valid.json", assertTimelineContextV1, (p) => { p.provenance.unexpected = true; }],
      ["context-missing-channel.valid.json", assertTimelineContextV1, (p) => { p.capabilities.unexpected = true; }],
    ];
    for (const [name, validate, mutate] of mutations) {
      const payload = fixture(name);
      mutate(payload);
      reject(validate, payload);
    }
  });

  it("rejects source and provenance crossings", () => {
    reject(assertTimelinePointV1, fixture("source-provenance-cross.invalid.json"));
  });

  it("rejects historical assessment chronology, persistence, score, and evidence crossings", () => {
    reject(assertHistoricalAssessmentV1, fixture("historical-assessment-future.invalid.json"));
    reject(assertHistoricalAssessmentV1, fixture("historical-assessment-episode.invalid.json"));

    const persistence = fixture("historical-assessment.valid.json");
    persistence.persistence.persistenceSeconds = 899;
    reject(assertHistoricalAssessmentV1, persistence);

    const score = fixture("historical-assessment.valid.json");
    score.status = "insufficient_data";
    score.anomalyScore = 0.1;
    score.deteriorationScore = null;
    score.persistence = {
      episodeId: null,
      episodeStartedAt: null,
      persistenceSeconds: 0,
      persistenceCount: 0,
    };
    reject(assertHistoricalAssessmentV1, score);

    const evidence = fixture("historical-assessment.valid.json");
    evidence.evidence = [{
      id: "ev-temperature",
      feature: "temperature",
      value: 30,
      unit: "degC",
      baseline: 29,
      deviation: 1,
      direction: "up",
      windowSeconds: 60,
      unexpected: true,
    }];
    reject(assertHistoricalAssessmentV1, evidence);
  });

  it("composes policy hash, validity, exact weekday order, and versioned identity", () => {
    reject(assertCollectionPolicyV1, fixture("collection-policy-hash.invalid.json"));

    const future = fixture("collection-policy.valid.json");
    future.collectionPolicyId = "forzy-live-window-v2";
    future.effectiveFrom = "2026-09-01T00:00:00.000Z";
    future.configurationHash = policyHash(future);
    expect(() => assertCollectionPolicyV1(future)).not.toThrow();

    const invalidInterval = structuredClone(future);
    invalidInterval.effectiveTo = "2026-08-31T23:59:59.999Z";
    reject(assertCollectionPolicyV1, invalidInterval);

    const reordered = fixture("collection-policy.valid.json");
    reordered.activeWeekdays = ["wednesday", "tuesday", "monday"];
    reordered.configurationHash = policyHash(reordered);
    reject(assertCollectionPolicyV1, reordered);
  });

  it("parses effectiveFrom even when an open-ended policy has no effectiveTo", () => {
    const policy = fixture("collection-policy.valid.json");
    policy.effectiveFrom = "2026-02-29T00:00:00.000Z";
    expect(
      () => assertCollectionPolicyV1(policy),
      "RED:FR1:I2:open-ended-policy-skips-effective-from-calendar",
    ).toThrow();
  });

  it("rejects candidate source, quality, trust, model, and episode crossings", () => {
    reject(assertTimelineEventCandidateV1, fixture("event-candidate-cross.invalid.json"));
    reject(assertTimelineEventCandidateV1, fixture("event-candidate-episode.invalid.json"));

    const flags = fixture("event-candidate-live.valid.json");
    flags.quality.flags = ["z_flag", "a_flag"];
    reject(assertTimelineEventCandidateV1, flags);

    const trust = fixture("event-candidate-live.valid.json");
    trust.quality.status = "insufficient_data";
    trust.dataTrust = "sufficient";
    reject(assertTimelineEventCandidateV1, trust);

    const model = fixture("event-candidate-live.valid.json");
    model.modelVersion = "";
    reject(assertTimelineEventCandidateV1, model);
  });

  it("freezes the candidate UUIDv5 name identity", () => {
    for (const name of [
      "event-candidate-historical.valid.json",
      "event-candidate-live.valid.json",
    ]) {
      const payload = fixture(name);
      expect(payload.candidateId, "RED:A1R:deterministic-candidate-uuid5-missing")
        .toBe(candidateUuid5(payload));

      const crossed = structuredClone(payload);
      crossed.candidateId = "00000000-0000-5000-8000-000000000099";
      reject(assertTimelineEventCandidateV1, crossed);
    }
  });

  it("freezes a four-segment/three-gap globally budgeted overview", () => {
    const payload = fixture("overview-unified.valid.json");
    expect(payload.gaps.length, "RED:A1R:multi-segment-three-gap-fixture-missing").toBeGreaterThanOrEqual(3);
    expect(payload.segments.length).toBeGreaterThanOrEqual(4);
    expect(payload.series.reduce((sum, row) => sum + row.aggregation.returnedPointCount, 0)).toBeLessThanOrEqual(40);
    expect(() => assertTimelineOverviewV1(payload)).not.toThrow();

    const perSegment = structuredClone(payload);
    const templatePoint = structuredClone(payload.series[0].points[0]);
    for (const row of perSegment.series) {
      row.aggregation.originalPointCount = 20;
      row.aggregation.returnedPointCount = 20;
      row.aggregation.omittedPointCount = 0;
      row.points = Array.from({ length: 20 }, () => structuredClone(templatePoint));
    }
    Object.assign(perSegment.aggregationSummary, {
      originalPointCount: 80,
      returnedPointCount: 80,
      omittedPointCount: 0,
    });
    reject(assertTimelineOverviewV1, perSegment);

    const mixedMethod = structuredClone(payload);
    mixedMethod.series[0].aggregation.method = "none";
    reject(assertTimelineOverviewV1, mixedMethod);

    const wrongReduced = structuredClone(payload);
    wrongReduced.aggregationSummary.reducedSeriesCount = 0;
    reject(assertTimelineOverviewV1, wrongReduced);

    const wrongCeiling = structuredClone(payload);
    wrongCeiling.series[0].aggregation.requestedMaxPoints = 41;
    reject(assertTimelineOverviewV1, wrongCeiling);

    const reversedSeries = structuredClone(payload);
    reversedSeries.series.reverse();
    reject(assertTimelineOverviewV1, reversedSeries);

    const reversedPoints = structuredClone(payload);
    reversedPoints.series[0].points.reverse();
    reject(assertTimelineOverviewV1, reversedPoints);
  });

  it("requires method none to retain every original point", () => {
    const payload = fixture("overview-unified.valid.json");
    payload.aggregationSummary.requestedMaxPoints = 100;
    payload.aggregationSummary.reducedSeriesCount = 0;
    for (const row of payload.series) {
      row.aggregation.requestedMaxPoints = 100;
      row.aggregation.method = "none";
    }
    expect(
      () => assertTimelineOverviewV1(payload),
      "RED:FR1:I3:none-method-retains-omissions",
    ).toThrow();
  });

  it("requires every nonzero segment sensor group including zero-selected series", () => {
    const payload = fixture("overview-unified.valid.json");
    const omitted = payload.series.pop();
    expect(omitted.aggregation.originalPointCount).toBeGreaterThan(0);
    expect(omitted.points).toHaveLength(0);
    const segments = new Map(payload.segments.map((segment) => [segment.segmentId, segment]));
    for (const row of payload.series) {
      row.aggregation.originalPointCount = 15;
      row.aggregation.omittedPointCount = 15 - row.aggregation.returnedPointCount;
      const segment = segments.get(row.segmentId);
      segment.sensorCounts.s1 = 15;
      segment.totalPoints = 15;
    }
    Object.assign(payload.aggregationSummary, {
      originalPointCount: 45,
      returnedPointCount: 4,
      omittedPointCount: 41,
      reducedSeriesCount: 3,
    });
    expect(
      () => assertTimelineOverviewV1(payload),
      "RED:FR1:I3:nonzero-zero-selected-group-may-be-omitted",
    ).toThrow();
  });

  it("rejects segment, gap, sensor-membership, and local count crossings", () => {
    const crossed = fixture("overview-unified.valid.json");
    crossed.segments[0].collectionPolicyId = "forzy-live-window-v1";
    reject(assertTimelineOverviewV1, crossed);

    const count = fixture("overview-unified.valid.json");
    count.segments[0].sensorCounts = { s1: 0, s2: 0 };
    reject(assertTimelineOverviewV1, count);

    const membership = fixture("overview-unified.valid.json");
    membership.series[0].sensorId = "s2";
    reject(assertTimelineOverviewV1, membership);

    const assumptions = fixture("overview-unified.valid.json");
    assumptions.segments[0].assumptions = ["same", "same"];
    reject(assertTimelineOverviewV1, assumptions);

    const gap = fixture("overview-unified.valid.json");
    gap.gaps = [{
      gapId: "00000000-0000-5000-8000-000000000020",
      leftSegmentId: gap.segments[0].segmentId,
      rightSegmentId: gap.segments[1].segmentId,
      startAt: "2026-08-22T12:00:00.000Z",
      endAt: "2026-08-22T12:01:00.000Z",
      gapType: "archive_sampling_gap",
      durationSeconds: 59,
      ruleVersion: "timeline-gap-v1",
      messageCode: "timeline_gap_expected_idle",
    }];
    gap.gaps[0].gapId = gapUuid5(gap.gaps[0]);
    reject(assertTimelineOverviewV1, gap);
  });

  it("freezes the gap UUIDv5 name identity", () => {
    const payload = fixture("overview-unified.valid.json");
    for (const gap of payload.gaps) {
      expect(gap.gapId, "RED:A1R:deterministic-gap-uuid5-missing").toBe(gapUuid5(gap));
    }

    const crossed = structuredClone(payload);
    crossed.gaps[0].gapId = "00000000-0000-5000-8000-000000000099";
    reject(assertTimelineOverviewV1, crossed);
  });

  it("accepts 204 ordered cycles and rejects count, duration, predecessor, and order mutations", () => {
    const payload = fixture("overview-unified.valid.json");
    payload.operatingCycles = operatingCycles();
    expect(payload.operatingCycles).toHaveLength(204);
    expect(() => assertTimelineOverviewV1(payload)).not.toThrow();

    const invalids = [];
    const count = structuredClone(payload);
    count.operatingCycles[1].sensorCounts.s2 = 0;
    invalids.push(count);
    const duration = structuredClone(payload);
    duration.operatingCycles[1].durationSeconds = 1;
    invalids.push(duration);
    const predecessor = structuredClone(payload);
    predecessor.operatingCycles[2].previousOperatingCycleId = predecessor.operatingCycles[0].operatingCycleId;
    invalids.push(predecessor);
    const order = structuredClone(payload);
    [order.operatingCycles[0], order.operatingCycles[1]] = [order.operatingCycles[1], order.operatingCycles[0]];
    invalids.push(order);
    invalids.forEach((value) => reject(assertTimelineOverviewV1, value));
  });

  it("freezes missing-channel, historical-gap, matching-assessment, and provenance branches", () => {
    const missing = fixture("context-missing-channel.valid.json");
    expect(
      Object.values(missing.channels).filter((point) => point !== null),
      "RED:A1R:missing-channel-fixture-does-not-prove-nullability",
    ).toHaveLength(1);

    const candidate = fixture("context-historical-candidate.valid.json");
    expect(candidate.assessment, "RED:A1R:matching-causal-assessment-missing").not.toBeNull();
    expect(() => assertTimelineContextV1(candidate)).not.toThrow();

    reject(assertTimelineContextV1, fixture("context-decision-facts-cross.invalid.json"));

    const provenance = fixture("context-missing-channel.valid.json");
    provenance.provenance.pointSourceKind = "live_collection";
    provenance.provenance.pointSourceSystem = "forzy-csv";
    reject(assertTimelineContextV1, provenance);

    const gap = fixture("context-historical-gap.valid.json");
    gap.channels.s1 = fixture("live-point.valid.json");
    reject(assertTimelineContextV1, gap);
  });

  it("composes child invariants through every aggregate root", () => {
    const page = fixture("page.valid.json");
    const point = fixture("live-point.valid.json");
    point.provenance.receivedAt = "2026-08-22T12:00:00.124Z";
    page.items = [point];
    reject(assertTimelinePageV1, page);

    const overview = fixture("overview-unified.valid.json");
    const candidate = fixture("event-candidate-live.valid.json");
    candidate.candidateId = "00000000-0000-5000-8000-000000000099";
    overview.eventCandidates = [candidate];
    reject(assertTimelineOverviewV1, overview);

    const context = fixture("context-historical-candidate.valid.json");
    context.assessment.persistence.persistenceSeconds = 899;
    reject(assertTimelineContextV1, context);
  });

  it("preserves explicit range bounds while availability remains global", () => {
    const bounded = fixture("overview-unified.valid.json");
    bounded.requestedRange = {
      from: "2026-08-22T11:59:00.000Z",
      to: "2026-08-22T12:04:00.000Z",
    };
    bounded.effectiveRange = structuredClone(bounded.requestedRange);
    expect(() => assertTimelineOverviewV1(bounded)).not.toThrow();

    const crossed = structuredClone(bounded);
    crossed.effectiveRange.to = bounded.availableRange.to;
    reject(assertTimelineOverviewV1, crossed);

    const noResult = fixture("overview-live-only.valid.json");
    noResult.requestedRange = {
      from: "2026-08-22T13:00:00.000Z",
      to: "2026-08-22T14:00:00.000Z",
    };
    noResult.availableRange = {
      from: "2026-08-22T12:00:00.000Z",
      to: "2026-08-22T12:00:00.124Z",
    };
    expect(() => assertTimelineOverviewV1(noResult)).not.toThrow();
  });

  it("requires one metric and one series per returned group", () => {
    const mixedMetric = fixture("overview-unified.valid.json");
    mixedMetric.series[1].metric = "vibrationAcceleration";
    reject(assertTimelineOverviewV1, mixedMetric);

    const duplicateGroup = fixture("overview-unified.valid.json");
    duplicateGroup.series.push(structuredClone(duplicateGroup.series.at(-1)));
    duplicateGroup.aggregationSummary.originalPointCount += 11;
    duplicateGroup.aggregationSummary.omittedPointCount += 11;
    duplicateGroup.aggregationSummary.reducedSeriesCount += 1;
    reject(assertTimelineOverviewV1, duplicateGroup);
  });

  it("enforces cycle gaps and candidate-to-cycle graph references", () => {
    const payload = fixture("overview-unified.valid.json");
    payload.operatingCycles = operatingCycles();

    const badGap = structuredClone(payload);
    badGap.operatingCycles[1].gapBeforeSeconds = 59;
    reject(assertTimelineOverviewV1, badGap);

    const unknownCycle = structuredClone(payload);
    unknownCycle.eventCandidates = [fixture("event-candidate-historical.valid.json")];
    reject(assertTimelineOverviewV1, unknownCycle);
  });

  it("admits archive page items only from the active batch", () => {
    const page = fixture("page.valid.json");
    const archivePoint = fixture("context-historical-candidate.valid.json").anchor;
    page.items = [archivePoint];
    reject(assertTimelinePageV1, page);

    page.activeHistoricalBatchId = archivePoint.provenance.batchId;
    expect(() => assertTimelinePageV1(page)).not.toThrow();
  });

  it("coheres context channel availability, pair identity, navigation, and provenance", () => {
    const missing = fixture("context-missing-channel.valid.json");
    const wrongAvailability = structuredClone(missing);
    wrongAvailability.decisionFacts.dataAvailability = "complete";
    reject(assertTimelineContextV1, wrongAvailability);

    const paired = fixture("context-historical-candidate.valid.json");
    const crossedPair = structuredClone(paired);
    crossedPair.channels.s2.samplePairId = "00000000-0000-5000-8000-000000000099";
    reject(assertTimelineContextV1, crossedPair);

    const noNavigation = structuredClone(paired);
    noNavigation.capabilities.historicalNavigation = false;
    reject(assertTimelineContextV1, noNavigation);

    const wrongBatch = structuredClone(paired);
    wrongBatch.provenance.activeHistoricalBatchId = `sha256:${"9".repeat(64)}`;
    reject(assertTimelineContextV1, wrongBatch);
  });

  it("resolves the unchanged v2 assessment schema through timeline context", () => {
    const payload = liveAssessmentContext();
    expect(assertTimelineContextV1(payload)).toBe(payload);
    expect(JSON.stringify(JSON.parse(JSON.stringify(payload)))).toBe(JSON.stringify(payload));
  });

  it("retains a degraded normal assessment while suppressing temporal condition claims", () => {
    const payload = degradedNormalContext();
    expect(
      () => assertTimelineContextV1(payload),
      "RED:FR1:I4:degraded-normal-assessment-is-unrepresentable",
    ).not.toThrow();
  });

  it("rejects near-neighbors of degraded normal suppression", () => {
    const watch = degradedNormalContext();
    watch.assessment.assessment.status = "watch";
    reject(assertTimelineContextV1, watch);

    const wrongLabel = degradedNormalContext();
    wrongLabel.decisionFacts.conditionState = "unknown";
    reject(assertTimelineContextV1, wrongLabel);

    const unsuppressed = degradedNormalContext();
    Object.assign(unsuppressed.decisionFacts, {
      conditionTemporalScope: "current",
      conditionAsOf: unsuppressed.selectedAt,
      conditionSource: "live_assessment",
    });
    unsuppressed.provenance.assessmentSource = "live_assessment";
    reject(assertTimelineContextV1, unsuppressed);

    const sufficientComplete = degradedNormalContext();
    const second = structuredClone(sufficientComplete.channels.s1);
    second.sensorId = "s2";
    second.pointId = "00000000-0000-5000-8000-000000000005";
    second.provenance.readingId = second.pointId;
    sufficientComplete.channels.s2 = second;
    sufficientComplete.decisionFacts.dataAvailability = "complete";
    sufficientComplete.decisionFacts.dataTrust = "sufficient";
    sufficientComplete.capabilities.pairedChannels = true;
    reject(assertTimelineContextV1, sufficientComplete);
  });

  it.each([
    ["wrong_sensor", (payload) => { payload.assessment.sensorId = "s2"; }],
    ["condition_as_of", (payload) => {
      payload.decisionFacts.conditionAsOf = "2026-08-22T12:00:00.124Z";
    }],
    ["window_order", (payload) => {
      payload.assessment.window.start = "2026-08-22T12:00:00.124Z";
    }],
    ["anchor_received_at", (payload) => {
      payload.assessment.window.receivedAt = "2026-08-22T12:00:00.124Z";
      payload.decisionFacts.conditionAsOf = "2026-08-22T12:00:00.124Z";
      payload.selectedAt = "2026-08-22T12:00:00.124Z";
      payload.assessment.window.freshnessMs = 1;
    }],
    ["selected_at", (payload) => { payload.selectedAt = "2026-08-22T12:00:00.124Z"; }],
    ["invented_episode_start", (payload) => {
      payload.decisionFacts.conditionEpisodeStartedAt = payload.decisionFacts.conditionAsOf;
    }],
    ["freshness_arithmetic", (payload) => { payload.assessment.window.freshnessMs = 1; }],
    ["future_trained_model", (payload) => {
      payload.assessment.model.trainedUntil = "2026-08-22T12:00:00.124Z";
    }],
    ["quality_trust", (payload) => {
      payload.assessment.quality.status = "insufficient_data";
    }],
  ])("rejects noncausal live v2 assessment mutation %s", (mutation, mutate) => {
    const payload = liveAssessmentContext();
    mutate(payload);
    expect(
      () => assertTimelineContextV1(payload),
      `RED:FR1:I5:live-assessment-causality:${mutation}`,
    ).toThrow();
  });

  it("matches live v2 assessment asset before structural validation", () => {
    const payload = liveAssessmentContext();
    payload.assessment.assetId = "crossed-asset";
    expect(
      () => assertTimelineInvariantsV1(payload, "timeline-context"),
      "RED:FR1:I5:live-assessment-causality:crossed_asset",
    ).toThrow();
  });

  it("rejects historical and unavailable decision-fact crossings", () => {
    const historical = fixture("context-historical-candidate.valid.json").decisionFacts;
    historical.dataFreshness = "fresh";
    reject(assertTimelineDecisionFactsV1, historical);

    const unavailable = {
      schemaVersion: "1.0",
      conditionState: "watch",
      conditionTemporalScope: "current",
      conditionAsOf: "2026-08-22T12:00:00.000Z",
      conditionEpisodeStartedAt: null,
      conditionSource: "live_assessment",
      collectionState: "unavailable",
      collectionExpectation: "not_applicable",
      dataAvailability: "unavailable",
      dataFreshness: "unknown",
      dataTrust: "insufficient",
    };
    reject(assertTimelineDecisionFactsV1, unavailable);
  });

  it("enforces page total order and duplicate rejection", () => {
    const point = fixture("live-point.valid.json");
    const later = structuredClone(point);
    later.pointId = "00000000-0000-5000-8000-000000000005";
    later.eventAt = "2026-08-22T12:00:00.124Z";
    later.provenance.readingId = later.pointId;
    later.provenance.scheduledAt = later.eventAt;
    later.provenance.receivedAt = later.eventAt;
    const page = fixture("page.valid.json");
    page.items = [point, later];
    expect(() => assertTimelinePageV1(page)).not.toThrow();

    const reversed = structuredClone(page);
    reversed.items.reverse();
    reject(assertTimelinePageV1, reversed);
    const duplicate = structuredClone(page);
    duplicate.items = [point, structuredClone(point)];
    reject(assertTimelinePageV1, duplicate);
  });

  it("uses only the literal public-millisecond successor table", () => {
    const cases = fixture("public-millisecond-successor-v1-cases.json");
    cases.valid.forEach((entry) => expect(publicMillisecondSuccessorV1(entry.input)).toBe(entry.expected));
    expect(() => publicMillisecondSuccessorV1(cases.invalid[0].input)).toThrow("timeline_invalid_public_millisecond");
    expect(() => publicMillisecondSuccessorV1(cases.invalid[1].input)).toThrow("timeline_range_overflow");
  });
});
