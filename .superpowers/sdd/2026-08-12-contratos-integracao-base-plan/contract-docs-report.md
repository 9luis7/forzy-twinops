# Contract documentation alignment report

## Status

Complete. Documentation, work packages, implementation plans, and SDD briefs
now use the approved v1 contract names.

## Alignment

- `CanonicalSensorReading` is the strict acquisition/import record.
- `SensorTelemetryFrame` is the consumer-safe snapshot projection: it excludes
  `raw` and permits explicitly named measurements to be `null` when unavailable.
- `AssetConditionAssessment` is the ML output.
- `DigitalTwinSnapshot` aggregates telemetry frames for consumers.
- Plan references use the four implemented `contracts/v1/*.schema.json` paths
  and the renamed canonical-reading fixtures.
- The ML plan specifies `AssessmentScorer.assess(samples:
  Sequence[CanonicalSensorReading], *, now: datetime) ->
  AssetConditionAssessment`.

## Scope and validation

- Changed Markdown documentation and SDD artifacts only; no application code,
  schemas, tests, package files, or ledger artifacts were changed.
- Legacy contract names are absent from Markdown documentation and SDD artifacts
  when searched as whole identifiers; historical `.diff` review artifacts were
  intentionally excluded from that documentation scan.
- The placeholder scan found only intentional command placeholders and JSX/HTML
  syntax in existing plan examples; no unresolved contract placeholder was found.
- The whitespace scan completed cleanly.

## Concern

Some historical review `.diff` artifacts retain the pre-alignment names. They
are immutable review evidence, not worker instructions, and were left intact.
