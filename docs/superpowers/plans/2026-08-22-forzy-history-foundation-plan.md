# Forzy Historical Foundation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` for every task and `superpowers:verification-before-completion` before claiming this plan complete.

**Goal:** Persist the exact Forzy CSV as an immutable, auditable historical batch in SQLite and PostgreSQL, with strict cross-runtime contracts, deterministic identities, safe staging/activation, and no effect on live TwinOps state.

**Architecture:** Keep archive ingestion outside the existing live telemetry repository. A registered byte-level profile prepares one immutable batch; a new historical repository writes it atomically as `staged`; a separate compare-and-swap command promotes it to `active`. Migration is an explicit administrative operation, never an accidental PostgreSQL cold-start side effect. Public timeline types are frozen here so the following API plan can consume them without changing persistence contracts.

**Tech Stack:** Python 3.12, Pydantic 2, SQLite, PostgreSQL/psycopg 3, FastAPI contract conventions, JSON Schema draft-07, JavaScript/AJV, pytest 8, Vitest.

**Planning lineage:** `globalBaseCommit=4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e` in `.worktrees/real-twinops-integration`.

**Execution starting point:** `phaseStartCommit` is the exact clean, independently reviewed E1 bootstrap SHA delivered by the execution-index integrator handoff. It must descend from `globalBaseCommit`, contain the committed ledger/verifier and frontend-only bundled-browser bootstrap, and equal `HEAD` before A changes anything. A never starts directly from `globalBaseCommit` and never reconstructs or skips E1.

**Spec:** [Unified History and Interactive Twin Design](../specs/2026-08-22-unified-history-interactive-twin-design.md)

---

## Global Constraints

