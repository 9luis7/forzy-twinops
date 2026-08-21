# Task 2R3 report — attested XJTU-SY multipart preparation

## Status

IMPLEMENTED — awaiting independent review; no real XJTU-SY extraction was run.

Base SHA: `5b2d4e789514b7475584b353f2e54bfad077da10`.

## Decisions

- Added immutable `XjtuSyPreparationConfig` and
  `XjtuSyPreparationResult` values plus `prepare_xjtu_sy(config)`.
- Bound the caller to the six official multipart names and SHA-256 values in
  exact order, six distinct absolute paths, an absolute caller-trusted 7-Zip
  executable, an absolute destination, and the task-owned 64 GiB total limit.
  The default file-count, per-file, ratio, and timeout protections remain
  unchanged.
- Reused the reviewed 2R2 security design locally without importing private
  Task 2R1 or NASA helpers. The only `downloads.py` imports are the approved
  public `ArchivePart`, `RarExtractionLimits`, `RawInventory`,
  `inspect_rar_archive`, and `safe_extract_rar_archive` APIs.
- Attested the 7-Zip regular file, all relevant plain/non-reparse ancestors,
  filesystem identities, size, and SHA-256 at config creation. The whole
  attestation is revalidated at preflight and immediately before the single
  extraction call; same-byte file or parent replacement is rejected.
- Inspect exactly once before any destination write and extract exactly once
  with all six parts. The archive contract requires 19 directories, 9,217
  regular files, 9,216 CSVs, one exact source PDF, 12,220,812,451 bytes, and
  the 15 contiguous author-table sequences.
- Stream-validate every CSV as ASCII numeric data with exactly 32,768 rows,
  exactly two finite comma-separated columns, and byte/hash equality to the
  reconstructed `RawInventory`. Validate and hash the PDF only inside the
  owned safe staging tree.
- Publish `attestation.json`, `metadata.json`, and
  `raw/XJTU-SY_Bearing_Datasets/...` as one content-addressed immutable
  generation. Existing exact generations are fully re-attested; divergent or
  unsafe generation roots are preserved and rejected.
- Bind the generation ID to all six ordered source hashes, raw inventory hash,
  metadata hash/schema, preparation schema, and the pinned author registry.
- Keep terminal outcomes only in bearing-level evidence, including the
  four-component Bearing 3_2 outcome. No terminal outcome becomes a per-window
  state or fault label.
- Keep acceleration unit, header names, absolute time/timezone, window state,
  onset, severity, physical failure time, life fraction, and true RUL unknown.
  Radial load is represented only as `{value, unit: "kN"}` in condition
  evidence; the unitless signal-window `load` field stays null.
- Tightened `iter_xjtu` to require positive `samplesPerWindow`, skip only
  explicit `source_document`, require `signal_window` for CSVs, enforce the
  declared row count, and reject duplicate global
  `(runId, bearingId, sequenceIndex)` identities.

## Pinned author registry

The preparation registry uses the source tutorial DOI
`10.3901/JME.2019.16.001` and only the facts required by the brief:

- condition 1 / `35Hz12kN`: `123 + 161 + 158 + 122 + 52 = 616`;
- condition 2 / `37.5Hz11kN`: `491 + 161 + 533 + 42 + 339 = 1,566`;
- condition 3 / `40Hz10kN`:
  `2,538 + 2,496 + 371 + 1,515 + 114 = 7,034`.

The registry therefore yields 15 bearings, 9,216 CSVs, 19 directories,
9,217 regular files with the source PDF, and 9,236 total members. Sampling is
25,600 Hz, each window has 32,768 samples, cadence is one minute, and source
columns 0/1 map to horizontal/vertical.

## TDD evidence

- Initial collector RED: the new test module could not import
  `twinops.research.datasets.xjtu_preparation`.
- First orchestration RED: `9 failed, 9 passed`; the public preparation
  function still raised `NotImplementedError` for inspection, archive
  divergence, metadata, and attestation cases.
- Adapter RED: `6 failed`; the previous adapter tried to read
  `sequenceIndex` from the source PDF and had no kind or row-count contract.
