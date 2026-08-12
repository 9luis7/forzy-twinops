# Task 4 — Gate 0 report

## Status

Completed in the `predictive-base` worktree.

## Delivered

- `src/dataSources/ReplayTwinDataSource.js`
  - Exports `buildReplaySnapshot`.
  - Maps deterministic legacy replay readings to replay snapshots, keeping
    legacy vibration exclusively in `vibrationAcceleration` and leaving
    `vibrationVelocityRms` as `null`.
  - Uses the reading timestamp for generated and sample timestamps, maps
    legacy status spellings, maps live points into deterministic history, and
    exposes replay-only capabilities.
  - Labels scenario/risk output with
    `demo_scenario_not_model_inference` and the reviewed relative-score
    semantic.
- `src/dataSources/ReplayTwinDataSource.test.js`
  - Covers a fixed normal tick, alert demo assessment and replay controls, and
    missing legacy values remaining `null`.

## RED → GREEN evidence

1. RED: `npm.cmd run test:run -- src/dataSources/ReplayTwinDataSource.test.js`
   failed because `./ReplayTwinDataSource.js` did not exist.
2. GREEN: the same command passed: 1 file, 3 tests.
3. Regression: `npm.cmd run test:run -- src/contracts/schema.test.js src/contracts/twin.test.js src/dataSources/TwinDataSource.test.js src/dataSources/ReplayTwinDataSource.test.js`
   passed: 4 files, 24 tests.

## Self-review

- `git diff --check` passed.
- The production and test changes are restricted to the new replay data-source
  files; existing untracked Python environment and cache directories were
  preserved.
- No mocks, contexts, schemas, packages, or other application modules changed.

## Concern / follow-up

The supplied Gate 0 requirement deliberately represents unavailable legacy
measurements as `null` and keeps RMS vibration absent as `null`. The current
strict JSON Schema describes numeric measurement values, an object RMS value,
and an empty `raw` object, so these partial replay snapshots are not valid
full-schema telemetry samples. This adapter remains compatible with the
reviewed lightweight frontend `assertDigitalTwinSnapshot` boundary; reconciliation of
the strict transport schema belongs to a later approved contract decision and
was not changed here.

## Contract separation approved by user

The user approved this fix round and replaced the unpublished v1 contracts
while retaining `schemaVersion: "1.0"`:

- `CanonicalSensorReading` is the strict immutable acquisition/import record,
  including `raw` and `provenance`.
- `SensorTelemetryFrame` is the consumer-safe projection with nullable,
  explicitly named measurements and provenance-aware timestamps.
- `AssetConditionAssessment` is the ML-output contract.
- `DigitalTwinSnapshot` is the frontend aggregate over telemetry frames.

The old three schema files and their fixtures were removed. The replay adapter
now produces frames with `sourceMode: "replay"`, `observedAt` from the legacy
reading, `receivedAt: null`, and `timestampQuality: "synthetic"`; it does not
claim `forzy-csv`, `scheduledAt`, or `raw` on the consumer projection.

### Validation

- RED was observed for missing renamed schemas and replay frame fields.
- JavaScript Gate 0: 4 files, 29 tests passed, including Ajv validation of the
  replay adapter output, all legacy status mappings, and epoch timestamps.
- Python contracts: 4 tests passed using the renamed Pydantic models and
  fixtures.
- `npm.cmd run build` passed. Vite retained its existing >500 kB chunk warning.

## Fix round 2/5

- `buildReplaySnapshot` now creates `AssetConditionAssessment` only when
  `risk.score` is a finite number. A scenario without a score, or with `NaN`,
  retains the legacy-derived snapshot status and sets `assessment` to `null`.
- Replay tests cover normal/no assessment, alert/scenario/finite score,
  scenario without a score, and a non-finite input score; each required null
  case is accepted by Ajv.
- The duplicate-S1 schema test now gives the duplicate frame a valid new
  `frameId` and explicitly sets `sensorId: "s1"`, so it proves the live
  S1/S2 containment invariant instead of failing on an unknown legacy field.

RED: two adapter tests failed because an assessment was emitted with missing or
`NaN` score. GREEN: Gate 0 JS passed (4 files, 32 tests) and the production
build passed. Python contracts were not touched. Vite retained its existing
>500 kB chunk warning.