Every executable Python block below is self-contained: it resolves the shared Python 3.12 virtual environment to an absolute path, sets `PYTHONPATH` to this worktree, and invokes that absolute executable rather than relying on a prior alias or shell setup. Every PowerShell block runs in the same checked Windows PowerShell 5.1 process. A fresh process must rerun the prelude below before executing any later block. Native commands never become terminating errors automatically in PowerShell 5.1, so capture `$LASTEXITCODE` immediately and admit only the explicitly allowed code. Every intentional RED test must exit exactly `1`, contain its task's exact `RED:<plan><task>:<reason>` assertion token, and contain neither a pytest/Vitest collection error nor `INTERNALERROR`; exit `2`, `4`, `5`, `127`, `128`, or any other infrastructure outcome is blocking. Run this initial preflight from the worktree root:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert-NativeExit {
  param(
    [Parameter(Mandatory=$true)][int]$ExitCode,
    [Parameter(Mandatory=$true)][string]$Label,
    [int[]]$Allowed = @(0)
  )
  if ($Allowed -notcontains $ExitCode) { throw "$Label exited $ExitCode" }
}
function Assert-ExactStringListV1 {
  param(
    [Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$Expected,
    [Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$Actual,
    [Parameter(Mandatory=$true)][string]$Label
  )
  $expectedList = @(@($Expected) | Sort-Object)
  $actualList = @(@($Actual) | Sort-Object)
  if ($expectedList.Count -ne $actualList.Count) { throw "$Label count mismatch" }
  for ($index = 0; $index -lt $expectedList.Count; $index++) {
    if ($expectedList[$index] -cne $actualList[$index]) { throw "$Label mismatch" }
  }
}
function Assert-ExactStagedScopeV1 {
  param(
    [Parameter(Mandatory=$true)][string[]]$Expected,
    [Parameter(Mandatory=$true)][string]$Label
  )
  $rawActual = @(git diff --cached --name-only)
  $nativeExit = $LASTEXITCODE
  Assert-NativeExit $nativeExit "$Label staged path read"
  Assert-ExactStringListV1 -Expected $Expected -Actual @($rawActual) -Label "$Label staged scope"
  git diff --cached --check
  Assert-NativeExit $LASTEXITCODE "$Label staged diff check"
}
function Get-WorktreeRelativePathV1 {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$Child
  )
  $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd([char[]]@('\','/'))
  $childFull = [IO.Path]::GetFullPath($Child)
  $rootPrefix = $rootFull + [IO.Path]::DirectorySeparatorChar
  if (-not $childFull.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'path escaped worktree root' }
  $relative = $childFull.Substring($rootPrefix.Length).Replace('\','/')
  if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative) -or $relative -eq '..' -or $relative.StartsWith('../')) { throw 'invalid worktree-relative path' }
  return $relative
}
$worktreeRoot = (Resolve-Path '.').Path
$globalBaseCommit = '4d1cc82fce1b147a3e50315fafdcd37d90dc9a7e'
$phaseStartCommit = [string]$env:PHASE_START_COMMIT
if ($phaseStartCommit -notmatch '^[0-9a-f]{40}$' -or $env:E1_REVIEWED_COMMIT -ne $phaseStartCommit -or $env:E1_REVIEW_VERDICT -ne 'PASS') { throw 'reviewed E1 phaseStartCommit handoff required' }
$headCommit = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $headCommit -ne $phaseStartCommit) { throw 'A must start at exact E1 phaseStartCommit' }
git merge-base --is-ancestor $globalBaseCommit $phaseStartCommit
if ($LASTEXITCODE -ne 0) { throw 'E1 phaseStartCommit does not descend from globalBaseCommit' }
$dirtyBeforeA = @(git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $dirtyBeforeA.Count -ne 0) { throw 'A requires a clean E1 worktree' }
$e1BootstrapPaths = @(
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md',
  'scripts/verify_unified_acceptance.py',
  'services/twinops/tests/test_verify_unified_acceptance.py',
  'playwright.twin.config.js',
  'tests/e2e/playwright-twin-config.test.js'
)
foreach ($path in $e1BootstrapPaths) {
  git cat-file -e "$phaseStartCommit`:$path"
  if ($LASTEXITCODE -ne 0) { throw "missing E1 bootstrap blob: $path" }
  $commitBlob = (git rev-parse "$phaseStartCommit`:$path").Trim()
  if ($LASTEXITCODE -ne 0) { throw "cannot resolve E1 bootstrap blob: $path" }
  $workingBlob = (git hash-object --path=$path -- $path).Trim()
  if ($LASTEXITCODE -ne 0 -or $workingBlob -ne $commitBlob) { throw "E1 bootstrap blob mismatch: $path" }
}
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
& $python -c "import sys, twinops, pathlib; assert sys.version_info[:2] == (3, 12); assert pathlib.Path(twinops.__file__).resolve().is_relative_to(pathlib.Path.cwd().resolve())"
if ($LASTEXITCODE -ne 0) { throw 'A Python provenance preflight failed' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'E1 acceptance ledger verification failed' }
```

The assertion must pass before any RED/GREEN evidence is accepted.

The acceptance ledger is a serialized integration resource. Phase workers may produce code, tests, and their strict review report, but only the execution-index integrator with exclusive ownership of `docs/verification/unified-twin-acceptance-v1.json` and its generated Markdown may run ledger mutation commands. The integrator merges one reviewed phase at a time, rechecks the exact code SHA, mutates only that phase/criterion ownership through the CLI, regenerates/verifies Markdown, and commits before admitting the next phase. Parallel A–D workers never edit, merge, or regenerate the shared ledger concurrently.

### Frozen boundaries and evidence

Existing live types used by name below are owned unchanged by the current codebase: `CanonicalSensorReadingV2`, `MeasurementsV2`, and `AssetConditionAssessmentV2` in `contracts/v2_models.py`, `TelemetryRepositoryV2` in `storage/v2_repository.py`, and `HistoricalBatchConflict` in the historical repository error module. The Foundation public contracts are defined literally in the next section; every new internal implementation type is defined in the closed catalog before Task 1.

- Do not loosen `CanonicalSensorReadingV2`; it remains `forzy-live` only.
- Do not write archive rows into `telemetry_samples_v2`, `latest_readings_v2`, `raw_readings_v2`, `collection_attempts_v2`, or `refresh_cycles_v2`.
- Do not change `effective_now`, live health, live sample counts, or refresh outcomes during migration, stage, revalidation, or activation.
- Only the active historical batch is eligible for a public timeline. A staged batch is administrative data.
- The registered profile is `forzy-history-2026-05-19-v1`:
  - file size: `1_096_042` bytes;
  - SHA-256: `f09a6613bf6ba3416555a15de6b381bd842474f5f3f33c20660416c7164f0be4`;
  - UTF-8 without BOM, semicolon delimiter, CRLF only, final CRLF present;
  - three header records followed by exactly `7_183` data records;
  - exactly `14_366` S1/S2 samples and `204` operating cycles at a `15 s` gap boundary;
  - source timestamps have no offset and are interpreted as `America/Sao_Paulo`, while the lexical text is retained.
- The CSV is not copied into the repository, frontend bundle, deploy artifact, HTTP response, or log. The real-file test is opt-in and receives an absolute controller-provided path.
- `batchId` is `sha256:` plus the SHA-256 of canonical JSON containing `assetId`, source SHA, parser version, timezone assumption, and historical contract version. `readingId`, `samplePairId`, `operatingCycleId`, and `pointId` are UUIDv5 values in a named TwinOps namespace.
- The user must authorize preview migration, preview stage, preview activation, production migration, production stage, and production activation separately. This plan creates commands and tests; it does not run any remote command.

## Public shapes frozen by this plan

The schema folder is `contracts/timeline/v1`. Every schema declares `"$schema":"http://json-schema.org/draft-07/schema#"`, a unique stable `$id` under `forzy://contracts/timeline/v1/`, and uses draft-07 `definitions`/`#/definitions/...` rather than 2020-12-only keywords. Every object uses `additionalProperties: false`; Pydantic uses strict mode, `extra="forbid"`, and `allow_inf_nan=False`; JavaScript performs the same closed-object checks. Cross-file `$ref` values use registered absolute `$id` URIs, including the existing `forzy://contracts/v2/asset-condition-assessment`; no filesystem-relative resolution is allowed at runtime.

Every **public timeline** timestamp is canonical UTC at exact millisecond precision, `YYYY-MM-DDTHH:mm:ss.sssZ`. Historical source lexical timestamps remain byte-preserved in provenance; live source timestamps with finer precision remain in the existing live record/provenance, but their timeline projection explicitly derives and records the public millisecond instant before identity/order validation. A noncanonical public timestamp is rejected rather than silently normalized by a consumer. Multiple original points may share the same public millisecond and remain distinct through the total-order IDs.

`HistoricalSensorReadingV1` contains exactly:

```text
schemaVersion       "1.0"
readingId           UUIDv5
samplePairId        UUIDv5
operatingCycleId    UUIDv5
assetId             "forzy-motor-01"
sensorId            "s1" | "s2"
eventAt             RFC3339 UTC
sourceTimestampText non-empty source lexical timestamp
sourceKind          "historical_archive"
timestampQuality    "source_without_offset_assumed_timezone"
measurements        exact velocity RMS, acceleration, and temperature object
qualityFlags        string[]
provenance          HistoricalProvenanceV1
```

`HistoricalProvenanceV1` contains `sourceSystem="forzy-csv"`, `batchId`, `sourceFileSha256`, `recordOrdinal`, `sourceLineNumber`, `rowSha256`, and `ingestedAt`. Ordinals start at one; physical source lines start at four.

`TimelinePointV1` uses the same measurement object and total ordering key, but admits two coherent variants only:

- archive: `sourceKind="historical_archive"`, archive timestamp quality, non-null `operatingCycleId`, and historical provenance;
- live: `sourceKind="live_collection"`, `timestampQuality="assumed_from_retrieval"`, nullable `operatingCycleId`, and provenance containing `sourceSystem="forzy-api"`, persisted `readingId`, `scheduledAt`, `receivedAt`, and nullable `collectionPolicyId`.

Crossed source/provenance/timestamp combinations are invalid in all three validators.

`HistoricalAssessmentV1` contains exactly the causal facts needed downstream: `schemaVersion`, `assessmentId`, `foldId`, `sensorId`, `operatingCycleId`, `trainingWindow`, `assessmentWindow`, `assessmentAt`, `anchorPointId`, `status`, nullable scores when not evaluable, score semantics, `persistence{episodeId,episodeStartedAt,persistenceSeconds,persistenceCount}`, `quality{status,flags}`, evidence, `modelFamily`, `modelVersion`, model/fold hashes, pinned report hash, `componentTag=null`, `humanValidationRequired=true`, and limitations. For `watch|alert`, episode ID/start are non-null; the start is the earliest consecutive causally evaluated candidate row in the same source, sensor, segment/cycle, model family/version, fold, and episode, and satisfies `trainingWindow.end < episodeStartedAt <= assessmentWindow.end <= assessmentAt <= anchor.eventAt`. It resets on source/sensor/segment/cycle/policy/model/version/fold/episode change, a gap, a non-candidate/insufficient row, or missing causal evaluation. `persistenceCount` counts those original rows and `persistenceSeconds = assessmentWindow.end - episodeStartedAt`; neither uses nominal cadence. For `normal|insufficient_data`, all episode fields are null/zero as defined by the schema.

`CollectionPolicyV1` is a closed persisted contract, not runtime configuration. It contains exactly:

```text
schemaVersion       "1.0"
collectionPolicyId  non-empty versioned string; initial value "forzy-live-window-v1"
assetId             "forzy-motor-01"
timezone            "America/Sao_Paulo"
activeWeekdays      ["monday","tuesday","wednesday"] in that exact order
windowStartLocal    "12:00:00"
windowEndLocal      "14:00:00"
pollIntervalSeconds 5
gapThresholdSeconds 15
effectiveFrom       RFC3339 UTC
effectiveTo         RFC3339 UTC | null
configurationHash   "sha256:89bde17193c7a34c80d48828f4e61fc5802caa92169d83f8a9fd8e4c282b1bce"
```

The configuration hash is SHA-256 over UTF-8 canonical JSON with recursively sorted object keys, compact separators, and the exact fields `schemaVersion`, `collectionPolicyId`, `assetId`, `timezone`, `activeWeekdays`, `windowStartLocal`, `windowEndLocal`, `pollIntervalSeconds`, and `gapThresholdSeconds`; `effectiveFrom`, `effectiveTo`, and `configurationHash` are excluded. The pinned canonical bytes are:

```json
{"activeWeekdays":["monday","tuesday","wednesday"],"assetId":"forzy-motor-01","collectionPolicyId":"forzy-live-window-v1","gapThresholdSeconds":15,"pollIntervalSeconds":5,"schemaVersion":"1.0","timezone":"America/Sao_Paulo","windowEndLocal":"14:00:00","windowStartLocal":"12:00:00"}
```

Validators require `effectiveTo > effectiveFrom` when present and reject duplicate/reordered weekdays, extra keys, numeric strings, naive timestamps, a mismatched hash, or a policy ID reused with different semantics. The pinned hash above is for the initial object; any changed configuration requires a new `collectionPolicyId`, validity interval, and canonical hash. Policy validity intervals for the same asset may touch but never overlap. A policy applies to a refresh only when `effectiveFrom <= scheduledAt < effectiveTo`, with a null `effectiveTo` meaning no upper bound. Old cycles without an explicit persisted association remain unclassified; validity alone never backfills an association.

`TimelineOverviewV1`, `TimelinePageV1`, and `TimelineContextV1` are also declared now. Their exact nested objects are:

```text
TimelineOverviewV1
  schemaVersion, assetId, queryFingerprint, activeHistoricalBatchId|null,
  requestedRange: TimelineRequestedRangeV1,
  effectiveRange: TimelineHalfOpenRangeV1|null,
  availableRange: TimelineHalfOpenRangeV1|null,
  aggregationSummary: TimelineAggregationSummaryV1,
  segments[], gaps[], operatingCycles: TimelineOperatingCycleV1[], series[],
  eventCandidates: TimelineEventCandidateV1[], capabilities{historical,live}

TimelinePageV1
  schemaVersion, assetId, queryFingerprint, activeHistoricalBatchId|null,
  items: TimelinePointV1[], nextCursor|null, hasMore, limit

TimelineContextV1
  schemaVersion, assetId, selectedAt, segmentId, anchor: TimelinePointV1|null,
  channels{s1: TimelinePointV1|null,s2: TimelinePointV1|null},
  assessment: HistoricalAssessmentV1|AssetConditionAssessmentV2|null,
  decisionFacts: TimelineDecisionFactsV1,
  provenance: TimelineContextProvenanceV1,
  capabilities: TimelineContextCapabilitiesV1,
  limitations[]
```

The overview nested shapes are literal and closed:

```text
TimelineRequestedRangeV1
  from  RFC3339 UTC | null
  to    RFC3339 UTC | null

TimelineHalfOpenRangeV1
  from  RFC3339 UTC
  to    RFC3339 UTC

TimelineAggregationSummaryV1
  requestedMaxPoints  integer 40..4000
  originalPointCount  integer >= 0
  returnedPointCount  integer >= 0
  omittedPointCount   integer >= 0
  reducedSeriesCount  integer >= 0

TimelineOperatingCycleV1
  operatingCycleId          UUIDv5
  sourceKind                "historical_archive"
  batchId                   sha256:<64 lowercase hex>
  startAt                   RFC3339 UTC, inclusive
  endAt                     RFC3339 UTC, inclusive
  durationSeconds           finite number >= 0
  totalPoints               integer >= 1
  sensorCounts              {s1: integer >= 0, s2: integer >= 0}
  candidateCount            integer >= 0
  gapBeforeSeconds          finite number >= 0 | null
  previousOperatingCycleId  UUIDv5 | null
  assumptions               string[]

TimelineSegmentV1
  segmentId                 UUIDv5
  sourceKind                "historical_archive" | "live_collection"
  startAt                   RFC3339 UTC, inclusive
  endAt                     RFC3339 UTC, inclusive
  totalPoints               integer >= 1
  sensorCounts              {s1: integer >= 0, s2: integer >= 0}
  timestampQuality          "source_without_offset_assumed_timezone" |
                            "assumed_from_retrieval"
  batchId                   sha256:<64 lowercase hex> | null
  collectionPolicyId        non-empty string | null
  assumptions               string[]

TimelineGapV1
  gapId                     UUIDv5
  leftSegmentId             UUIDv5 | null
  rightSegmentId            UUIDv5 | null
  startAt                   RFC3339 UTC, exclusive
  endAt                     RFC3339 UTC, exclusive
  gapType                   "source_discontinuity" | "archive_sampling_gap" |
                            "live_expected_collection_gap" | "expected_idle" |
                            "unclassified_coverage_gap"
  durationSeconds           finite number > 0
  ruleVersion               "timeline-gap-v1"
  messageCode               "timeline_gap_source_discontinuity" |
                            "timeline_gap_archive_sampling" |
                            "timeline_gap_live_expected_collection" |
                            "timeline_gap_expected_idle" |
                            "timeline_gap_unclassified_coverage"
```

`requestedRange` preserves the caller's nullable normalized bounds. `effectiveRange` is the actual `[from,to)` used by the query and is null when no point exists. `availableRange` is the smallest public-millisecond `[from,to)` covering every readable active-archive/live point: `from` is the earliest original `eventAt` and `to` is `public_millisecond_successor_v1(latestEventAt)`. That helper accepts only a canonical public-millisecond instant and adds exactly one millisecond; distinct points tied in the same millisecond therefore share one successor while IDs retain their order. It is null only when neither source has a point. When an unbounded effective range reaches the latest point, it uses that same successor rule. An explicit caller `to` remains unchanged. The terminal public instant `9999-12-31T23:59:59.999Z` raises `TimelineRangeOverflow`; clamping, wrapping, sub-millisecond input/output, or returning a non-covering bound is forbidden.

Each series contains exactly `segmentId`, `sensorId`, `sourceKind`, `metric`, `points` and closed `aggregation{method:"none"|"time_bucket_envelope_v1",requestedMaxPoints,originalPointCount,returnedPointCount,omittedPointCount}`. `segmentId` references exactly one returned segment; every point in the series belongs to that same segment/source/sensor and contains only its original `pointId`, canonical `eventAt` and finite metric `value`. A series never crosses a gap or source boundary.

`maxPoints` is one global ceiling for each `(sensorId, sourceKind)` combination in the response, not a fresh allowance for every segment series. The request resolves exactly one metric. For each sensor/source combination, the service deterministically applies the one `time_bucket_envelope_v1` selection to all of that combination's original points in the effective range and only then partitions the selected original points back into segment-scoped series. It returns one series for every nonempty original `(segmentId, sensorId, sourceKind)` group, including an empty `points` array when the global selector retained no point from that segment, so omitted originals remain countable and no series crosses a gap. Every split series repeats the request-level `requestedMaxPoints` and inherits the combination-level method: all are `none` exactly when the combination's original count is at most the ceiling; otherwise all are `time_bucket_envelope_v1`, even when a particular segment happened to retain all its local points.

For each `(sensorId, sourceKind)`, the sum of `returnedPointCount` across its segment series is at most `requestedMaxPoints`. Per-series original/returned/omitted counts are local to that segment and satisfy `omittedPointCount = originalPointCount - returnedPointCount`; their sums equal the original/returned/omitted counts for the sensor/source selection. Summary original/returned/omitted counts are the respective sums across every returned series, and `reducedSeriesCount` is exactly the number of segment series whose inherited method is not `none`. The composed Python/JavaScript invariant validators enforce the payload-observable per-combination ceiling, segment references/membership, method agreement inside a combination, local arithmetic, and summary equalities. Because the response cannot independently reveal an omitted original group hidden by a faulty producer, the service construction test against the full original-point-to-segment map owns the one-series-per-original-group proof. These facts prevent the browser from guessing whether reduction occurred or accidentally multiplying the budget by the number of gaps.

The two segment/gap shapes above are exhaustive. `sensorCounts.s1 + sensorCounts.s2 = totalPoints`, `startAt <= endAt`, assumptions are unique canonical strings, and a segment contains only original points with the same source and timestamp quality. Archive segments require non-null `batchId`, null `collectionPolicyId`, and archive timestamp quality; live segments require null `batchId`, live timestamp quality, and carry either one exact persisted policy ID or null when coverage is unclassified. A gap requires `startAt < endAt`, `durationSeconds = endAt - startAt`, and exactly the message code paired by ordinal with its `gapType`; `gapId` is UUIDv5 over `timeline-gap-v1|gapType|left-or-none|right-or-none|startAt|endAt|ruleVersion`. A non-null adjacent ID resolves to the segment whose inclusive endpoint borders that side of the open gap; an ID cannot appear on the wrong side or reference an unrelated segment. `source_discontinuity` is the only type between different sources; archive sampling uses `archive_sampling_gap`; a live gap uses `live_expected_collection_gap` only with one valid explicitly associated policy that expected collection, `expected_idle` only with valid policy evidence that did not expect collection, and `unclassified_coverage_gap` when policy evidence is missing/invalid. Series expose sensor, source, metric, value points, and the closed aggregation object above.

`TimelineEventCandidateV1` contains exactly:

```text
schemaVersion            "1.0"
candidateId              UUIDv5
anchorPointId            UUIDv5 of the original, unreduced TimelinePointV1
operatingCycleId         UUIDv5 | null
sensorId                 "s1" | "s2"
eventAt                  RFC3339 UTC
sourceKind               "historical_archive" | "live_collection"
status                   "watch" | "alert"
persistenceCount         integer >= 1
episodeStartedAt         RFC3339 UTC
dataTrust                "sufficient" | "degraded" | "insufficient"
quality                  {status:"ok"|"degraded"|"insufficient_data",flags:string[]}
batchId                  sha256:<64 lowercase hex> | null
modelFamily              non-empty string
modelVersion             non-empty string
foldId                   non-empty string | null
candidateRankingVersion  "forzy-review-priority-v1"
```

Before projection, the service rereads `anchorPointId` and its original pair and requires exact equality of anchor source, sensor, `eventAt`, cycle, and batch; the pure projector then revalidates those supplied identities before serialization. A reduced-series point or synthetic timestamp can never be an anchor. Historical candidates require non-null `operatingCycleId`, `batchId`, and `foldId`; live candidates require `batchId=null` and `foldId=null`, while their cycle may be null. `quality.flags` are unique and canonically ordered. `dataTrust="sufficient"` requires quality `ok`, a complete original pair, and no gap; quality `ok` with a partial pair or quality `degraded` yields at most `degraded`; quality `insufficient_data` or unavailable/gap evidence yields `insufficient`. A candidate cannot claim trust better than those facts. `persistenceCount` and `episodeStartedAt` come from the causal original-row episode defined above; the candidate verifies `episodeStartedAt <= eventAt` and the same source/segment/episode/model/fold reset boundaries. `candidateId` is UUIDv5 over `timeline-event-candidate-v1|sourceKind|batch-or-none|anchorPointId|modelFamily|modelVersion|fold-or-none`. Candidates never expose failure probability, RUL, cause, or component attribution.

`operatingCycles` contains archive cycles only and is ordered by `startAt`, then `operatingCycleId`. The real registered batch must expose 204 entries. `sensorCounts.s1 + sensorCounts.s2 = totalPoints`; `candidateCount` counts only validated candidates anchored in that cycle; `durationSeconds = endAt - startAt`; and `previousOperatingCycleId` references only the immediately preceding cycle in the same active batch/source, null for the first cycle.

`TimelineDecisionFactsV1` is backend evidence, not UI copy or a triage ruleset. It contains exactly:

```text
schemaVersion           "1.0"
conditionState          normal | watch | alert | insufficient_data | unknown
conditionTemporalScope current | last_known | historical | none
conditionAsOf           RFC3339 UTC | null
conditionEpisodeStartedAt RFC3339 UTC | null
conditionSource         live_assessment | historical_walk_forward | none
collectionState         received_now | last_known | expected_idle | unavailable |
                        historical_context | historical_gap
collectionExpectation   expected_now | expected_idle | not_applicable
dataAvailability        complete | partial | gap | unavailable
dataFreshness           fresh | stale | historical | unknown
dataTrust               sufficient | degraded | insufficient
```

`TimelineContextProvenanceV1` contains `pointSourceKind|null`, `pointSourceSystem|null`, `activeHistoricalBatchId|null`, `collectionPolicyId|null`, and `assessmentSource` using the same closed `conditionSource` enum. `TimelineContextCapabilitiesV1` contains booleans `historicalNavigation`, `pairedChannels`, `causalAssessment`, `baselineComparison`, and `previousCycleComparison`. These are calculated from the selected original point, active batch, linked collection policy, causal assessment, and same-source previous cycle. They are never inferred from screen width or frontend clocks.

Contract validators enforce: `conditionAsOf` and `conditionEpisodeStartedAt` are null when temporal scope/source are `none`; a non-null episode start requires a non-null condition time, `episodeStartedAt <= conditionAsOf`, and a returned matching causal assessment. Historical navigation uses `historical` freshness, `historical_context` collection state, `not_applicable` expectation, and never `current`; an explicit gap uses `historical_gap`, null anchor/channels/assessment, `unknown/none/null` condition, gap availability, historical freshness, and insufficient trust. A retrospectively selected live point is also historical navigation: it may preserve `conditionSource="live_assessment"` and `conditionTemporalScope="historical"` only when the assessment survives the normality suppression rule below, and it never becomes snapshot-now facts. A gap/unavailable context cannot claim a current condition; a missing policy cannot become `expected_now`; `dataTrust` reflects explicit quality/coverage facts independently of condition state.

In every projection scope, `normal + (dataTrust=degraded|insufficient or dataAvailability!=complete)` retains `conditionState="normal"` as the assessment label but must set `conditionTemporalScope="none"`, `conditionSource="none"`, and both condition timestamps null; it is not a declaration of current or causally supported normality. `insufficient_data` without a returned assessment likewise uses `none/none/null`; an explicit timely snapshot assessment may use `current/live_assessment` with its `conditionAsOf`, while the same explicit assessment selected retrospectively uses `historical/live_assessment`. Watch/alert evidence remains visible under degraded trust but cannot invent episode data. Presentation adapters must distinguish these variants and copy the facts literally rather than overwriting them. `TimelineContextV1` intentionally omits `summaryCode`, `triageState`, copy, checklists, rule-set hashes, and action recommendations: `OperationalDecisionViewV1` derives those in the presentation layer from these closed facts without magic numbers.

## Closed foundation core type catalog

Public contracts above are owned by `contracts/timeline_v1_models.py`; existing `MeasurementsV2`, `CanonicalSensorReadingV2`, and `AssetConditionAssessmentV2` are imported unchanged from `contracts/v2_models.py`, `TelemetryRepositoryV2` from `storage/v2_repository.py`, and `HistoricalBatchConflict` from the historical repository error module. Standard names (`re`, `UUID`, `datetime`, `timedelta`, `timezone`, `Path`, `dataclass`, `Annotated`, `Literal`, `Mapping`, `Protocol`, `Sequence`, `BeforeValidator`, and `PlainSerializer`) come from Python/Pydantic. The following internal types are frozen here before any task first uses them:

```python
PUBLIC_UTC_MILLIS_RE = re.compile(
    r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r"T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d\.\d{3}Z$"
)

def parse_uuid_json_v1(value: object) -> UUID:
    if isinstance(value, UUID):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = UUID(value)
        except ValueError as exc:
            raise ValueError("expected a canonical UUID string") from exc
    else:
        raise ValueError("expected a canonical UUID string")
    if str(parsed) != str(value):
        raise ValueError("expected a canonical lowercase UUID string")
    return parsed

def parse_public_utc_millis_v1(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and PUBLIC_UTC_MILLIS_RE.fullmatch(value):
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise ValueError("expected a real canonical UTC millisecond instant") from exc
    else:
        raise ValueError("expected YYYY-MM-DDTHH:mm:ss.sssZ")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("expected an aware UTC instant")
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond % 1_000:
        raise ValueError("public timeline timestamps require exact milliseconds")
    return parsed

def serialize_public_utc_millis_v1(value: datetime) -> str:
    parsed = parse_public_utc_millis_v1(value)
    return f"{parsed:%Y-%m-%dT%H:%M:%S}.{parsed.microsecond // 1_000:03d}Z"

Sha256V1 = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
UuidV1 = Annotated[
    UUID,
    BeforeValidator(parse_uuid_json_v1),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
]
UtcTimestampV1 = Annotated[
    datetime,
    BeforeValidator(parse_public_utc_millis_v1),
    PlainSerializer(
        serialize_public_utc_millis_v1, return_type=str, when_used="json"
    ),
]
TimelineMeasurementsV1 = MeasurementsV2
TimelineSourceKindV1 = Literal["historical_archive", "live_collection"]
TimelineTimestampQualityV1 = Literal[
    "source_without_offset_assumed_timezone", "assumed_from_retrieval"
]
TimelineGapTypeV1 = Literal[
    "source_discontinuity", "archive_sampling_gap",
    "live_expected_collection_gap", "expected_idle",
    "unclassified_coverage_gap",
]
TimelineGapMessageCodeV1 = Literal[
    "timeline_gap_source_discontinuity", "timeline_gap_archive_sampling",
    "timeline_gap_live_expected_collection", "timeline_gap_expected_idle",
    "timeline_gap_unclassified_coverage",
]
BatchStatusV1 = Literal["staged", "active", "superseded"]
EnvironmentV1 = Literal["local", "preview", "production"]
JsonScalarV1 = str | int | bool | None

class TimelineRangeOverflow(ValueError):
    pass

def public_millisecond_successor_v1(value: datetime) -> datetime:
    parsed = parse_public_utc_millis_v1(value)
    terminal = datetime(9999, 12, 31, 23, 59, 59, 999_000, tzinfo=timezone.utc)
    if parsed == terminal:
        raise TimelineRangeOverflow("timeline_range_overflow")
    return parsed + timedelta(milliseconds=1)

@dataclass(frozen=True)
class MigrationSpec:
    version: str
    sqlite_path: Path
    postgres_path: Path
    sqlite_sha256: Sha256V1
    postgres_sha256: Sha256V1

@dataclass(frozen=True)
class SchemaVerification:
    expected_version: str
    current_version: str | None
    applied_migration_hashes: Mapping[str, Sha256V1]
    is_current: bool

@dataclass(frozen=True)
class DeploymentIdentityV1:
    environment: EnvironmentV1
    label: str
    target_fingerprint: Sha256V1
    schema_version: str

@dataclass(frozen=True)
class CollectionPolicySeedResultV1:
    policy: CollectionPolicyV1
    inserted: bool
    writes_performed: int

@dataclass(frozen=True)
class HistoryProfileV1:
    profile_id: str
    source_size_bytes: int
    source_sha256: Sha256V1
    header_records: tuple[bytes, bytes, bytes]
    encoding: Literal["utf-8"]
    delimiter: Literal[";"]
    newline: Literal["CRLF"]
    final_crlf_required: bool
    data_record_count: int
    sample_count: int
    operating_cycle_count: int
    timezone_name: Literal["America/Sao_Paulo"]
    parser_version: str
    contract_version: Literal["1.0"]
    gap_seconds: float

@dataclass(frozen=True)
class HistoricalRawRowV1:
    batch_id: Sha256V1
    record_ordinal: int
    source_line_number: int
    byte_start: int
    byte_end: int
    source_timestamp_text: str
    canonical_values_json: str
    row_sha256: Sha256V1

@dataclass(frozen=True)
class HistoricalStoredSampleV1:
    batch_id: Sha256V1
    record_ordinal: int
    point_id: str
    reading: HistoricalSensorReadingV1

@dataclass(frozen=True)
class PreparedHistoricalBatchV1:
    batch_id: Sha256V1
    asset_id: Literal["forzy-motor-01"]
    source_bytes: bytes
    source_sha256: Sha256V1
    manifest_json: str
    manifest_sha256: Sha256V1
    imported_at: datetime
    raw_rows: tuple[HistoricalRawRowV1, ...]
    samples: tuple[HistoricalStoredSampleV1, ...]

@dataclass(frozen=True)
class StoredHistoricalAssessmentV1:
    batch_id: Sha256V1
    assessment: HistoricalAssessmentV1

@dataclass(frozen=True)
class HistoricalBatchSummaryV1:
    batch_id: Sha256V1
    asset_id: Literal["forzy-motor-01"]
    status: BatchStatusV1
    source_sha256: Sha256V1
    manifest_sha256: Sha256V1
    raw_row_count: int
    sample_count: int
    operating_cycle_count: int
    assessment_count: int
    assessment_manifest_sha256: Sha256V1 | None
    staged_at: datetime
    activated_at: datetime | None

@dataclass(frozen=True)
class StageHistoryResultV1:
    batch: HistoricalBatchSummaryV1
    inserted: bool
    writes_performed: int

@dataclass(frozen=True)
class AssessmentStoreResultV1:
    batch_id: Sha256V1
    inserted_count: int
    existing_count: int
    total_count: int
    assessment_manifest_sha256: Sha256V1
    writes_performed: int

@dataclass(frozen=True)
class ActivateHistoryResultV1:
    asset_id: Literal["forzy-motor-01"]
    batch_id: Sha256V1
    previous_active_batch_id: Sha256V1 | None
    active_batch_id: Sha256V1
    activated: bool
    assessment_count: int
    assessment_manifest_sha256: Sha256V1 | None
    writes_performed: int

@dataclass(frozen=True)
class DirectoryIdentityV1:
    canonical_path: Path
    device_or_volume: int
    inode_or_file_id: int

@dataclass(frozen=True)
class LocalWritePermitV1:
    root: DirectoryIdentityV1
    target_path: Path
    creator_pid: int
    private_token: bytes

class AdminResultWriterV1(Protocol):
    def write(
        self, path: Path, result: Mapping[str, JsonScalarV1]
    ) -> Sha256V1: ...

class HistoricalRepositoryV1(Protocol):
    def verify_schema(self, expected_version: str) -> SchemaVerification: ...
    def target_identity(self) -> DeploymentIdentityV1 | None: ...
    def stage_batch(self, batch: PreparedHistoricalBatchV1) -> StageHistoryResultV1: ...
    def store_assessments(
        self, batch_id: str, assessments: Sequence[StoredHistoricalAssessmentV1]
    ) -> AssessmentStoreResultV1: ...
    def activate_batch(
        self, *, asset_id: str, batch_id: str,
        expected_active_batch_id: str | None,
    ) -> ActivateHistoryResultV1: ...
    def active_batch(self, asset_id: str) -> HistoricalBatchSummaryV1 | None: ...
    def reconstruct_source(self, batch_id: str) -> bytes: ...
    def collection_policy(self, policy_id: str) -> CollectionPolicyV1 | None: ...
    def collection_policies(
        self, policy_ids: set[str]
    ) -> dict[str, CollectionPolicyV1]: ...
    def effective_collection_policy(
        self, asset_id: str, at: datetime
    ) -> CollectionPolicyV1 | None: ...

class RepositoryFactory(Protocol):
    def __call__(
        self,
        *,
        environment: EnvironmentV1,
        expected_target_fingerprint: Sha256V1,
        expected_schema_version: str,
        local_write_permit: LocalWritePermitV1 | None,
    ) -> HistoricalRepositoryV1: ...
```

Owners/invariants are fixed. `UuidV1`, `UtcTimestampV1`, and `TimelineMeasurementsV1` are the strict canonical UUID, aware-UTC exact-millisecond timestamp, and unchanged closed `MeasurementsV2` aliases owned by `contracts/timeline_v1_models.py`; model-specific invariants still require UUIDv5 wherever the public shape declares a deterministic v5 identity. Their `BeforeValidator`s admit the canonical strings produced by a JSON decoder while strict mode continues to reject numeric UUID/timestamp inputs, noncanonical UUIDs, offsets other than lexical `Z`, naive timestamps, and sub-millisecond values. Their JSON serializers emit lowercase canonical UUID strings and timestamps with exactly `.sssZ`; every public response uses aliases and JSON mode rather than Python-mode dumps. Migration/schema/identity types live in `storage/schema_migrations.py`; policy seed result in `storage/collection_policy_v1.py`; profile/raw/sample/prepared types in `ingestion/history_profiles_v1.py` and `ingestion/historical_import_v1.py`; repository summaries/results/protocol in `storage/historical_repository_v1.py`; local directory/permit types in `security/local_write_guard_v1.py`; `AdminResultWriterV1` lives in `security/admin_result_writer_v1.py`; `RepositoryFactory` lives in `history_admin.py`. All datetimes are aware UTC; hashes include the `sha256:` prefix; counts/writes are non-negative; raw ordinals start at one and line numbers at four; byte ranges are contiguous, inclusive/exclusive, and bounded by `source_bytes`; each sample's reading provenance matches its batch/ordinal; prepared tuple counts equal its registered profile; result IDs/counts/hashes are reread from the committed/no-op state. `SchemaVerification.is_current` is true exactly when version and all registered SQL hashes match. `LocalWritePermitV1.private_token` is memory-only, non-serializable, and its identities are reattested before use. `AdminResultWriterV1` accepts only the flat, command-specific sanitized shapes frozen in Task 6 and returns the SHA-256 of the exact canonical JSON bytes written.

---

### Task 1: Freeze the archive and timeline contract matrix

**Files:**

- Create: `contracts/timeline/v1/historical-sensor-reading.schema.json`
- Create: `contracts/timeline/v1/timeline-point.schema.json`
- Create: `contracts/timeline/v1/historical-assessment.schema.json`
- Create: `contracts/timeline/v1/collection-policy.schema.json`
- Create: `contracts/timeline/v1/timeline-event-candidate.schema.json`
- Create: `contracts/timeline/v1/timeline-overview.schema.json`
- Create: `contracts/timeline/v1/timeline-page.schema.json`
- Create: `contracts/timeline/v1/timeline-decision-facts.schema.json`
- Create: `contracts/timeline/v1/timeline-context.schema.json`
- Create: `contracts/timeline/v1/fixtures/historical-reading.valid.json`
- Create: `contracts/timeline/v1/fixtures/live-point.valid.json`
- Create: `contracts/timeline/v1/fixtures/source-provenance-cross.invalid.json`
- Create: `contracts/timeline/v1/fixtures/historical-assessment.valid.json`
- Create: `contracts/timeline/v1/fixtures/historical-assessment-future.invalid.json`
- Create: `contracts/timeline/v1/fixtures/historical-assessment-episode.invalid.json`
- Create: `contracts/timeline/v1/fixtures/collection-policy.valid.json`
- Create: `contracts/timeline/v1/fixtures/collection-policy-hash.invalid.json`
- Create: `contracts/timeline/v1/fixtures/event-candidate-historical.valid.json`
- Create: `contracts/timeline/v1/fixtures/event-candidate-live.valid.json`
- Create: `contracts/timeline/v1/fixtures/event-candidate-cross.invalid.json`
- Create: `contracts/timeline/v1/fixtures/event-candidate-episode.invalid.json`
- Create: `contracts/timeline/v1/fixtures/overview-unified.valid.json`
- Create: `contracts/timeline/v1/fixtures/overview-live-only.valid.json`
- Create: `contracts/timeline/v1/fixtures/page.valid.json`
- Create: `contracts/timeline/v1/fixtures/context-missing-channel.valid.json`
- Create: `contracts/timeline/v1/fixtures/context-historical-candidate.valid.json`
- Create: `contracts/timeline/v1/fixtures/context-historical-gap.valid.json`
- Create: `contracts/timeline/v1/fixtures/context-decision-facts-cross.invalid.json`
- Create: `contracts/timeline/v1/fixtures/public-millisecond-successor-v1-cases.json`
- Create: `services/twinops/src/twinops/contracts/timeline_v1_models.py`
- Create: `services/twinops/tests/contracts/test_timeline_v1_models.py`
- Create: `src/contracts/timelineV1.js`
- Create: `src/contracts/timelineV1.test.js`
- Create: `src/contracts/schemaTimelineV1.test.js`

- [ ] **Step 1: Write the failing shared-fixture tests**

The initial Python test must avoid importing the absent module at collection time and first assert `importlib.util.find_spec("twinops.contracts.timeline_v1_models") is not None` with the exact failure message `RED:A1:python-timeline-contract-missing`; after implementation, replace the deferred discovery seam with the real imports while retaining the behavioral assertion. The initial JavaScript test likewise checks file existence without an unresolved static import and fails with exactly `RED:A1:javascript-timeline-contract-missing`; Step 3 replaces that seam with the real static imports. In Python, map each fixture to its Pydantic model and prove strict numeric/timestamp/source behavior:

```python
@pytest.mark.parametrize(
    ("fixture_name", "model_type"),
    [
        ("historical-reading.valid.json", HistoricalSensorReadingV1),
        ("live-point.valid.json", TimelinePointV1),
        ("historical-assessment.valid.json", HistoricalAssessmentV1),
        ("collection-policy.valid.json", CollectionPolicyV1),
        ("event-candidate-historical.valid.json", TimelineEventCandidateV1),
        ("event-candidate-live.valid.json", TimelineEventCandidateV1),
        ("overview-unified.valid.json", TimelineOverviewV1),
        ("overview-live-only.valid.json", TimelineOverviewV1),
        ("page.valid.json", TimelinePageV1),
        ("context-missing-channel.valid.json", TimelineContextV1),
        ("context-historical-candidate.valid.json", TimelineContextV1),
        ("context-historical-gap.valid.json", TimelineContextV1),
    ],
)
def test_timeline_fixture_matrix_accepts_valid_cases(fixture_name, model_type):
    payload = _fixture(fixture_name)
    parsed = model_type.model_validate(payload)
    wire_json = parsed.model_dump_json(by_alias=True, exclude_none=False)
    wire_payload = json.loads(wire_json)

    assert wire_payload == payload
    assert model_type.model_validate_json(wire_json) == parsed

def test_strict_public_json_accepts_strings_and_emits_canonical_wire_values():
    payload = _fixture("live-point.valid.json")
    assert isinstance(payload["pointId"], str)
    assert isinstance(payload["eventAt"], str)

    point = TimelinePointV1.model_validate(payload)
    wire = point.model_dump(mode="json", by_alias=True, exclude_none=False)

    assert wire["pointId"] == payload["pointId"]
    assert PUBLIC_UTC_MILLIS_RE.fullmatch(wire["eventAt"])
    assert wire["eventAt"] == payload["eventAt"]
    assert "point_id" not in wire
    assert TimelinePointV1.model_validate(wire) == point

@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pointId", 123),
        ("pointId", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),
        ("eventAt", 1_724_329_600),
        ("eventAt", "2026-08-22T12:00:00+00:00"),
        ("eventAt", "2026-08-22T12:00:00.123456Z"),
    ],
)
def test_strict_public_json_rejects_noncanonical_identifier_or_timestamp(field, value):
    payload = _fixture("live-point.valid.json")
    payload[field] = value
    with pytest.raises(ValidationError):
        TimelinePointV1.model_validate(payload)

def test_source_and_provenance_cannot_be_crossed():
    with pytest.raises(ValidationError):
        TimelinePointV1.model_validate(_fixture("source-provenance-cross.invalid.json"))

def test_historical_assessment_rejects_future_training_or_window():
    with pytest.raises(ValidationError):
        HistoricalAssessmentV1.model_validate(
            _fixture("historical-assessment-future.invalid.json")
        )

def test_historical_assessment_rejects_noncausal_episode_start():
    with pytest.raises(ValidationError):
        HistoricalAssessmentV1.model_validate(
            _fixture("historical-assessment-episode.invalid.json")
        )

def test_policy_hash_and_candidate_source_branches_fail_closed():
    with pytest.raises(ValidationError):
        CollectionPolicyV1.model_validate(_fixture("collection-policy-hash.invalid.json"))
    with pytest.raises(ValidationError):
        TimelineEventCandidateV1.model_validate(_fixture("event-candidate-cross.invalid.json"))
    with pytest.raises(ValidationError):
        TimelineEventCandidateV1.model_validate(_fixture("event-candidate-episode.invalid.json"))

def test_context_rejects_crossed_temporal_and_collection_facts():
    with pytest.raises(ValidationError):
        TimelineContextV1.model_validate(
            _fixture("context-decision-facts-cross.invalid.json")
        )
```

The Foundation-owned successor fixture is literal and is the only table either runtime may consume:

```json
{
  "schemaVersion": "1.0",
  "valid": [
    {"caseId":"ordinary","input":"2026-08-22T12:00:00.123Z","expected":"2026-08-22T12:00:00.124Z"},
    {"caseId":"tied-point-a","input":"2026-08-22T12:00:00.999Z","expected":"2026-08-22T12:00:01.000Z"},
    {"caseId":"tied-point-b","input":"2026-08-22T12:00:00.999Z","expected":"2026-08-22T12:00:01.000Z"},
    {"caseId":"day-rollover","input":"2026-08-22T23:59:59.999Z","expected":"2026-08-23T00:00:00.000Z"}
  ],
  "invalid": [
    {"caseId":"sub-millisecond","input":"2026-08-22T12:00:00.1234Z","errorCode":"timeline_invalid_public_millisecond"},
    {"caseId":"terminal-overflow","input":"9999-12-31T23:59:59.999Z","errorCode":"timeline_range_overflow"}
  ]
}
```

Mirror every structurally expressible assertion in draft-07 JSON Schema, AJV, and `timelineV1.js`, including type/nullability, closed keys, source discriminators, timestamp syntax, literal policy fields and the exact historical-gap branch. Cross-field arithmetic, total ordering, canonical-calendar parsing, temporal inequalities, graph references and sum/count equalities are deliberately **not** claimed as draft-07 keywords: implement a closed `assert_timeline_invariants_v1(...)` after structural validation in both Python and JavaScript. The Python public validator is `Draft7Validator + assert_timeline_invariants_v1`; the JavaScript public validator is `AJV + assertTimelineInvariantsV1`; Pydantic calls the same Python invariant functions. A exports `public_millisecond_successor_v1(value: datetime) -> datetime` and `publicMillisecondSuccessorV1(value: string) -> string`; both read `public-millisecond-successor-v1-cases.json` unchanged, return the literal expected values, reject the invalid precision with `timeline_invalid_public_millisecond`, and raise `TimelineRangeOverflow("timeline_range_overflow")` / `RangeError("timeline_range_overflow")` for terminal overflow. The parity matrix covers `NaN`, `Infinity`, numeric strings, impossible calendar timestamps, extra keys, archive/live provenance crossings, policy hash/validity, candidate anchor/source/quality/model/episode crossings, missing-channel nullability, 204-cycle ordering/count facts, the exact segment/gap field/enumeration/cross-field rules, millisecond-successor behavior, aggregation sums and decision-fact coherence, and requires the **composed public validators** to return the same verdict. Add a multi-segment overview fixture/mutation in which one sensor/source combination spans at least three gaps: both runtimes must accept the deterministic split whose summed `returnedPointCount <= requestedMaxPoints`, reject a response that grants the ceiling independently to each segment, reject crossed segment membership, and reject inconsistent local/summary counts or mixed methods within the same combination. Revalidating the same canonical payload must produce byte-identical canonical JSON and the same series/point order. The Phase B producer test, which can see the original groups, separately proves that a zero-selected segment series cannot be omitted. Run `Draft7Validator.check_schema` for every schema and register every `$id`; do not assert that bare draft-07 alone can prove arithmetic or chronology. In JavaScript, construct AJV without coercion/default removal, add every timeline schema plus the existing v2 asset-assessment schema by `$id` before compiling roots, and assert unresolved/duplicate IDs fail the suite. `TimelineContextV1.assessment` is an explicit draft-07 `oneOf` between the new walk-forward historical assessment, the existing live `AssetConditionAssessmentV2`, and null; do not duplicate or weaken the live model.

- [ ] **Step 2: Run the tests to verify RED**

Run from `services/twinops`:

```powershell
$serviceRoot = (Resolve-Path '.').Path
$worktreeRoot = (Resolve-Path "$serviceRoot\..\..").Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
$redOutput = @(& $python -m pytest tests/contracts/test_timeline_v1_models.py -q 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch [regex]::Escape('RED:A1:python-timeline-contract-missing') -or $redText -match '(?m)^(ERROR|INTERNALERROR)') { throw 'timeline contract RED did not fail on its exact assertion' }
$redOutput
```

Expected: FAIL only on `RED:A1:python-timeline-contract-missing`; import or collection errors are forbidden.

Run from the repository root:

```powershell
$redOutput = @(npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/contracts/schemaTimelineV1.test.js src/contracts/timelineV1.test.js 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch [regex]::Escape('RED:A1:javascript-timeline-contract-missing') -or $redText -match '(?m)^(ERROR|INTERNALERROR)') { throw 'timeline JavaScript RED did not fail on its exact assertion' }
$redOutput
```

Expected: FAIL because the schemas and runtime validator do not exist.

- [ ] **Step 3: Implement schemas, strict Pydantic models, and strict JavaScript validation**

Use a discriminated validator instead of a permissive provenance dictionary:

```python
class ContractModelTimelineV1(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        allow_inf_nan=False,
        populate_by_name=False,
    )

    def model_dump_public(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=False)

    def model_dump_public_json(self) -> str:
        return self.model_dump_json(by_alias=True, exclude_none=False)

class HistoricalProvenanceV1(ContractModelTimelineV1):
    source_system: Literal["forzy-csv"] = Field(alias="sourceSystem")
    batch_id: Sha256V1 = Field(alias="batchId")
    source_file_sha256: Sha256V1 = Field(alias="sourceFileSha256")
    record_ordinal: int = Field(alias="recordOrdinal", ge=1)
    source_line_number: int = Field(alias="sourceLineNumber", ge=4)
    row_sha256: Sha256V1 = Field(alias="rowSha256")
    ingested_at: UtcTimestampV1 = Field(alias="ingestedAt")

class LiveTimelineProvenanceV1(ContractModelTimelineV1):
    source_system: Literal["forzy-api"] = Field(alias="sourceSystem")
    reading_id: UuidV1 = Field(alias="readingId")
    scheduled_at: UtcTimestampV1 = Field(alias="scheduledAt")
    received_at: UtcTimestampV1 = Field(alias="receivedAt")
    collection_policy_id: str | None = Field(alias="collectionPolicyId")

class TimelinePointV1(ContractModelTimelineV1):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    point_id: UuidV1 = Field(alias="pointId")
    sample_pair_id: UuidV1 = Field(alias="samplePairId")
    operating_cycle_id: UuidV1 | None = Field(alias="operatingCycleId")
    asset_id: Literal["forzy-motor-01"] = Field(alias="assetId")
    sensor_id: Literal["s1", "s2"] = Field(alias="sensorId")
    event_at: UtcTimestampV1 = Field(alias="eventAt")
    source_kind: Literal["historical_archive", "live_collection"] = Field(alias="sourceKind")
    timestamp_quality: Literal[
        "source_without_offset_assumed_timezone", "assumed_from_retrieval"
    ] = Field(alias="timestampQuality")
    measurements: TimelineMeasurementsV1
    quality_flags: list[str] = Field(alias="qualityFlags")
    provenance: HistoricalProvenanceV1 | LiveTimelineProvenanceV1

    @model_validator(mode="after")
    def source_claims_are_coherent(self) -> Self:
        historical = self.source_kind == "historical_archive"
        if historical != isinstance(self.provenance, HistoricalProvenanceV1):
            raise ValueError("sourceKind and provenance must describe the same source")
        if historical and self.operating_cycle_id is None:
            raise ValueError("historical points require operatingCycleId")
        return self
```

`populate_by_name=False` makes aliases the only accepted already-decoded JSON keys; public adapters call `model_dump_public()`/`model_dump_public_json()` so aliases, UUID strings, explicit nulls, and canonical `.sssZ` timestamps cannot depend on caller options. Use `BeforeValidator` only for the two JSON-native string encodings above: strict numeric, boolean, collection, and object validation remains unchanged. Use draft-07 `definitions` plus `oneOf` to enforce the same branch. Use absolute `$id` references for shared schemas and `#/definitions/...` only within the same document. Do not rely on AJV coercion, 2019-09/2020-12 vocabularies, or implementation-specific `$defs` behavior.

- [ ] **Step 4: Run the focused tests to verify GREEN**

Expected: both commands PASS with no skipped case.

- [ ] **Step 5: Commit**

```powershell
$expectedStagedPaths=@('contracts/timeline/v1/historical-sensor-reading.schema.json','contracts/timeline/v1/timeline-point.schema.json','contracts/timeline/v1/historical-assessment.schema.json','contracts/timeline/v1/collection-policy.schema.json','contracts/timeline/v1/timeline-event-candidate.schema.json','contracts/timeline/v1/timeline-overview.schema.json','contracts/timeline/v1/timeline-page.schema.json','contracts/timeline/v1/timeline-decision-facts.schema.json','contracts/timeline/v1/timeline-context.schema.json','contracts/timeline/v1/fixtures/historical-reading.valid.json','contracts/timeline/v1/fixtures/live-point.valid.json','contracts/timeline/v1/fixtures/source-provenance-cross.invalid.json','contracts/timeline/v1/fixtures/historical-assessment.valid.json','contracts/timeline/v1/fixtures/historical-assessment-future.invalid.json','contracts/timeline/v1/fixtures/historical-assessment-episode.invalid.json','contracts/timeline/v1/fixtures/collection-policy.valid.json','contracts/timeline/v1/fixtures/collection-policy-hash.invalid.json','contracts/timeline/v1/fixtures/event-candidate-historical.valid.json','contracts/timeline/v1/fixtures/event-candidate-live.valid.json','contracts/timeline/v1/fixtures/event-candidate-cross.invalid.json','contracts/timeline/v1/fixtures/event-candidate-episode.invalid.json','contracts/timeline/v1/fixtures/overview-unified.valid.json','contracts/timeline/v1/fixtures/overview-live-only.valid.json','contracts/timeline/v1/fixtures/page.valid.json','contracts/timeline/v1/fixtures/context-missing-channel.valid.json','contracts/timeline/v1/fixtures/context-historical-candidate.valid.json','contracts/timeline/v1/fixtures/context-historical-gap.valid.json','contracts/timeline/v1/fixtures/context-decision-facts-cross.invalid.json','contracts/timeline/v1/fixtures/public-millisecond-successor-v1-cases.json','services/twinops/src/twinops/contracts/timeline_v1_models.py','services/twinops/tests/contracts/test_timeline_v1_models.py','src/contracts/timelineV1.js','src/contracts/timelineV1.test.js','src/contracts/schemaTimelineV1.test.js')
git add contracts/timeline/v1 services/twinops/src/twinops/contracts/timeline_v1_models.py services/twinops/tests/contracts/test_timeline_v1_models.py src/contracts/timelineV1.js src/contracts/timelineV1.test.js src/contracts/schemaTimelineV1.test.js
if ($LASTEXITCODE -ne 0) { throw 'staging timeline contract files failed' }
Assert-ExactStagedScopeV1 -Expected $expectedStagedPaths -Label 'Task A1'
git commit -m "feat: freeze historical timeline contracts"
if ($LASTEXITCODE -ne 0) { throw 'timeline contract commit failed' }
```

### Task 2: Add explicit, versioned schema migration and target identity

**Files:**

- Create: `services/twinops/migrations/003_unified_history_timeline_sqlite.sql`
- Create: `services/twinops/migrations/003_unified_history_timeline_postgres.sql`
- Create: `services/twinops/src/twinops/storage/schema_migrations.py`
- Create: `services/twinops/src/twinops/storage/collection_policy_v1.py`
- Create: `services/twinops/tests/storage/test_schema_migrations_v3.py`
- Create: `services/twinops/tests/storage/test_collection_policy_v1.py`
- Modify: `services/twinops/src/twinops/storage/postgres_repository.py`
- Modify: `services/twinops/src/twinops/storage/sqlite_v2_repository.py`
- Modify: `services/twinops/tests/storage/test_postgres_repository.py`
- Modify: `scripts/check_postgres.py`
- Modify: `services/twinops/tests/test_check_postgres.py`

- [ ] **Step 1: Write failing migration tests**

Cover fresh SQLite, upgrade from 002, a second no-op run, wrong recorded migration hash, and PostgreSQL lock/recheck. Seed/read the initial policy through the administrative migrator and prove: first insert, exact second-run no-op retaining the original `effectiveFrom`, wrong pinned hash rejection, same ID with divergent fields rejection, touching validity accepted, overlapping validity rejected, zero effective matches returning null, multiple effective matches failing closed, validity boundary checks, and no policy write during app construction. Assert these tables:

```python
V3_TABLES = {
    "schema_migrations_v1",
    "deployment_identity_v1",
    "historical_import_batches_v1",
    "historical_raw_rows_v1",
    "historical_samples_v1",
    "historical_assessments_v1",
    "collection_policies_v1",
    "refresh_cycle_policies_v1",
}
```

Also prove that importing or constructing the FastAPI app does not apply migration 003. PostgreSQL DDL is only executed by the explicit administrative migrator after the fixed advisory lock and target preflight.

- [ ] **Step 2: Run RED**

```powershell
$serviceRoot = (Resolve-Path '.').Path
$worktreeRoot = (Resolve-Path "$serviceRoot\..\..").Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
$redOutput = @(& $python -m pytest tests/storage/test_schema_migrations_v3.py tests/storage/test_collection_policy_v1.py tests/test_check_postgres.py tests/storage/test_postgres_repository.py -q 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch [regex]::Escape('RED:A2:migration-surface-missing') -or $redText -match '(?m)^(ERROR|INTERNALERROR)') { throw 'migration RED did not fail on its exact assertion' }
$redOutput
```

Expected: FAIL only on the test assertion `RED:A2:migration-surface-missing`; collection/usage/infrastructure errors do not satisfy RED.

- [ ] **Step 3: Implement the two dialect migrations**

Use `BLOB` in SQLite and `BYTEA` in PostgreSQL. Use UTC text timestamps in SQLite and `TIMESTAMPTZ` in PostgreSQL. Both migrations must enforce the same behavioral constraints.

Required keys and indexes:

```sql
CREATE UNIQUE INDEX uq_historical_import_batches_v1_active_asset
ON historical_import_batches_v1(asset_id) WHERE status = 'active';

CREATE UNIQUE INDEX uq_historical_samples_v1_source_sensor
ON historical_samples_v1(batch_id, record_ordinal, sensor_id);

CREATE INDEX ix_historical_samples_v1_timeline
ON historical_samples_v1(
  asset_id, observed_at, sample_pair_id, sensor_id, reading_id
);

CREATE INDEX ix_historical_assessments_v1_anchor
ON historical_assessments_v1(
  batch_id, anchor_point_id, sensor_id, assessment_at
);

CREATE INDEX ix_telemetry_samples_v2_timeline
ON telemetry_samples_v2(asset_id, observed_at, reading_id);
```

`historical_raw_rows_v1` has composite primary key `(batch_id, record_ordinal)`, inclusive `byte_start`, exclusive `byte_end`, a physical line number, lexical timestamp, parsed canonical JSON, and row SHA. Add checks for positive ordinals/lines and `byte_end > byte_start >= 0`.

`historical_samples_v1` references its raw row, stores the deterministic IDs, three scalar measurements plus canonical JSON, and retains flags/hashes. `historical_assessments_v1.anchor_point_id` references a historical reading. All archive FKs use `ON DELETE RESTRICT`; archive tables are append-only through the repository.

`collection_policies_v1` maps the closed contract one-to-one to columns: `schema_version`, `policy_id`, `asset_id`, `timezone_name`, canonical JSON `active_weekdays_json`, `window_start_local`, `window_end_local`, `poll_interval_seconds`, `gap_threshold_seconds`, `effective_from`, nullable `effective_to`, and `configuration_hash`. Both dialects enforce positive intervals, `window_start_local < window_end_local`, hash syntax, and unique `policy_id`; the Pydantic model performs the full weekday/hash/timestamp validation on every read. The repository/admin transaction rejects overlapping validity for an asset and verifies the initial seed's exact ID/fields/hash.

`refresh_cycle_policies_v1(asset_id, scheduled_at, policy_id)` is the portable association between an existing live refresh cycle and `collection_policies_v1`; it avoids rebuilding `refresh_cycles_v2` in SQLite while satisfying the versioned-policy reference. It has primary key `(asset_id, scheduled_at)`, a foreign key to the exact existing refresh cycle, a foreign key to the policy, and `ON DELETE RESTRICT`. No migration associates legacy cycles.

- [ ] **Step 4: Implement explicit migration state**

Expose:

```python
def apply_sqlite_migrations(
    connection: sqlite3.Connection,
    specs: Sequence[MigrationSpec],
    *,
    initial_policy_effective_from: datetime,
) -> None: ...
def apply_postgres_migrations(
    connection,
    specs: Sequence[MigrationSpec],
    *,
    initial_policy_effective_from: datetime,
) -> None: ...
def verify_schema_version(connection, expected_version: str) -> SchemaVerification: ...

def ensure_initial_collection_policy(
    connection,
    *,
    effective_from: datetime,
) -> CollectionPolicySeedResultV1: ...

def read_collection_policy(connection, policy_id: str) -> CollectionPolicyV1 | None: ...
```

For a database already matching 002, register the baseline only inside the authorized migration transaction, then apply 003. The explicit migration command requires `--initial-policy-effective-from` as an RFC3339 UTC value and calls `ensure_initial_collection_policy` inside that same transaction. A retry rereads the full closed row, validates the pinned canonical hash, returns `inserted=false`, and never changes its original validity. A conflicting row aborts migration; `INSERT OR IGNORE`/`ON CONFLICT DO NOTHING` without an exact reread is prohibited. `seed-collection-policy` in the admin CLI calls the same function for an already migrated target under the normal target/write gates, so recovery remains idempotent and cannot mutate or close an existing version.

A recorded migration version with a different SQL SHA fails closed. Keep the existing fixed PostgreSQL advisory lock/recheck pattern. Change repository runtime initialization so it can verify 003 and read policies after deployment but cannot be the first actor to apply it remotely. The initial policy's `effectiveFrom` is an operator/audit value, not invented from the first telemetry row; future refresh cycles are associated only after that instant.

- [ ] **Step 5: Update the safe PostgreSQL checker**

`scripts/check_postgres.py` accepts only the exact checked-in migration files, verifies target identity and expected current version before DDL, accepts the explicit initial-policy effective time, and emits counts/version plus the non-secret policy ID/configuration hash only. It never prints DSN, host, user, path, or SQL parameters.

- [ ] **Step 6: Run GREEN**

```powershell
$serviceRoot = (Resolve-Path '.').Path
$worktreeRoot = (Resolve-Path "$serviceRoot\..\..").Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
& $python -m pytest tests/storage/test_schema_migrations_v3.py tests/storage/test_collection_policy_v1.py tests/test_check_postgres.py tests/storage/test_postgres_repository.py -q
if ($LASTEXITCODE -ne 0) { throw 'migration GREEN pytest failed' }
```

Expected: focused tests PASS; tests prove no cold-start migration 003 and exact idempotent administrative application.

- [ ] **Step 7: Commit**

```powershell
$expectedStagedPaths=@('services/twinops/migrations/003_unified_history_timeline_sqlite.sql','services/twinops/migrations/003_unified_history_timeline_postgres.sql','services/twinops/src/twinops/storage/schema_migrations.py','services/twinops/src/twinops/storage/collection_policy_v1.py','services/twinops/tests/storage/test_schema_migrations_v3.py','services/twinops/tests/storage/test_collection_policy_v1.py','services/twinops/src/twinops/storage/postgres_repository.py','services/twinops/src/twinops/storage/sqlite_v2_repository.py','services/twinops/tests/storage/test_postgres_repository.py','scripts/check_postgres.py','services/twinops/tests/test_check_postgres.py')
git add services/twinops/migrations services/twinops/src/twinops/storage/schema_migrations.py services/twinops/src/twinops/storage/collection_policy_v1.py services/twinops/src/twinops/storage/postgres_repository.py services/twinops/src/twinops/storage/sqlite_v2_repository.py services/twinops/tests/storage/test_schema_migrations_v3.py services/twinops/tests/storage/test_collection_policy_v1.py services/twinops/tests/storage/test_postgres_repository.py scripts/check_postgres.py services/twinops/tests/test_check_postgres.py
if ($LASTEXITCODE -ne 0) { throw 'staging migration files failed' }
Assert-ExactStagedScopeV1 -Expected $expectedStagedPaths -Label 'Task A2'
git commit -m "feat: add gated historical schema migration"
if ($LASTEXITCODE -ne 0) { throw 'migration commit failed' }
```

### Task 3: Parse the registered CSV byte-for-byte

**Files:**

- Create: `services/twinops/src/twinops/ingestion/history_profiles_v1.py`
- Create: `services/twinops/src/twinops/ingestion/historical_import_v1.py`
- Create: `services/twinops/tests/ingestion/test_history_profiles_v1.py`
- Create: `services/twinops/tests/ingestion/test_historical_import_v1.py`
- Reuse, do not modify: `services/twinops/src/twinops/ingestion/forzy_history.py`

- [ ] **Step 1: Write failing byte-boundary and identity tests**

Use a compact synthetic file with the exact three header records and CRLF. Test wrong BOM, LF-only, missing final CRLF, hash, size, header, count, timestamp order, timestamp timezone, NaN/infinity, empty row, extra column, and an altered byte. Assert `byte_start` inclusive and `byte_end` exclusive reconstruct every source row exactly.

```python
prepared = prepare_historical_batch(
    source_bytes,
    profile=registered_profile("forzy-history-2026-05-19-v1"),
    asset_id="forzy-motor-01",
    ingested_at=datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
)
assert b"".join(
    source_bytes[row.byte_start:row.byte_end] for row in prepared.raw_rows
) == b"".join(source_bytes.splitlines(keepends=True)[3:])
assert len(prepared.samples) == 2 * len(prepared.raw_rows)
assert prepared.samples[0].reading.sample_pair_id == prepared.samples[1].reading.sample_pair_id
```

- [ ] **Step 2: Run RED**

```powershell
$serviceRoot = (Resolve-Path '.').Path
$worktreeRoot = (Resolve-Path "$serviceRoot\..\..").Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
$redOutput = @(& $python -m pytest tests/ingestion/test_history_profiles_v1.py tests/ingestion/test_historical_import_v1.py -q 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch [regex]::Escape('RED:A3:registered-importer-missing') -or $redText -match '(?m)^(ERROR|INTERNALERROR)') { throw 'historical import RED did not fail on its exact assertion' }
$redOutput
```

Expected: FAIL only on `RED:A3:registered-importer-missing`.

- [ ] **Step 3: Implement a closed profile registry**

The registered profile embeds the exact bytes of the three known header records, file size/hash, encoding, delimiter, newline, row/sample/cycle counts, timezone, parser version, contract version, and `gap_seconds=15.0`. There is no generic/fallback profile.

Use the catalogued immutable profile/raw/sample/prepared types and expose:

```python
def registered_profile(profile_id: str) -> HistoryProfileV1: ...
def prepare_historical_batch(
    source_bytes: bytes,
    *,
    profile: HistoryProfileV1,
    asset_id: str,
    ingested_at: datetime,
) -> PreparedHistoricalBatchV1: ...
```

Decode only after byte validation. Parse timestamps with `ZoneInfo("America/Sao_Paulo")`, persist UTC, and retain lexical text. Segment operating cycles on the pair-level timeline: a gap strictly greater than 15 seconds starts the next cycle. Repeated measurements remain samples and gain `unchanged_from_previous`; they are not discarded.

- [ ] **Step 4: Run GREEN**

Expected: all parser tests PASS deterministically on repeated preparation with the same `ingested_at`.

- [ ] **Step 5: Commit**

```powershell
$expectedStagedPaths=@('services/twinops/src/twinops/ingestion/history_profiles_v1.py','services/twinops/src/twinops/ingestion/historical_import_v1.py','services/twinops/tests/ingestion/test_history_profiles_v1.py','services/twinops/tests/ingestion/test_historical_import_v1.py')
git add services/twinops/src/twinops/ingestion/history_profiles_v1.py services/twinops/src/twinops/ingestion/historical_import_v1.py services/twinops/tests/ingestion/test_history_profiles_v1.py services/twinops/tests/ingestion/test_historical_import_v1.py
if ($LASTEXITCODE -ne 0) { throw 'staging historical import files failed' }
Assert-ExactStagedScopeV1 -Expected $expectedStagedPaths -Label 'Task A3'
git commit -m "feat: parse registered Forzy history exactly"
if ($LASTEXITCODE -ne 0) { throw 'historical import commit failed' }
```

### Task 4: Stage and activate historical batches in SQLite

**Files:**

- Create: `services/twinops/src/twinops/storage/historical_repository_v1.py`
- Create: `services/twinops/src/twinops/storage/sqlite_historical_repository_v1.py`
- Create: `services/twinops/tests/storage/historical_repository_contract.py`
- Create: `services/twinops/tests/storage/test_sqlite_historical_repository_v1.py`

- [ ] **Step 1: Write the shared repository contract and SQLite failure tests**

The contract must cover atomic stage, exact revalidation no-op, same source with a different asset producing a different batch, byte reconstruction, immutable rows, count/hash reread, divergent existing batch failure, expected-active compare-and-swap, replacement of one active batch, policy read-by-ID/read-many with full Pydantic/hash validation, and rollback under `Exception`, `KeyboardInterrupt`, and `SystemExit`.

Implement the catalogued `HistoricalRepositoryV1` protocol exactly; adapters may not return dictionaries in place of the frozen result types.

- [ ] **Step 2: Run RED**

```powershell
$serviceRoot = (Resolve-Path '.').Path
$worktreeRoot = (Resolve-Path "$serviceRoot\..\..").Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
$redOutput = @(& $python -m pytest tests/storage/test_sqlite_historical_repository_v1.py -q 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch [regex]::Escape('RED:A4:sqlite-history-repository-missing') -or $redText -match '(?m)^(ERROR|INTERNALERROR)') { throw 'SQLite repository RED did not fail on its exact assertion' }
$redOutput
```

Expected: FAIL only on `RED:A4:sqlite-history-repository-missing`.

- [ ] **Step 3: Implement one-transaction staging**

Open SQLite with foreign keys enabled. Use `BEGIN IMMEDIATE` for stage and activation. Stage the batch row, exact source blob, raw rows, and samples in one transaction; reread count/hash/offset invariants before commit. If the deterministic batch already exists, write nothing and fully revalidate it. Any mismatch raises `HistoricalBatchConflict`. Policy reads are side-effect free, select only requested IDs, construct `CollectionPolicyV1`, and fail closed on stored field/hash drift; they never substitute the runtime default. Effective lookup applies the persisted half-open validity interval and fails closed if corrupted data yields more than one match.

Activation must:

1. lock via `BEGIN IMMEDIATE`;
2. reread target and current active batch;
3. compare the current active ID with the caller's expected ID;
4. validate target status and all registered counts/hashes;
5. supersede the current active row, if any;
6. set exactly the target to active;
7. reread the unique active row before commit.

- [ ] **Step 4: Run GREEN**

Expected: SQLite shared contract PASS, including interruption rollback and exactly one active batch.

- [ ] **Step 5: Commit**

```powershell
$expectedStagedPaths=@('services/twinops/src/twinops/storage/historical_repository_v1.py','services/twinops/src/twinops/storage/sqlite_historical_repository_v1.py','services/twinops/tests/storage/historical_repository_contract.py','services/twinops/tests/storage/test_sqlite_historical_repository_v1.py')
git add services/twinops/src/twinops/storage/historical_repository_v1.py services/twinops/src/twinops/storage/sqlite_historical_repository_v1.py services/twinops/tests/storage/historical_repository_contract.py services/twinops/tests/storage/test_sqlite_historical_repository_v1.py
if ($LASTEXITCODE -ne 0) { throw 'staging SQLite historical repository files failed' }
Assert-ExactStagedScopeV1 -Expected $expectedStagedPaths -Label 'Task A4'
git commit -m "feat: stage and activate historical batches in sqlite"
if ($LASTEXITCODE -ne 0) { throw 'SQLite historical repository commit failed' }
```

### Task 5: Match behavior and concurrency in PostgreSQL

**Files:**

- Create: `services/twinops/src/twinops/storage/postgres_historical_repository_v1.py`
- Create: `services/twinops/tests/storage/test_postgres_historical_repository_v1.py`
- Modify: `services/twinops/tests/storage/historical_repository_contract.py`

- [ ] **Step 1: Add the PostgreSQL fixture and expected failing contract**

Use only an authorized disposable `TEST_DATABASE_URL`; absence blocks Task 5 and cannot be recorded as skip/pass. Cleanup only the eight v3 tables in FK-safe order. Reuse the shared contract and add a two-thread activation race.

```python
with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(activate, (candidate_a, candidate_b)))
assert sum(result.activated for result in results) == 1
assert repository.count_active("forzy-motor-01") == 1
```

- [ ] **Step 2: Run RED**

```powershell
$serviceRoot = (Resolve-Path '.').Path
$worktreeRoot = (Resolve-Path "$serviceRoot\..\..").Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
if ([string]::IsNullOrWhiteSpace([string]$env:TEST_DATABASE_URL)) { throw 'Task A5 requires an authorized disposable TEST_DATABASE_URL; absence is not a skip/pass' }
$redOutput = @(& $python -m pytest -m postgres tests/storage/test_postgres_historical_repository_v1.py -q 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch [regex]::Escape('RED:A5:postgres-history-repository-missing') -or $redText -match '(?i)\bskipped\b|(?m)^(ERROR|INTERNALERROR)') { throw 'PostgreSQL RED did not fail on its exact executed assertion' }
$redOutput
```

Expected: FAIL only on the executed database assertion `RED:A5:postgres-history-repository-missing`, with zero skips. Missing authorization/URL blocks this task.

- [ ] **Step 3: Implement PostgreSQL parity**

Use psycopg `dict_row`. For stage, lock the deterministic batch key with `pg_advisory_xact_lock(hashtextextended(batch_id, 0))`. For activation, lock the asset key, reread active and target `FOR UPDATE`, apply compare-and-swap, and rely on the partial unique index as the final invariant. Never retry an expected-active mismatch as if it succeeded.

- [ ] **Step 4: Run GREEN**

```powershell
if ([string]::IsNullOrWhiteSpace([string]$env:TEST_DATABASE_URL)) { throw 'Task A5 GREEN requires an authorized disposable TEST_DATABASE_URL' }
$postgresGreenOutput = @(& $python -m pytest -m postgres tests/storage/test_postgres_historical_repository_v1.py -q -ra 2>&1)
$postgresGreenExit = $LASTEXITCODE
$postgresGreenText = $postgresGreenOutput -join "`n"
if ($postgresGreenExit -ne 0 -or $postgresGreenText -match '(?i)\bskipped\b' -or $postgresGreenText -notmatch '(?m)\b[1-9][0-9]* passed\b') { throw 'PostgreSQL GREEN requires at least one executed pass and zero skips' }
$postgresGreenOutput
```

Expected: shared contract and real PostgreSQL concurrency tests execute and PASS with zero skips.

- [ ] **Step 5: Commit**

```powershell
$expectedStagedPaths=@('services/twinops/src/twinops/storage/postgres_historical_repository_v1.py','services/twinops/tests/storage/test_postgres_historical_repository_v1.py','services/twinops/tests/storage/historical_repository_contract.py')
git add services/twinops/src/twinops/storage/postgres_historical_repository_v1.py services/twinops/tests/storage/test_postgres_historical_repository_v1.py services/twinops/tests/storage/historical_repository_contract.py
if ($LASTEXITCODE -ne 0) { throw 'staging PostgreSQL historical repository files failed' }
Assert-ExactStagedScopeV1 -Expected $expectedStagedPaths -Label 'Task A5'
git commit -m "feat: add postgres historical repository parity"
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL historical repository commit failed' }
```

### Task 6: Add a fail-closed administrative CLI

**Files:**

- Create: `scripts/history_admin.py`
- Create: `services/twinops/src/twinops/history_admin.py`
- Create: `services/twinops/src/twinops/security/local_write_guard_v1.py`
- Create: `services/twinops/src/twinops/security/admin_result_writer_v1.py`
- Create: `services/twinops/tests/test_history_admin.py`
- Create: `services/twinops/tests/security/test_local_write_guard_v1.py`
- Create: `services/twinops/tests/security/test_admin_result_writer_v1.py`

- [ ] **Step 1: Write failing preflight and sanitized-output tests**

Every subcommand requires `--environment local|preview|production`, `--expected-target-fingerprint sha256:...`, and `--expected-schema-version 003`. Every write-capable subcommand (`migrate-local`, `seed-collection-policy`, `stage-history`, `build-assessments` added in Phase B, and `activate-history`) requires exactly one of `--dry-run` and `--apply`; the read-only `show-active` and `verify-active` commands reject both flags. `migrate-local` is rejected unless `--environment local`, an absolute guarded `--database-path`, `--initial-policy-effective-from`, and `--allow-local-write` on apply are present; it is the only CLI surface allowed to create a new SQLite target. `seed-collection-policy` additionally requires `--effective-from` and uses the pinned `forzy-live-window-v1` object; it accepts no free-form policy JSON.

`stage-history` additionally requires an absolute `--input`, exact `--expected-sha256`, the registered `--profile`, and `--asset-id forzy-motor-01`. `activate-history` requires `--batch-id`, `--expected-source-sha256`, `--expected-manifest-sha256`, `--expected-assessment-manifest-sha256`, and `--expected-active-batch`; literal `none` is accepted only for the nullable expected assessment/active values. Activation rereads and matches all supplied identities before compare-and-swap. Every local database command requires an absolute guarded `--database-path`; a local apply additionally requires `--allow-local-write`. Preview/production reject `--database-path` and obtain `DATABASE_URL` from the environment only. `migrate-local`, `stage-history`, `build-assessments`, `activate-history`, `show-active`, and `verify-active` require an absolute `--result-json <path>` governed by the result boundary below, so automation never scrapes prose/stdout to discover IDs or manifests.

Test that wrong environment, fingerprint, schema version, profile, path, file hash, active batch, policy hash, policy validity, result path, or expected post-activation manifest fails before the first database write. Cover `migrate-local` fresh-target dry-run/apply, an already existing target, a missing/non-directory/reparse parent, apply without the explicit local-write flag, exact schema/policy reread, and a second migration no-op. Capture stdout/stderr and result files and assert they contain no DSN, username, host, absolute source/database path, CSV content, model bytes, or row payload.

The local write guard is normative and separately unit tested:

1. Reject relative, drive-relative, volume-root, UNC, and Windows device paths. The SQLite target's parent must already exist.
2. Establish allowed roots only as (a) the current worktree root derived from the checked-in launcher location, or (b) a directory created in this process by `create_attested_temp_dir()`. A caller-supplied temp path is never sufficient.
3. Walk every existing component using `lstat`; on Windows also reject `FILE_ATTRIBUTE_REPARSE_POINT`. Reject any symlink, junction, mount/reparse hop, non-directory parent, or non-regular existing target before resolving containment.
4. Resolve final component paths/handles, normalize Windows case and separators, and require `target.relative_to(allowed_root)` to succeed. String-prefix containment is forbidden.
5. An in-process temp permit contains an unexported random token, creator PID, canonical root, and directory identity (`st_dev/st_ino`, or Windows volume serial + file ID). Reattest all values on use; a copied/forged permit or replaced directory fails.
6. Immediately before `BEGIN` and again after opening SQLite, rewalk components and compare the final file/directory identity with the preflight permit. A parent/target replacement between preflight and open aborts before application DML.
7. Build the local target fingerprint as SHA-256 of canonical JSON containing exactly `kind="local-sqlite"`, normalized resolved `path`, `schemaVersion`, and the sorted `migrationHashes` map. A change in path, expected schema, or any SQL hash must change the fingerprint. `preflight_new_local_database(path, expected_schema_version)` exposes only this fingerprint to the controller after proving that the target is absent and its existing parent chain is contained, regular, and non-reparse; it never creates the file or prints the path payload.

Tests create real symlinks and, on Windows where permitted, a junction/reparse directory; they cover an external sibling path, lexical `..` escape, a symlinked file, a symlinked parent, a replaced parent race, an arbitrary system-temp directory, an attested same-process temp directory, a forged/stale permit, a valid regular file in the worktree, and fingerprint sensitivity to path/schema/migration hash. Privilege-gated junction creation may skip only that one case; mocked reparse attributes still run on every platform.

The admin result boundary is separate and exact. Derive `<worktree>` from the checked-in launcher, allow only a direct child named by `[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json` under `<worktree>/tmp/twinops-admin-results`, and reject every other `--result-json` path. The CLI may create the exact `tmp/twinops-admin-results` chain itself only after walking the worktree and every existing component with the same symlink/junction/reparse checks; it never accepts a caller-chosen root. Before and after serialization, reattest the root and any existing destination as regular/non-reparse. Write compact sorted-key UTF-8 JSON plus one LF to a same-directory random file opened with exclusive create, flush and `fsync`, then atomically `os.replace` the validated regular destination and `fsync` the directory where supported. Remove only the private temp file on failure. Tests cover an external path, nested child, wrong suffix/name, lexical escape, linked/reparse root or destination, replacement race, pre-existing regular result replacement, canonical byte stability, and no result file on preflight/transaction failure. A result-write failure after a committed apply returns a sanitized nonzero operational error without attempting compensation or a second transaction; a retry must be idempotent, reread the committed state, and reproduce the same IDs/manifests.

- [ ] **Step 2: Run RED**

```powershell
$serviceRoot = (Resolve-Path '.').Path
$worktreeRoot = (Resolve-Path "$serviceRoot\..\..").Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
$redOutput = @(& $python -m pytest tests/test_history_admin.py tests/security/test_local_write_guard_v1.py tests/security/test_admin_result_writer_v1.py -q 2>&1)
$redExit = $LASTEXITCODE
$redText = $redOutput -join "`n"
if ($redExit -ne 1 -or $redText -notmatch [regex]::Escape('RED:A6:history-admin-missing') -or $redText -match '(?m)^(ERROR|INTERNALERROR)') { throw 'history admin RED did not fail on its exact assertion' }
$redOutput
```

Expected: FAIL only on `RED:A6:history-admin-missing`.

- [ ] **Step 3: Implement target fingerprint and command flow**

Canonical target fingerprints use:

- local: the guarded canonical payload containing resolved database path, expected schema version, and current migration hashes defined above;
- preview/production: operator-provided non-secret project and branch IDs plus SQL `current_database()` and `current_schema()`, serialized canonically and hashed.

The local staged handoff is revalidated through a pure read-only boundary, not by trusting prior result JSON:

```python
def preflight_new_local_database(
    path: Path,
    *,
    expected_schema_version: str,
) -> Sha256V1: ...

def reattest_local_staged_handoff(
    path: Path,
    *,
    expected_target_fingerprint: Sha256V1,
    expected_schema_version: str,
    expected_batch_id: Sha256V1,
    expected_source_sha256: Sha256V1,
    expected_manifest_sha256: Sha256V1,
    expected_raw_row_count: int,
    expected_sample_count: int,
    expected_operating_cycle_count: int,
    require_no_active_batch: bool,
) -> None: ...
```

`reattest_local_staged_handoff` rewalks the guarded path, opens SQLite with `mode=ro` and query-only semantics, verifies migration identities/hashes and the recomputed target fingerprint, requires the named batch to remain `staged`, reconstructs the source bytes from immutable raw rows, recomputes the source and manifest hashes/counts, and—when requested—requires no active batch. It produces no stdout, result file, DDL, DML, journal, or path-bearing exception. Its tests snapshot the database bytes before/after and prove equality, rejection of a replaced/reparse target, wrong handoff fields, a non-staged batch, any active batch, malformed stored rows, and reconstruction/hash/count divergence.

The operator provides project/branch IDs through `TWINOPS_TARGET_PROJECT_ID` and `TWINOPS_TARGET_BRANCH_ID`; the CLI never infers them from a DSN. `deployment_identity_v1` must contain the same environment, label, fingerprint, and schema version before stage/activate begins. The initial migration command binds that row only inside the separately authorized migration transaction.

`migrate-local` applies only the registered SQLite migration set and initial pinned collection policy. Its flat result contains exactly `command="migrate-local"`, `mode`, `environment="local"`, `targetFingerprint`, `schemaVersion`, `migrationManifestSha256`, `initialPolicyId`, `initialPolicyConfigurationHash`, `appliedMigrationCount`, `policyInserted`, and `writesPerformed`. Dry-run proves the absent target/parent/fingerprint and reports `writesPerformed=0`; apply creates only the guarded target, rereads exact migration hashes/schema/policy after commit, and writes the sanitized result. It cannot stage or activate a batch.

Freeze the executable preview command surfaces (PowerShell variables contain already approved values and absolute paths):

```powershell
$worktreeRoot = (Resolve-Path '.').Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
& $python -c "import sys, twinops, pathlib; assert sys.version_info[:2] == (3, 12); assert pathlib.Path(twinops.__file__).resolve().is_relative_to(pathlib.Path.cwd().resolve())"
if ($LASTEXITCODE -ne 0) { throw 'preview admin Python provenance failed' }
& $python scripts/history_admin.py stage-history --environment preview --expected-target-fingerprint $targetFingerprint --expected-schema-version 003 --dry-run --input $historyCsv --expected-sha256 $historySha256 --profile forzy-history-2026-05-19-v1 --asset-id forzy-motor-01 --result-json $stageDryRunResult
if ($LASTEXITCODE -ne 0) { throw 'preview stage dry-run failed' }
& $python scripts/history_admin.py stage-history --environment preview --expected-target-fingerprint $targetFingerprint --expected-schema-version 003 --apply --input $historyCsv --expected-sha256 $historySha256 --profile forzy-history-2026-05-19-v1 --asset-id forzy-motor-01 --result-json $stageApplyResult
if ($LASTEXITCODE -ne 0) { throw 'preview stage apply failed' }
& $python scripts/history_admin.py activate-history --environment preview --expected-target-fingerprint $targetFingerprint --expected-schema-version 003 --dry-run --asset-id forzy-motor-01 --batch-id $batchId --expected-source-sha256 $historySha256 --expected-manifest-sha256 $historyManifestSha256 --expected-assessment-manifest-sha256 $assessmentManifestSha256 --expected-active-batch $expectedActiveBatch --result-json $activateDryRunResult
if ($LASTEXITCODE -ne 0) { throw 'preview activation dry-run failed' }
& $python scripts/history_admin.py activate-history --environment preview --expected-target-fingerprint $targetFingerprint --expected-schema-version 003 --apply --asset-id forzy-motor-01 --batch-id $batchId --expected-source-sha256 $historySha256 --expected-manifest-sha256 $historyManifestSha256 --expected-assessment-manifest-sha256 $assessmentManifestSha256 --expected-active-batch $expectedActiveBatch --result-json $activateApplyResult
if ($LASTEXITCODE -ne 0) { throw 'preview activation apply failed' }
```

`stage-history` writes the exact flat shape `command="stage-history"`, `mode`, `environment`, `targetFingerprint`, `schemaVersion`, `assetId`, `batchId`, `sourceSha256`, `manifestSha256`, `rawRowCount`, `sampleCount`, `operatingCycleCount`, `inserted`, and `writesPerformed`. `activate-history` writes exactly `command="activate-history"`, `mode`, `environment`, `targetFingerprint`, `schemaVersion`, `assetId`, `batchId`, `previousActiveBatchId`, `activeBatchId`, `sourceSha256`, `manifestSha256`, `assessmentManifestSha256`, `rawRowCount`, `sampleCount`, `operatingCycleCount`, `assessmentCount`, `activated`, and `writesPerformed`. Dry-run uses the same shape with predicted IDs/counts and `writesPerformed=0`; apply values are reread after commit before the atomic result write.

Post-activation inspection is read-only and executable:

```powershell
$worktreeRoot = (Resolve-Path '.').Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
& $python -c "import sys, twinops, pathlib; assert sys.version_info[:2] == (3, 12); assert pathlib.Path(twinops.__file__).resolve().is_relative_to(pathlib.Path.cwd().resolve())"
if ($LASTEXITCODE -ne 0) { throw 'post-activation Python provenance failed' }
& $python scripts/history_admin.py show-active --environment preview --expected-target-fingerprint $targetFingerprint --expected-schema-version 003 --asset-id forzy-motor-01 --result-json $showActiveResult
if ($LASTEXITCODE -ne 0) { throw 'show-active failed' }
& $python scripts/history_admin.py verify-active --environment preview --expected-target-fingerprint $targetFingerprint --expected-schema-version 003 --asset-id forzy-motor-01 --expected-batch-id $batchId --expected-source-sha256 $historySha256 --expected-manifest-sha256 $historyManifestSha256 --expected-assessment-manifest-sha256 $assessmentManifestSha256 --result-json $verifyActiveResult
if ($LASTEXITCODE -ne 0) { throw 'verify-active failed' }
```

Neither read-only command accepts a mode flag or begins a write transaction. `show-active` writes exactly `command="show-active"`, `environment`, `targetFingerprint`, `schemaVersion`, `assetId`, `activeBatchId`, `sourceSha256`, `manifestSha256`, `assessmentManifestSha256`, `rawRowCount`, `sampleCount`, `operatingCycleCount`, and `assessmentCount`, using null batch/hash fields and zero counts when no active batch exists. `verify-active` rereads identity/schema/migration hashes, the active batch, immutable counts, source/manifest/assessment manifests, and policy validity; it exits nonzero before writing a success result on any mismatch. On success it writes the same fields plus `command="verify-active"` and `verified=true`.

Public entry points are injectable for tests:

```python
def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    clock: Callable[[], datetime] = utc_now,
    repository_factory: RepositoryFactory = repository_from_target,
) -> int: ...
```

Dry-run fully reads/parses/hashes the file, validates the local write permit when applicable, and reads target state but performs no DDL or DML. Apply repeats target, policy, and local-path attestation immediately before `BEGIN` and after database open. Each command validates its exact result model, emits the same sanitized canonical JSON on stdout, and writes those exact bytes through `AdminResultWriterV1`; unknown/extra output keys fail closed.

- [ ] **Step 4: Run GREEN**

Expected: CLI and guard tests PASS, including explicit no-write spy assertions and all non-privilege-gated containment/reparse cases.

- [ ] **Step 5: Commit**

```powershell
$expectedStagedPaths=@('scripts/history_admin.py','services/twinops/src/twinops/history_admin.py','services/twinops/src/twinops/security/local_write_guard_v1.py','services/twinops/src/twinops/security/admin_result_writer_v1.py','services/twinops/tests/test_history_admin.py','services/twinops/tests/security/test_local_write_guard_v1.py','services/twinops/tests/security/test_admin_result_writer_v1.py')
git add scripts/history_admin.py services/twinops/src/twinops/history_admin.py services/twinops/src/twinops/security/local_write_guard_v1.py services/twinops/src/twinops/security/admin_result_writer_v1.py services/twinops/tests/test_history_admin.py services/twinops/tests/security/test_local_write_guard_v1.py services/twinops/tests/security/test_admin_result_writer_v1.py
if ($LASTEXITCODE -ne 0) { throw 'staging history admin files failed' }
Assert-ExactStagedScopeV1 -Expected $expectedStagedPaths -Label 'Task A6'
git commit -m "feat: add safe historical administration commands"
if ($LASTEXITCODE -ne 0) { throw 'history admin commit failed' }
```

### Task 7: Prove the registered real file and complete regression

**Files:**

- Create: `services/twinops/tests/ingestion/test_real_historical_import_v1.py`
- Modify: `services/twinops/pyproject.toml`
- Create: `docs/verification/phase-a-findings.json`
- Modify, never recreate: `docs/verification/unified-twin-acceptance-v1.json`
- Regenerate, never hand-edit: `docs/verification/unified-twin-acceptance-v1.md`

- [ ] **Step 1: Add a marked, opt-in real-file test**

Register marker `real_history`. Read `TWINOPS_FORZY_HISTORY_CSV` only; require an absolute regular file outside deploy outputs. Skip when absent. Never print the path.

```python
@pytest.mark.real_history
def test_registered_forzy_file_matches_audited_counts(monkeypatch):
    source = _controller_file_from_env()
    prepared = prepare_historical_batch(
        source.read_bytes(),
        profile=registered_profile("forzy-history-2026-05-19-v1"),
        asset_id="forzy-motor-01",
        ingested_at=datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
    )
    assert len(prepared.raw_rows) == 7_183
    assert len(prepared.samples) == 14_366
    assert len({sample.reading.operating_cycle_id for sample in prepared.samples}) == 204
    assert prepared.source_sha256 == "sha256:f09a6613bf6ba3416555a15de6b381bd842474f5f3f33c20660416c7164f0be4"
```

- [ ] **Step 2: Run the normal suite**

```powershell
$serviceRoot = (Resolve-Path '.').Path
$worktreeRoot = (Resolve-Path "$serviceRoot\..\..").Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Phase A full Python regression failed' }
```

Expected: PASS; real-history test SKIP when the environment variable is absent.

- [ ] **Step 3: Run the opt-in proof with a controller-provided path**

```powershell
$serviceRoot = (Resolve-Path '.').Path
$worktreeRoot = (Resolve-Path "$serviceRoot\..\..").Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
$controllerCsvPath = Read-Host 'Absolute path to the controller-provided Forzy CSV'
$env:TWINOPS_FORZY_HISTORY_CSV = [System.IO.Path]::GetFullPath($controllerCsvPath)
$realHistoryExit = 1
try {
  & $python -m pytest -m real_history tests/ingestion/test_real_historical_import_v1.py -q
  $realHistoryExit = $LASTEXITCODE
} finally {
  Remove-Item Env:TWINOPS_FORZY_HISTORY_CSV -ErrorAction SilentlyContinue
}
if ($realHistoryExit -ne 0) { throw 'registered real-history proof failed' }
```

Expected: PASS with `7_183`, `14_366`, and `204` invariants. This is local read-only validation, not authorization to stage any database.

- [ ] **Step 4: Run the JavaScript contract suite**

From repository root:

```powershell
npm.cmd run test:run -- --exclude "**/.pytest_cache/**" src/contracts/schemaTimelineV1.test.js src/contracts/timelineV1.test.js
if ($LASTEXITCODE -ne 0) { throw 'Phase A JavaScript contract regression failed' }
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
$expectedStagedPaths=@('services/twinops/tests/ingestion/test_real_historical_import_v1.py','services/twinops/pyproject.toml')
git add services/twinops/tests/ingestion/test_real_historical_import_v1.py services/twinops/pyproject.toml
if ($LASTEXITCODE -ne 0) { throw 'staging real-history proof files failed' }
Assert-ExactStagedScopeV1 -Expected $expectedStagedPaths -Label 'Task A7 code'
git commit -m "test: prove audited Forzy history profile"
if ($LASTEXITCODE -ne 0) { throw 'real-history proof commit failed' }
```

- [ ] **Step 6: After a separate authorization, stage the real file into one disposable guarded SQLite database**

This is a distinct local-write gate. Passing the read-only real-file test, approving any remote operation, or approving the plan does not satisfy it. The controller must set the exact one-shot approval token and an audited initial-policy instant; this step writes only a new ignored SQLite file and sanitized ignored result JSON below this worktree's `tmp/`. It never runs `activate-history`, never writes preview/production, and deliberately preserves the final database for Phase B.

Run from the worktree root only after the Step 5 commit leaves the tracked/untracked worktree clean:

```powershell
$worktreeRoot = (Resolve-Path '.').Path
$python = (Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH = "$worktreeRoot\services\twinops\src;$worktreeRoot"
if ($env:TWINOPS_APPROVE_LOCAL_HISTORY_PROOF -ne 'phase-a-local-sqlite-stage-v1') { throw 'separate disposable SQLite stage authorization required' }
$initialPolicyEffectiveFrom = [string]$env:TWINOPS_LOCAL_INITIAL_POLICY_EFFECTIVE_FROM
if ($initialPolicyEffectiveFrom -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$') { throw 'audited canonical initial-policy instant required' }
$localProofCodeCommit = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $localProofCodeCommit -notmatch '^[0-9a-f]{40}$') { throw 'cannot freeze local proof code commit' }
$statusBeforeLocalProof = @(git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $statusBeforeLocalProof.Count -ne 0) { throw 'local proof requires a clean committed code SHA' }

$controllerCsv = [System.IO.Path]::GetFullPath([string]$env:TWINOPS_FORZY_HISTORY_CSV)
$csvItem = Get-Item -LiteralPath $controllerCsv -Force
if (-not $csvItem.PSIsContainer -and (($csvItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0)) { $csvRegular = $true } else { $csvRegular = $false }
$historySha256 = 'sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath $controllerCsv).Hash.ToLowerInvariant()
if (-not $csvRegular -or $historySha256 -ne 'sha256:f09a6613bf6ba3416555a15de6b381bd842474f5f3f33c20660416c7164f0be4') { throw 'registered controller CSV required' }

$proofNonce = [Guid]::NewGuid().ToString('N')
$localDatabaseRelative = "tmp/twinops-local-proof/$proofNonce/history.sqlite3"
git check-ignore --quiet -- $localDatabaseRelative
if ($LASTEXITCODE -ne 0) { throw 'local proof database path must already be ignored' }
$worktreeItem = Get-Item -LiteralPath $worktreeRoot -Force
if (-not $worktreeItem.PSIsContainer -or (($worktreeItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw 'worktree root is not a regular non-reparse directory' }
$tmpRoot = Join-Path $worktreeRoot 'tmp'
if (Test-Path -LiteralPath $tmpRoot) {
  $tmpItem = Get-Item -LiteralPath $tmpRoot -Force
  if (-not $tmpItem.PSIsContainer -or (($tmpItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw 'worktree tmp root is not a regular directory' }
} else {
  New-Item -ItemType Directory -Path $tmpRoot | Out-Null
}
$proofParent = Join-Path $tmpRoot 'twinops-local-proof'
if (Test-Path -LiteralPath $proofParent) {
  $proofParentItem = Get-Item -LiteralPath $proofParent -Force
  if (-not $proofParentItem.PSIsContainer -or (($proofParentItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw 'local proof parent is not a regular directory' }
} else {
  New-Item -ItemType Directory -Path $proofParent | Out-Null
}
$proofRoot = Join-Path $proofParent $proofNonce
if (Test-Path -LiteralPath $proofRoot) { throw 'local proof directory must be new' }
New-Item -ItemType Directory -Path $proofRoot | Out-Null
$proofRootItem = Get-Item -LiteralPath $proofRoot -Force
if (($proofRootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'local proof directory is reparse-backed' }
$localDatabasePath = Join-Path $proofRoot 'history.sqlite3'
if (Test-Path -LiteralPath $localDatabasePath) { throw 'local database target must be new' }

$localTargetFingerprint = (& $python -c "from pathlib import Path; import sys; from twinops.history_admin import preflight_new_local_database; print(preflight_new_local_database(Path(sys.argv[1]), expected_schema_version=sys.argv[2]))" $localDatabasePath '003').Trim()
if ($LASTEXITCODE -ne 0 -or $localTargetFingerprint -notmatch '^sha256:[0-9a-f]{64}$') { throw 'guarded local target preflight failed' }
$migrationApplyResult = Join-Path $worktreeRoot "tmp\twinops-admin-results\phase-a-local-migrate-$proofNonce.json"
$stageApplyResult = Join-Path $worktreeRoot "tmp\twinops-admin-results\phase-a-local-stage-$proofNonce.json"
$stageNoopResult = Join-Path $worktreeRoot "tmp\twinops-admin-results\phase-a-local-stage-noop-$proofNonce.json"

& $python scripts/history_admin.py migrate-local --environment local --expected-target-fingerprint $localTargetFingerprint --expected-schema-version 003 --apply --allow-local-write --database-path $localDatabasePath --initial-policy-effective-from $initialPolicyEffectiveFrom --result-json $migrationApplyResult
if ($LASTEXITCODE -ne 0) { throw 'guarded local migration failed' }
$databaseItem = Get-Item -LiteralPath $localDatabasePath -Force
if ($databaseItem.PSIsContainer -or (($databaseItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw 'migration did not create one regular SQLite file' }

& $python scripts/history_admin.py stage-history --environment local --expected-target-fingerprint $localTargetFingerprint --expected-schema-version 003 --apply --allow-local-write --database-path $localDatabasePath --input $controllerCsv --expected-sha256 $historySha256 --profile forzy-history-2026-05-19-v1 --asset-id forzy-motor-01 --result-json $stageApplyResult
if ($LASTEXITCODE -ne 0) { throw 'first guarded local stage failed' }
$stageApply = Get-Content -Raw -LiteralPath $stageApplyResult | ConvertFrom-Json
if ($stageApply.command -ne 'stage-history' -or $stageApply.mode -ne 'apply' -or $stageApply.environment -ne 'local' -or $stageApply.targetFingerprint -ne $localTargetFingerprint -or -not $stageApply.inserted -or [int]$stageApply.writesPerformed -le 0 -or [int]$stageApply.rawRowCount -ne 7183 -or [int]$stageApply.sampleCount -ne 14366 -or [int]$stageApply.operatingCycleCount -ne 204 -or $stageApply.sourceSha256 -ne $historySha256) { throw 'first stage result invariants failed' }
$localBatchId = [string]$stageApply.batchId
$localManifestSha256 = [string]$stageApply.manifestSha256

& $python -c "from pathlib import Path; import sys; from twinops.history_admin import reattest_local_staged_handoff; reattest_local_staged_handoff(Path(sys.argv[1]), expected_target_fingerprint=sys.argv[2], expected_schema_version='003', expected_batch_id=sys.argv[3], expected_source_sha256=sys.argv[4], expected_manifest_sha256=sys.argv[5], expected_raw_row_count=7183, expected_sample_count=14366, expected_operating_cycle_count=204, require_no_active_batch=True)" $localDatabasePath $localTargetFingerprint $localBatchId $historySha256 $localManifestSha256
if ($LASTEXITCODE -ne 0) { throw 'post-stage reconstruction/hash/count reattestation failed' }

& $python scripts/history_admin.py stage-history --environment local --expected-target-fingerprint $localTargetFingerprint --expected-schema-version 003 --apply --allow-local-write --database-path $localDatabasePath --input $controllerCsv --expected-sha256 $historySha256 --profile forzy-history-2026-05-19-v1 --asset-id forzy-motor-01 --result-json $stageNoopResult
if ($LASTEXITCODE -ne 0) { throw 'second guarded local stage failed' }
$stageNoop = Get-Content -Raw -LiteralPath $stageNoopResult | ConvertFrom-Json
foreach ($field in @('targetFingerprint','schemaVersion','assetId','batchId','sourceSha256','manifestSha256','rawRowCount','sampleCount','operatingCycleCount')) {
  if ($stageNoop.$field -ne $stageApply.$field) { throw "second stage changed $field" }
}
if ($stageNoop.command -ne 'stage-history' -or $stageNoop.mode -ne 'apply' -or $stageNoop.environment -ne 'local' -or $stageNoop.inserted -or [int]$stageNoop.writesPerformed -ne 0) { throw 'second stage was not an exact no-op' }
& $python -c "from pathlib import Path; import sys; from twinops.history_admin import reattest_local_staged_handoff; reattest_local_staged_handoff(Path(sys.argv[1]), expected_target_fingerprint=sys.argv[2], expected_schema_version='003', expected_batch_id=sys.argv[3], expected_source_sha256=sys.argv[4], expected_manifest_sha256=sys.argv[5], expected_raw_row_count=7183, expected_sample_count=14366, expected_operating_cycle_count=204, require_no_active_batch=True)" $localDatabasePath $localTargetFingerprint $localBatchId $historySha256 $localManifestSha256
if ($LASTEXITCODE -ne 0) { throw 'post-no-op staged database reattestation failed' }
$proofDirectoryEntries=@(Get-ChildItem -LiteralPath $proofRoot -Force | ForEach-Object { $_.Name })
Assert-ExactStringListV1 -Expected @('history.sqlite3') -Actual @($proofDirectoryEntries) -Label 'local proof directory inventory'

$runtimeFiles = @($localDatabasePath,$migrationApplyResult,$stageApplyResult,$stageNoopResult)
foreach ($runtimeFile in $runtimeFiles) {
  $runtimeRelative = Get-WorktreeRelativePathV1 -Root $worktreeRoot -Child ([IO.Path]::GetFullPath($runtimeFile))
  git check-ignore --quiet -- $runtimeRelative
  Assert-NativeExit $LASTEXITCODE 'local proof ignore check'
  git ls-files --error-unmatch -- $runtimeRelative *> $null
  $trackedLookupExit = $LASTEXITCODE
  if ($trackedLookupExit -ne 1) { throw "local proof tracking probe expected exact untracked exit 1, got $trackedLookupExit" }
}
$statusAfterLocalProof = @(git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $statusAfterLocalProof.Count -ne 0) { throw 'local proof changed the committed worktree' }
$headAfterLocalProof = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $headAfterLocalProof -ne $localProofCodeCommit) { throw 'local proof changed the committed code SHA' }

$phaseALocalProofHandoff = [ordered]@{
  schemaVersion='1.0'; kind='phase-a-local-staged-history-handoff'; localProofCodeCommit=$localProofCodeCommit
  targetFingerprint=$localTargetFingerprint; databaseContentSha256=('sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath $localDatabasePath).Hash.ToLowerInvariant())
  batchId=$localBatchId; sourceSha256=$historySha256; reconstructedSourceSha256=$historySha256; manifestSha256=$localManifestSha256
  rawRowCount=7183; sampleCount=14366; operatingCycleCount=204; activeBatchId=$null
  migrationResultSha256=('sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath $migrationApplyResult).Hash.ToLowerInvariant())
  stageApplyResultSha256=('sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath $stageApplyResult).Hash.ToLowerInvariant())
  stageNoopResultSha256=('sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath $stageNoopResult).Hash.ToLowerInvariant())
  stageApplyInserted=$true; stageApplyWritesPerformed=[int]$stageApply.writesPerformed; stageNoopInserted=$false; stageNoopWritesPerformed=0
}
Remove-Item Env:TWINOPS_FORZY_HISTORY_CSV
```

The controller retains `$localDatabasePath` privately and transfers it to B only as the process-local `TWINOPS_PHASE_A_LOCAL_DB_PATH`; it is never printed, serialized into the handoff, committed, uploaded, or placed in review/ledger evidence. Transfer `$phaseALocalProofHandoff` separately as `TWINOPS_PHASE_A_LOCAL_PROOF_JSON`; its exact closed fields are those constructed above and contain no path, CSV bytes, source timestamp/row, DSN, or credential. Keep the ignored database and three ignored results intact through Phase B. If code changes after this proof, rerun the entire gate against a new nonce/new database and discard the old handoff; a proof bound to an earlier code SHA is invalid.

- [ ] **Step 7: Obtain independent review on the exact implementation SHA and local staged proof**

Freeze `$phaseAVerifiedCodeCommit = (git rev-parse HEAD).Trim()` and require it to equal `phaseALocalProofHandoff.localProofCodeCommit`. An independent reviewer checks every Phase A finding and acceptance criterion against that exact code commit, including policy hash/seed/read behavior, migration idempotency, local write containment/reparse tests, immutable archive storage, unchanged live tables, the separately authorized local migration, exact first stage, byte reconstruction/hash/counts, second-stage no-op, absence of activation, ignored-artifact containment, and every sanitized handoff/result hash. Store the closed findings report at `docs/verification/phase-a-findings.json` in the strict `finding-review-v1` shape with `plan="A"`, `reviewedSha=$phaseAVerifiedCodeCommit`, verdict and findings. Do not mark pass with any open Critical/Important; `accepted` is legal only for a Minor finding with rationale. Fix every other open finding, rerun affected/full gates, commit, rerun Step 6 against a fresh database, and repeat review on the new code commit.

- [ ] **Step 8: Update the cumulative acceptance ledger through its CLI**

The ledger/verifier are bootstrapped by integrated validation Task 1 before Phase A starts. After the A worker hands the exact review report and `$phaseAVerifiedCodeCommit` to the execution-index integrator, only that integrator runs this step serially; never hand-edit either ledger rendering, discard earlier findings, or let another phase mutate the files concurrently. The integrator preserves this SHA under the phase-specific name `phaseAVerifiedCodeCommit` and the controller re-exports it as `PHASE_A_VERIFIED_CODE_COMMIT` for Step 9; a generic or newly derived replacement is forbidden.

```powershell
$worktreeRoot=(Resolve-Path '.').Path
$python=(Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH="$worktreeRoot\services\twinops\src;$worktreeRoot"
$phaseAVerifiedCodeCommit=(git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $phaseAVerifiedCodeCommit -notmatch '^[0-9a-f]{40}$') { throw 'cannot freeze phaseAVerifiedCodeCommit' }
$review=(Get-Content -Raw -Encoding utf8 -LiteralPath docs/verification/phase-a-findings.json | ConvertFrom-Json)
$expectedReviewKeys=@('findings','plan','reviewedSha','schemaVersion','verdict')
$actualReviewKeys=@($review.PSObject.Properties.Name)
Assert-ExactStringListV1 -Expected $expectedReviewKeys -Actual $actualReviewKeys -Label 'phase A review root shape'
Assert-ExactStringListV1 -Expected @('critical','important','minor') -Actual @($review.verdict.PSObject.Properties.Name) -Label 'phase A review verdict shape'
$reviewVerdict=@([int]$review.verdict.critical,[int]$review.verdict.important,[int]$review.verdict.minor)
if ($review.schemaVersion -cne 'finding-review-v1' -or $review.plan -cne 'A' -or $review.reviewedSha -cne $phaseAVerifiedCodeCommit -or $reviewVerdict[0] -ne 0 -or $reviewVerdict[1] -ne 0 -or $reviewVerdict[2] -lt 0) { throw 'phase A review identity/count verdict mismatch' }
& $python scripts/verify_unified_acceptance.py ingest-review --ledger docs/verification/unified-twin-acceptance-v1.json --review-report docs/verification/phase-a-findings.json
if ($LASTEXITCODE -ne 0) { throw 'phase A review ingestion failed' }
& $python scripts/verify_unified_acceptance.py update-criterion --ledger docs/verification/unified-twin-acceptance-v1.json --criterion AC-06 --status passed --evidence-kind database --evidence-ref docs/verification/phase-a-findings.json --verified-code-commit $phaseAVerifiedCodeCommit
if ($LASTEXITCODE -ne 0) { throw 'AC-06 ledger update failed' }
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'phase A ledger render failed' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'phase A ledger verification failed' }
$ledgerAfterA=Get-Content -Raw -Encoding utf8 docs/verification/unified-twin-acceptance-v1.json | ConvertFrom-Json
$ac06=@($ledgerAfterA.criteria | Where-Object { $_.criterionId -eq 'AC-06' })
$ledgerReviewVerdict=@($ledgerAfterA.plans.A.reviewVerdict | ForEach-Object { [int]$_ })
if ($ledgerAfterA.plans.A.verifiedCodeCommit -cne $phaseAVerifiedCodeCommit -or $ledgerReviewVerdict.Count -ne 3 -or $ledgerReviewVerdict[0] -ne $reviewVerdict[0] -or $ledgerReviewVerdict[1] -ne $reviewVerdict[1] -or $ledgerReviewVerdict[2] -ne $reviewVerdict[2] -or $ac06.Count -ne 1 -or $ac06[0].ownerPlan -ne 'A' -or $ac06[0].status -ne 'passed' -or $ac06[0].evidenceKind -ne 'database' -or $ac06[0].verifiedCodeCommit -cne $phaseAVerifiedCodeCommit -or $ac06[0].evidenceRefs -notcontains 'docs/verification/phase-a-findings.json') { throw 'phase A ledger postcondition mismatch' }
$env:PHASE_A_VERIFIED_CODE_COMMIT=$phaseAVerifiedCodeCommit
```

Only `ingest-review` may mutate the plan review record; only `update-criterion` may mutate AC-06. They reject a report whose `reviewedSha` differs from `$phaseAVerifiedCodeCommit`, any criterion whose frozen `ownerPlan` is not `A`, evidence attached to the wrong `gate`, an evidence kind outside `allowedEvidenceKinds`, a removed cumulative finding, or `accepted` on non-Minor severity. Expected: atomic updates preserve plans B-E and all cumulative finding IDs, plan A records `verifiedCodeCommit` (never HEAD or the later evidence commit), AC-06 is closed by database evidence on that same SHA, generated Markdown matches the JSON byte-for-byte, and verification reports zero open Critical/Important for plan A.

- [ ] **Step 9: Commit only the reviewed Phase A evidence**

```powershell
$worktreeRoot=(Resolve-Path '.').Path
$python=(Resolve-Path "$worktreeRoot\..\..\services\twinops\.venv\Scripts\python.exe").Path
$env:PYTHONPATH="$worktreeRoot\services\twinops\src;$worktreeRoot"
$phaseAVerifiedCodeCommit=[string]$env:PHASE_A_VERIFIED_CODE_COMMIT
if ($phaseAVerifiedCodeCommit -notmatch '^[0-9a-f]{40}$') { throw 'preserved phaseAVerifiedCodeCommit required' }
$headBeforeAEvidence=(git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $headBeforeAEvidence -cne $phaseAVerifiedCodeCommit) { throw 'HEAD differs from preserved phaseAVerifiedCodeCommit' }
$review=Get-Content -Raw -Encoding utf8 docs/verification/phase-a-findings.json | ConvertFrom-Json
$ledger=Get-Content -Raw -Encoding utf8 docs/verification/unified-twin-acceptance-v1.json | ConvertFrom-Json
$ac06=@($ledger.criteria | Where-Object { $_.criterionId -eq 'AC-06' })
Assert-ExactStringListV1 -Expected @('findings','plan','reviewedSha','schemaVersion','verdict') -Actual @($review.PSObject.Properties.Name) -Label 'phase A review root shape before evidence commit'
Assert-ExactStringListV1 -Expected @('critical','important','minor') -Actual @($review.verdict.PSObject.Properties.Name) -Label 'phase A review verdict shape before evidence commit'
$reviewVerdict=@([int]$review.verdict.critical,[int]$review.verdict.important,[int]$review.verdict.minor)
$ledgerReviewVerdict=@($ledger.plans.A.reviewVerdict | ForEach-Object { [int]$_ })
if ($review.schemaVersion -cne 'finding-review-v1' -or $review.plan -cne 'A' -or $review.reviewedSha -cne $phaseAVerifiedCodeCommit -or $reviewVerdict[0] -ne 0 -or $reviewVerdict[1] -ne 0 -or $reviewVerdict[2] -lt 0 -or $ledgerReviewVerdict.Count -ne 3 -or $ledgerReviewVerdict[0] -ne $reviewVerdict[0] -or $ledgerReviewVerdict[1] -ne $reviewVerdict[1] -or $ledgerReviewVerdict[2] -ne $reviewVerdict[2] -or $ledger.plans.A.verifiedCodeCommit -cne $phaseAVerifiedCodeCommit -or $ac06.Count -ne 1 -or $ac06[0].ownerPlan -ne 'A' -or $ac06[0].status -ne 'passed' -or $ac06[0].evidenceKind -ne 'database' -or $ac06[0].verifiedCodeCommit -cne $phaseAVerifiedCodeCommit -or $ac06[0].evidenceRefs -notcontains 'docs/verification/phase-a-findings.json') { throw 'phase A review/ledger pre-commit mismatch' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'phase A ledger pre-commit verification failed' }
$expectedAEvidencePaths=@(
  'docs/verification/phase-a-findings.json',
  'docs/verification/unified-twin-acceptance-v1.json',
  'docs/verification/unified-twin-acceptance-v1.md'
) | Sort-Object
$phaseAFindingsSha256='sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath 'docs/verification/phase-a-findings.json').Hash.ToLowerInvariant()
$phaseALedgerJsonSha256='sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.json').Hash.ToLowerInvariant()
$phaseALedgerMarkdownSha256='sha256:' + (Get-FileHash -Algorithm SHA256 -LiteralPath 'docs/verification/unified-twin-acceptance-v1.md').Hash.ToLowerInvariant()
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'phase A evidence diff check failed' }
git add docs/verification/phase-a-findings.json docs/verification/unified-twin-acceptance-v1.json docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'staging phase A evidence failed' }
$stagedAEvidencePaths=@(git diff --cached --name-only) | Sort-Object
$stagedAEvidenceExit=$LASTEXITCODE
Assert-NativeExit $stagedAEvidenceExit 'phase A staged evidence path read'
Assert-ExactStringListV1 -Expected $expectedAEvidencePaths -Actual @($stagedAEvidencePaths) -Label 'phase A staged evidence scope'
$unstagedAPaths=@(git diff --name-only)
if ($LASTEXITCODE -ne 0 -or $unstagedAPaths.Count -ne 0) { throw 'unstaged changes remain before phase A evidence commit' }
$untrackedAPaths=@(git ls-files --others --exclude-standard)
if ($LASTEXITCODE -ne 0 -or $untrackedAPaths.Count -ne 0) { throw 'untracked material remains before phase A evidence commit' }
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'phase A staged evidence diff check failed' }
git commit -m "docs: record reviewed phase A evidence"
if ($LASTEXITCODE -ne 0) { throw 'phase A evidence commit failed' }
$phaseAEvidenceCommit=(git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $phaseAEvidenceCommit -notmatch '^[0-9a-f]{40}$') { throw 'cannot resolve phaseAEvidenceCommit' }
$actualAEvidencePaths=@(git diff --name-only "$phaseAVerifiedCodeCommit..$phaseAEvidenceCommit") | Sort-Object
$actualAEvidenceExit=$LASTEXITCODE
Assert-NativeExit $actualAEvidenceExit 'Phase A evidence commit path read'
Assert-ExactStringListV1 -Expected $expectedAEvidencePaths -Actual @($actualAEvidencePaths) -Label 'Phase A evidence commit scope'
$phaseAEvidenceProjectionScript='import base64,hashlib,json,subprocess,sys; c=base64.b64decode(sys.argv[2]).decode(); ps=json.loads(base64.b64decode(sys.argv[3]).decode()); blobs={p:subprocess.run(["git","show",c+":"+p],check=True,stdout=subprocess.PIPE).stdout for p in ps}; review=json.loads(blobs["docs/verification/phase-a-findings.json"]); ledger=json.loads(blobs["docs/verification/unified-twin-acceptance-v1.json"]); ac=[x for x in ledger["criteria"] if x["criterionId"]=="AC-06"]; print(json.dumps({"digests":{p:"sha256:"+hashlib.sha256(blobs[p]).hexdigest() for p in ps},"review":review,"planA":ledger["plans"]["A"],"ac06":ac},sort_keys=True,separators=(",",":")))'
$pythonBase64Launcher='import base64,sys;exec(base64.b64decode(sys.argv[1]).decode())'
$phaseAEvidenceProjectionScriptBase64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($phaseAEvidenceProjectionScript))
$phaseAEvidenceCommitBase64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($phaseAEvidenceCommit))
$phaseAEvidencePathsJson=($expectedAEvidencePaths | ConvertTo-Json -Compress)
$phaseAEvidencePathsBase64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($phaseAEvidencePathsJson))
$phaseAEvidenceProjectionJson=@(& $python -c $pythonBase64Launcher $phaseAEvidenceProjectionScriptBase64 $phaseAEvidenceCommitBase64 $phaseAEvidencePathsBase64)
$phaseAEvidenceProjectionExit=$LASTEXITCODE
Assert-NativeExit $phaseAEvidenceProjectionExit 'raw git-show Phase A evidence reparse'
$phaseAEvidenceProjection=(($phaseAEvidenceProjectionJson -join "`n") | ConvertFrom-Json)
$committedLedgerVerdict=@($phaseAEvidenceProjection.planA.reviewVerdict | ForEach-Object { [int]$_ })
if ($phaseAEvidenceProjection.digests.'docs/verification/phase-a-findings.json' -cne $phaseAFindingsSha256 -or $phaseAEvidenceProjection.digests.'docs/verification/unified-twin-acceptance-v1.json' -cne $phaseALedgerJsonSha256 -or $phaseAEvidenceProjection.digests.'docs/verification/unified-twin-acceptance-v1.md' -cne $phaseALedgerMarkdownSha256 -or $phaseAEvidenceProjection.review.schemaVersion -cne 'finding-review-v1' -or $phaseAEvidenceProjection.review.plan -cne 'A' -or $phaseAEvidenceProjection.review.reviewedSha -cne $phaseAVerifiedCodeCommit -or [int]$phaseAEvidenceProjection.review.verdict.critical -ne $reviewVerdict[0] -or [int]$phaseAEvidenceProjection.review.verdict.important -ne $reviewVerdict[1] -or [int]$phaseAEvidenceProjection.review.verdict.minor -ne $reviewVerdict[2] -or $phaseAEvidenceProjection.planA.verifiedCodeCommit -cne $phaseAVerifiedCodeCommit -or $committedLedgerVerdict.Count -ne 3 -or $committedLedgerVerdict[0] -ne $reviewVerdict[0] -or $committedLedgerVerdict[1] -ne $reviewVerdict[1] -or $committedLedgerVerdict[2] -ne $reviewVerdict[2] -or @($phaseAEvidenceProjection.ac06).Count -ne 1) { throw 'raw committed Phase A evidence identity/digest/verdict mismatch' }
$env:PHASE_A_FINDINGS_SHA256=$phaseAFindingsSha256
$env:PHASE_A_LEDGER_JSON_SHA256=$phaseALedgerJsonSha256
$env:PHASE_A_LEDGER_MARKDOWN_SHA256=$phaseALedgerMarkdownSha256
& $python scripts/verify_unified_acceptance.py render --ledger docs/verification/unified-twin-acceptance-v1.json --output docs/verification/unified-twin-acceptance-v1.md
if ($LASTEXITCODE -ne 0) { throw 'phase A post-commit ledger render failed' }
& $python scripts/verify_unified_acceptance.py verify --ledger docs/verification/unified-twin-acceptance-v1.json
if ($LASTEXITCODE -ne 0) { throw 'phase A post-commit ledger verification failed' }
$postAEvidenceStatus=@(git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $postAEvidenceStatus.Count -ne 0) { throw 'phase A evidence commit/post-render must be clean' }
```

The evidence commit must not contain code, migration, CSV, database, or generated runtime artifacts. The post-commit render must be a no-diff operation and verification must pass.
The `phaseAEvidenceCommit` SHA is deliberately outside the ledger JSON to avoid self-reference; record it only in the Phase A handoff after the post-commit scope, `render`, and `verify` checks succeed.

---

## Dependency order and external gates

1. Task 1 blocks every stored/public type.
2. Tasks 2 and 3 may proceed in parallel after Task 1.
3. Task 4 requires Tasks 2 and 3.
4. Task 5 requires Task 4 and a disposable `TEST_DATABASE_URL`.
5. Task 6 requires Tasks 2, 4, and 5.
6. Task 7 requires Tasks 3 through 6 and the controller-provided real CSV. Its read-only file proof and disposable local SQLite write are separate gates; neither authorizes the other.
7. The local SQLite proof may write only after its exact one-shot approval. It must leave one final ignored, non-reparse, staged-but-not-active database for B; no remote approval is implied.
8. Do not run preview migration without the migration gate.
9. Do not run preview stage or activation without their separate gates and a confirmed fingerprint/hash report.
10. Production repeats all three gates; preview approval never implies production approval.
11. The database cannot independently prove a Neon project/branch ID from a generic PostgreSQL DSN. The operator-provided IDs and expected fingerprint are therefore an explicit external control, not inferred evidence.
12. This plan does not activate hotspots, sensor placement, maintenance instructions, or operational stop/run guidance.

## Completion evidence

Before handing off to the timeline plan, the integrator emits a strict sanitized handoff containing `globalBaseCommit`, the E1 `phaseStartCommit`, `phaseAVerifiedCodeCommit`, externally recorded `phaseAEvidenceCommit`, textual `reviewVerdict="PASS"`, the exact three-path evidence diff above, and raw-blob digests `phaseAFindingsSha256`, `phaseALedgerJsonSha256`, and `phaseALedgerMarkdownSha256`. The textual PASS means the report's object verdict has zero Critical/Important; it never replaces that object or the ledger's exact `[critical,important,minor]` tuple. B uses `phaseAEvidenceCommit` as its own `phaseStartCommit`; it never restarts from the global base. The controller maps the three digests to `PHASE_A_FINDINGS_SHA256`, `PHASE_A_LEDGER_JSON_SHA256`, and `PHASE_A_LEDGER_MARKDOWN_SHA256`; B recomputes them from raw `git show` blobs before trusting any working file. The controller also transfers the exact closed `phase-a-local-staged-history-handoff` object from Step 6 and, through a separate private process-local channel, the ignored SQLite path. The public/review/ledger handoff never contains that path. Also capture:

- independently reviewed `phaseAVerifiedCodeCommit`, findings report, verified ledger state, and separately recorded `phaseAEvidenceCommit`;
- Python and JavaScript contract test results;
- SQLite fresh/upgrade/idempotency results;
- PostgreSQL shared-contract/concurrency result with a configured disposable `TEST_DATABASE_URL`, at least one executed pass, and zero skips;
- real-file opt-in counts/hash result;
- guarded local migration result hash, first real stage identity/hash/counts, reconstructed byte hash, exact second-stage no-op, final database-content hash, and proof that the batch remains `staged` with `activeBatchId=null`;
- proof that snapshot/live tables are byte/count unchanged by historical stage and activation;
- sanitized `stage-history`, `activate-history`, `show-active`, and `verify-active` result JSON hashes/fields from the guarded report boundary;
- no preview or production writes unless each gate was separately authorized.

B must reject the handoff unless `localProofCodeCommit == phaseAVerifiedCodeCommit`, all closed fields and result hashes are present, the privately supplied database remains ignored/regular/non-reparse under this worktree's `tmp/twinops-local-proof`, its content hash and target fingerprint match, and `reattest_local_staged_handoff(..., require_no_active_batch=True)` reproduces the exact batch/source/manifest/counts without changing a byte.
