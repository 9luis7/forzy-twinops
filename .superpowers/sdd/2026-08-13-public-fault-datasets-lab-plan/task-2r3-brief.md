# Task 2R3 brief — attested XJTU-SY multipart preparation

## Frozen base and goal

- Base SHA: `5b2d4e7` on `luis/public-fault-real-data`.
- Goal: prepare the six official XJTU-SY RAR5 volumes into one immutable,
  path-free, semantically gated generation without changing the operational ML
  package or opening the public-fault experiment gate.
- Required workflow: TDD, implementation commit, independent review on the
  closed SHA, fix waves until 0 Critical / 0 Important, then controller-only
  authorization for the real extraction.

## Ownership

Create:

- `services/twinops/src/twinops/research/datasets/xjtu_preparation.py`
- `services/twinops/tests/research/test_xjtu_preparation.py`
- `.superpowers/sdd/2026-08-13-public-fault-datasets-lab-plan/task-2r3-report.md`

Modify:

- `services/twinops/src/twinops/research/datasets/xjtu.py`
- `services/twinops/tests/research/test_xjtu_adapter.py`
- `data/public/README.md` only for the XJTU prepared layout and gates

No touch:

- `downloads.py` or any private Task 2R1 helper
- `data/public/sources.json` (controller-owned)
- `scripts/run_public_fault_lab.py`, experiments, features, artifacts, CLI
- NASA files, operational ML, deploy files, raw/downloaded archives

No real extraction, push, merge, mirror, new download, or direct `7z` call in
this implementation task.

## Pinned official source

The caller must supply these six distinct absolute `ArchivePart` values in this
exact order:

| Part | Bytes | SHA-256 |
| --- | ---: | --- |
| `XJTU-SY_Bearing_Datasets.part01.rar` | 744488960 | `c500657353f089a4ab50212ff4ddfc7b982729e92e2b127440c8ad881d80b968` |
| `part02.rar` | 744488960 | `4dfa6286a8e9c7cec1e925b347642349f36e27ab3f703c90d1d08977b7b4f61f` |
| `part03.rar` | 744488960 | `6929f531284f79e0209246b4ee23b23dd8d4faac1c0c3ff8fb131cda4a18bd3a` |
| `part04.rar` | 744488960 | `2245825acd29bed3b95e7a77879a3fbadf20f4ad4f99486384c714174621597d` |
| `part05.rar` | 744488960 | `e1b0a41a32b865e48ea7981c56f952a960d94335f3496b72eb4a65932f1671bd` |
| `part06.rar` | 722155640 | `df1854821a9d481104476379f7bc045ea1e101427c6e36145cd7677dc7c4a684` |

The accepted Task 2R1 public surface is limited to `ArchivePart`,
`RarExtractionLimits`, `RawInventory`, `inspect_rar_archive`, and
`safe_extract_rar_archive`. Never import its private helpers.

Use an explicit task-owned limit with
`max_total_uncompressed_bytes=64 * 1024**3`; retain the existing member-count,
per-file, ratio, and timeout protections. The global/default limit remains
unchanged.

## Exact archive contract

Inspection before any staging/write must prove:

- 6 RAR5 volumes, 9,236 members: 19 directories and 9,217 regular files.
- 9,216 CSV files plus exactly one source PDF.
- Total uncompressed bytes `12,220,812,451`.
- Root `XJTU-SY_Bearing_Datasets/` only.
- PDF exactly
  `XJTU-SY_Bearing_Datasets/Introduction_to_XJTU-SY_Bearing_Dataset.pdf`.
- Conditions and CSV totals: `35Hz12kN=616`, `37.5Hz11kN=1566`,
  `40Hz10kN=7034`.
- Exactly 15 bearing directories (`Bearing1_1..1_5`, `2_1..2_5`,
  `3_1..3_5`). Each sequence is contiguous from `1.csv` through its pinned
  author-table count; no missing, duplicate, padded, zero, negative, or extra
  sequence name.

Reject any extra root, wrong/deeper path, missing/duplicate PDF, unexpected
extension/type, or count/byte/order/hash divergence before creating staging.

## Public preparation API

Provide immutable, typed values with a minimal public surface:

- `XjtuSyPreparationConfig`
- `XjtuSyPreparationResult`
- `prepare_xjtu_sy(config) -> XjtuSyPreparationResult`

The config contains the six ordered parts, caller-supplied absolute trusted
7-Zip path, absolute destination root, and the task-owned limits. Reuse the
reviewed 2R2 executable-attestation and directory-ownership design rather than
weakening it or hardcoding a local path.

Call `inspect_rar_archive` once before writes and
`safe_extract_rar_archive` exactly once for all six parts. Publish atomically:

```text
xjtu-sy/prepared/<generation-id>/
  attestation.json
  metadata.json
  raw/XJTU-SY_Bearing_Datasets/
    Introduction_to_XJTU-SY_Bearing_Dataset.pdf
    <condition>/<bearing>/<sequence>.csv
```

