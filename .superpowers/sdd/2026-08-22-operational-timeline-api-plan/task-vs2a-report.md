# Task VS2A report — honest timeline overview

## Status

`DONE_WITH_CONCERNS`

VS2A now builds and strictly validates a read-only `TimelineOverviewV1` from
the active archive batch and live originals. The focused/relevant local gates
are green. This does not complete Phase B and does not add routes, startup
wiring, assessment/scoring, candidate construction, artifacts, migrations,
data operations, activation, deployment, push, or merge work.

Approved starting point: branch `luis/operational-timeline-api` at
`9f778a37d65ed18278351849f06266408a747321`.

Commit subject reserved for this slice: `feat: build honest timeline overview`.

## Implementation

- Added a strict overview query and range resolver. Requested bounds remain
  canonical half-open UTC-millisecond instants, the global available range is
  derived from originals, and empty or non-intersecting requests retain null
  effective bounds.
- Added honest archive/live segmentation. Archive continuity breaks only when
  the point-to-point gap is greater than 15 seconds; exactly 15.000 seconds is
  continuous and 15.001 seconds creates a gap. Live expected/idle gaps are
  classified only from the persisted, hash-valid collection policy effective
  for the evidence time.
- Added deterministic coverage gaps and operating cycles. Cycles use all active
  archive originals, preserve inclusive bounds/counts/durations and preceding
  gap evidence, intersect the effective range, and keep `candidateCount=0`.
- Added deterministic first/min/max/last envelope downsampling. The budget is
  applied once per sensor/source over the response range, buckets are anchored
  to the response bounds, full total-order ties are stable, extrema retain
  their original point identity, and a rendered series never crosses a gap.
- Added the read-only composition service. It uses bounded VS1 source pages,
  validates the active archive batch before and after reads, retains every
  archive/live original for future `/samples` and context work, emits
  `eventCandidates=[]`, and does not invoke a model, scorer, artifact path,
  upstream refresh, or repository write.
- Extended only the timeline repository protocol with the bulk
  `collection_policies(...)` read already implemented by both storage
  adapters. No SQLite/PostgreSQL adapter or migration change was necessary.
- Exported only the public overview query/service entry points from the
  timeline package.

## TDD evidence

### Required RED

The first sandboxed invocation was not accepted as RED because Windows denied
loading the pinned environment's `rpds` DLL and pytest exited during import.
The same focused test was rerun with the pinned Python and worktree-isolated
`PYTHONPATH`, `TEMP`, `TMP`, and `--basetemp` in the permitted execution
context. It exited `1` solely on the deliberate assertion, without collection
or internal error:

```text
AssertionError: RED:VS2A:timeline-overview-missing
1 failed in 0.21s
```

The deliberate token remains present exactly once in the VS2A test sources.

### Required GREEN

- Final focused VS2A modules: `54 passed in 1.11s`.
- Final Python timeline plus frozen Timeline model/JSON Schema contract gate:
  `154 passed in 7.03s`.
- Frozen JavaScript/AJV Timeline contract gate: one file passed,
  `63 passed (63)` in `2.32s`. The invocation explicitly excluded only the
  inaccessible worktree-local `services/twinops/.pytest_cache` from Vitest's
  filesystem scan; no source or test selection was excluded.
- The Python timeline run includes the VS1 repository/cursor regressions once.
- No skipped result is used as evidence for PostgreSQL parity.

The coverage matrix includes empty, narrow, and full ranges; multiple sensors;
15.000 versus 15.001 seconds; source discontinuity and overlap failure;
missing, null, invalid, and transitioning policy evidence; negative, zero,
extrema, and tied values; deterministic serialized bytes; cycle contents and
the 204-cycle response shape; the global ceiling per sensor/source; and series
that cannot cross a gap.

## Decisions and invariants

- No storage interpolation, carry-forward, or deduplication is performed.
  Original total order and provenance are validated before reduction.
- A live point with `collectionPolicyId=null` is represented conservatively by
  an `unclassified_coverage_gap` plus the
  `live_collection_policy_missing` assumption code. Runtime defaults are never
  inherited.