- CLI compatibility RED: `1 failed, 13 passed`; the existing synthetic XJTU
  metadata lacked mandatory `samplesPerWindow`. The source `_signal()` creates
  exactly 128 rows, so the authorized fixture correction adds literal 128 and
  `kind="signal_window"`; production has no default or inference.
- Ownership/content pressure RED: `2 failed`; a different valid numeric byte
  total could be returned for the same inspected paths, and a reparse `raw/`
  root was detected only after five CSV reads. The minimum fix binds the raw
  total to inspection and validates the raw-root identity before and after all
  reads.
- Public API normalization RED: the Task 2R1 inspector's resolved
  `ArchivePart` paths were rejected when the caller supplied equivalent
  absolute paths containing `..`. Comparison now uses exact order/hash plus
  strict resolved path equality.
- The explicit CSV matrix covers header text, one-row-low/high fixtures
  equivalent to 32,767/32,769, one/three columns, blank, ragged, nonnumeric,
  NaN, and infinity. All fail without publication.

## Atomicity and security self-review

- Destination and staging creation begin only after the complete multipart
  inspection passes.
- Staging ownership is granted only when the full stable creation guard
  (device, inode, mode, file attributes, reparse tag, and ctime) agrees with a
  separately acquired stable positive identity.
- Cleanup considers only known staging/final candidates and removes exactly
  one matching owned identity. Ambiguous replacements, displaced trees, and
  controller sentinels are preserved.
- `RuntimeError`, `KeyboardInterrupt`, and `SystemExit` keep the exact original
  object for extraction, pre-rename, post-mutation rename, and identity-swap
  cases. Cleanup-note failure, including hostile `add_note`, never masks it.
- Existing final roots are stable plain directories before and after manifest
  traversal. Nested links/reparse objects are rejected by the filesystem walk.
- Raw-root identity is stable and plain before content reads and after all
  hashes. Inventory paths, total bytes, per-file bytes/hashes, and filesystem
  paths are mutually bound.
- Attestation serialization is canonical and path-free. It contains no local
  archive path, destination, executable detail, credential, or host value.
- Confirmatory, supervised, transfer, and RUL metric flags are all false.

## Verification evidence

Fresh final numbers from the post-report gate rerun:

- focused XJTU preparation/adapter: `73 passed, 1 skipped in 4.81s`;
- focused public-fault CLI: `14 passed in 22.93s`;
- research suite: `308 passed, 4 skipped, 1 warning in 33.68s`;
- full Python suite: `523 passed, 6 skipped, 2 warnings in 41.85s`;
- isolated performance gate: `p50=47.99 ms`, `p95=p99=50.04 ms`;
- `compileall`, `pip check`, `git diff --check`, and tracking gates: passed.

The real-source smoke is opt-in and read-only. It requires both
`TWINOPS_XJTU_RAR_DIRECTORY` and `TWINOPS_TRUSTED_7Z_PATH`; without both it is
explicitly skipped and creates no destination. No direct 7-Zip command or real
9,217-file extraction was run in this implementation wave.

The explicit smoke result was `1 skipped in 1.85s` with the two required
environment variables named in the reason.

## Scope proof and concerns

- `data/public/sources.json`, `downloads.py`, NASA preparation, raw/downloaded
  archives, prepared data, scripts/CLI logic, experiments, features,
  operational artifacts, and deploy files are unchanged.
- The sole authorized CLI test change adds factual XJTU fixture fields; no
  assertion or flow changes.
- Full real extraction remains controller-gated until this implementation SHA
  receives independent PASS. Expected work remains roughly 9,217 member
  processes, 11.38 GiB final data, 55–80 GB logical I/O, and conservatively
  1–6+ hours on the documented Windows/SSD environment.
- The final OS scheduling interval between 7-Zip revalidation and the public
  path-based Task 2R1 extraction call cannot be removed without changing the
  accepted public boundary; there is no application operation between them.

## Commit

Planned message: `feat: prepare attested XJTU-SY volumes`.

The final SHA is reported by Git after this brief/report are included in the
atomic commit.