Existing exact generations are fully re-attested and returned idempotently.
Existing divergent generations, links, junctions, reparse roots, or ambiguous
ownership are preserved and rejected. On any `BaseException`, preserve the
same exception object; cleanup only paths proven task-owned, and defensive
notes must never mask the primary exception. Cover rename-before-raise and
identity swaps explicitly.

## Content validation and metadata

After safe extraction but before promotion:

- Reconstruct the filesystem inventory; source hashes must remain pinned.
- Every CSV is strict UTF-8/ASCII numeric content with exactly 32,768 rows and
  2 finite columns. Detect header, blank, ragged, nonnumeric, NaN/Inf, extra
  column, and off-by-one rows fail-closed; do not silently skip a header.
- Read/hash the PDF only inside the safely extracted staging tree. Treat it as
  `kind="source_document"`; it is never a signal window.
- Metadata schema v1 maps every raw-inventory path exactly. CSV entries use
  `kind="signal_window"`; the single PDF uses `kind="source_document"`.
- The adapter ignores only the explicit `source_document` entry and rejects
  every unknown kind or inventory mismatch.

Author-supported mappings:

- Sampling: `25600 Hz`; samples/window: `32768`; observation cadence: one
  minute.
- Columns: `0=horizontal`, `1=vertical`; never rename to radial/axial.
- Conditions: `35Hz12kN -> condition-1, 2100 rpm, 12 kN`;
  `37.5Hz11kN -> condition-2, 2250 rpm, 11 kN`;
  `40Hz10kN -> condition-3, 2400 rpm, 10 kN`.
- Global bearing ID: `xjtu-sy-bearing-<condition-index>-<bearing-index>`.
- Run ID: `xjtu-sy-run-to-failure-<condition-index>-<bearing-index>`.
- `sequenceIndex=int(csv_stem)-1`; preserve the original sequence number.
- Terminal failure descriptions remain bearing-level evidence only. Map an
  author-described compound outcome as evidence, never as every window label.

Mandatory unknown/fail-closed fields:

- numeric acceleration unit and header names
- absolute timestamps/timezone
- per-window state/fault label, onset, severity
- physical failure time, true RUL, and `lifeFraction`
- load in the current unitless float field (record `{value, unit:"kN"}` only in
  condition evidence)

If an observation fraction is ever emitted, name it separately and identify it
as sequence-derived; do not populate `lifeFraction`.

## Determinism and attestation

The generation ID binds, in canonical order:

- all six source hashes
- raw inventory hash
- metadata hash/schema and preparation schema version
- pinned author condition/bearing registry

The path-free attestation records counts, hashes, conditions, terminal
evidence, PDF hash, and semantic gates. Its status is
`prepared_semantically_gated`; confirmatory, supervised, transfer, and RUL
metric flags remain false. Do not serialize absolute paths, executable details,
credentials, or host-specific values.

## Mandatory TDD

Start with RED tests for:

1. Six-part order, names, hashes, absolute/distinct paths, trusted executable,
   and explicit 64 GiB limit.
2. Inspect-before-write, exact archive shape, contiguous per-bearing sequences,
   PDF uniqueness, and one extraction call.
3. CSV shape/content failures: header, 32767/32769 rows, 1/3 columns,
   blank/ragged/nonnumeric/NaN/Inf.
4. Metadata equals filesystem inventory; PDF document kind; adapter skips only
   that kind and keeps global `(runId,bearingId,sequenceIndex)` uniqueness.
5. No inferred unit, timestamps, window labels, onset, severity, load float,
   life fraction, or RUL.
6. Cross-root determinism, idempotency, divergent final preservation,
   link/reparse roots, pre/post-rename `RuntimeError`, `KeyboardInterrupt`, and
   `SystemExit`, identity swaps, cleanup failure, and note failure.
7. Attestation is path-free and all metric gates stay closed.
8. Real-source smoke is read-only inspection only, opt-in with explicit archive
   directory and trusted 7-Zip path; it skips otherwise and writes nothing.

## Verification and commit

Run, at minimum:

```powershell
services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research/test_xjtu_preparation.py services/twinops/tests/research/test_xjtu_adapter.py -q
services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests/research -q
services\twinops\.venv\Scripts\python.exe -m pytest services/twinops/tests -q
services\twinops\.venv\Scripts\python.exe -m compileall -q services/twinops/src scripts
services\twinops\.venv\Scripts\python.exe -m pip check
git diff --check
git ls-files data/public artifacts/ml/real-forzy
```

Also rerun the isolated performance gate and prove `sources.json`, downloaded
RARs, prepared directories, operational artifacts, CLI, and experiments are
unchanged. Commit only owned files plus this brief/report. Do not run the real
9,217-file extraction until the implementation SHA receives independent PASS
and the controller explicitly starts the runtime task.

Expected real-runtime cost after PASS: 9,217 `7z` member processes, about
11.38 GiB final data and roughly 55–80 GB logical I/O. Current free disk is
ample, but duration is conservatively 1–6+ hours on this Windows/SSD setup.