- A non-null policy association that cannot resolve to persisted, hash-valid,
  time-effective policy evidence fails closed as
  `TimelinePolicyEvidenceInvalidV1`; its association/provenance is not erased
  or coerced. The database foreign key makes a missing referenced record an
  inconsistent/corrupt-evidence branch, not the normal demo path.
- A live interval whose two endpoints require different non-null policies or
  whose persisted schedule changes within the interval cannot be represented
  honestly by the frozen single-gap model. It fails closed as
  `TimelineUnrepresentableLiveGapV1`.
- Archive/live source overlap, including an equal endpoint, cannot satisfy the
  frozen non-overlapping segment invariant. It fails closed as
  `TimelineSourceOverlapV1` instead of discarding points or emitting invalid
  JSON.
- Segment and gap identities are deterministic UUIDv5 values; the frozen gap
  identity formula is preserved exactly.
- Downsampling validates complete, homogeneous, uniquely identified,
  full-total-ordered originals and retains finite original values. It selects
  originals only; it never synthesizes a sample.

## Files

- `.superpowers/sdd/2026-08-22-operational-timeline-api-plan/task-vs2a-report.md`
- `services/twinops/src/twinops/timeline/__init__.py`
- `services/twinops/src/twinops/timeline/repository_v1.py`
- `services/twinops/src/twinops/timeline/ranges_v1.py`
- `services/twinops/src/twinops/timeline/segments_v1.py`
- `services/twinops/src/twinops/timeline/downsample_v1.py`
- `services/twinops/src/twinops/timeline/service_v1.py`
- `services/twinops/tests/timeline/overview_fixtures_v1.py`
- `services/twinops/tests/timeline/test_ranges_v1.py`
- `services/twinops/tests/timeline/test_segments_v1.py`
- `services/twinops/tests/timeline/test_downsample_v1.py`
- `services/twinops/tests/timeline/test_timeline_overview_v1.py`

## Self-review

- Re-read the binding brief, demo plan, VS1 report, Task B5, and design sections
  8.1–8.4 before implementation, then reviewed the complete owned diff against
  those requirements.
- Checked the frozen Python models, JSON Schemas, and JavaScript contract for
  unintended changes; none are part of this slice.
- Confirmed `eventCandidates` is always the empty frozen tuple/list and that no
  model, scorer, assessment, artifact, route, startup, migration, or frontend
  dependency was introduced.
- Confirmed repository interaction is read-only and uses the existing bounded
  bulk/source reads; fake-repository write traps remain uncalled.
- Confirmed all touched paths stay inside the VS2A ownership allowlist. No
  storage adapter was changed.
- Ran whitespace, status, staged-path, and final verification gates before the
  commit; exact results are retained in the implementation handoff.
- Resolved and removed all 21 task-owned worktree-local `.tmp/vs2a-*`
  basetemp directories without broad `.tmp` cleanup.

## Concerns and remaining gates

- `TEST_DATABASE_URL` is absent. Real disposable-PostgreSQL parity remains an
  explicit external gate and is neither a pass nor a skip in this report.
- The service materializes all matching originals through bounded pages before
  applying the response-global envelope. This is correct for the demonstrator
  and preserves future original retrieval, but is a production-evolution seam
  for very large windows.
- Source overlap and live evidence that the frozen gap shape cannot represent
  are intentionally named fail-closed branches. Supporting those conditions as
  normal output would require an approved contract/model change outside VS2A.
- The initial Python and JavaScript sandbox attempts encountered Windows ACL
  failures while loading pinned native tooling. Their permitted-context reruns
  completed normally; the ACL incidents are not counted as product failures.
- The ignored worktree-local `services/twinops/.pytest_cache` remains
  ACL-inaccessible: both removal and ACL inspection were denied even in the
  permitted context. Git status can warn while scanning it. Vitest's prescribed
  cache exclusion bypasses only that directory; it does not exclude a source or
  test. No other task-owned temp directory remains.
