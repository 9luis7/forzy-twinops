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

## Independent-review fix wave on `a9750c6`

Status: IMPLEMENTED AND LOCALLY VERIFIED; awaiting independent re-review. No
real XJTU-SY extraction, direct 7-Zip invocation, download, push, or merge was
performed.

### Reviewer reproductions and TDD

The focused reviewer reproduction command initially returned `18 failed, 67
deselected`. The failures were kept distinct and covered the five Important
findings without duplicating the raw-mutation case:

- inspection returned only paths, so it had no immutable per-member size/type
  binding; compensated `9/7` byte mutations with an unchanged total passed;
- bytes changed after raw content validation were adopted as the expected
  staging manifest;
- all 12 cleanup cases failed to attempt a quarantine rename: empty/nonempty,
  pre/post-mutation rename, and `RuntimeError`/`KeyboardInterrupt`/`SystemExit`;
- an undeclared empty directory was accepted as an idempotent generation and a
  blocked `scandir` traversal was silently reduced to an incomplete walk;
- `semanticGates.physicalFailureTime` was absent.

After the minimum implementation, the same selection returned `18 passed, 67
deselected`. A focused regression then exposed that the zero-inode acquisition
case left its safely guard-bound empty staging directory behind. Cleanup
identity checks were made independent two-snapshot `lstat` validations; the
complete preparation module then returned `84 passed, 1 skipped`.

### Review fixes

- `_validate_inspection` now returns a frozen tuple of frozen member bindings
  containing canonical relative path, exact inspected size, and explicit
  `signal_window`/`source_document` kind. `_validate_inventory` compares every
  extracted path and size against that binding before accepting inventory
  hash or total-byte evidence.
- The expected publication manifest is constructed only from immutable
  `RawInventory` `(path, size, sha256)` values and the canonical metadata and
  attestation bytes. It is never learned from staging. Staging is compared
  immediately before promotion; promoted and idempotent final trees are
  traversed and compared independently.
- The manifest represents every file and directory, including empty
  directories. Traversal uses fail-closed `scandir`, validates plain
  non-link/non-reparse objects and stable identities, hashes every file, and
  rejects traversal errors or undeclared objects.
- Cleanup first locates exactly one owned identity among staging/final
  candidates, moves it to a fresh cryptographically named cleanup quarantine,
  re-locates and revalidates the identity there, and only then removes it.
  Pre- and post-mutation rename faults preserve controller replacements and
  sentinels for both empty and nonempty trees. The exact primary BaseException
  object remains authoritative; cleanup-note failure remains defensive.
- The path-free attestation now explicitly records
  `physicalFailureTime: "unknown"`; metric gates remain closed.

### Fresh verification after the fix

- reviewer reproduction selection: `18 passed, 67 deselected in 5.04s`;
- complete XJTU-SY preparation module: `84 passed, 1 skipped in 6.07s`;
- focused preparation plus adapter: `91 passed, 1 skipped in 8.66s`;
- focused public-fault CLI regression: `14 passed in 27.11s`;
- research suite: `326 passed, 4 skipped, 1 warning in 41.85s`;
- first full-suite run: one known environment-sensitive performance failure
  at `p95=124.98 ms`, with all functional tests passing (`540 passed, 6
  skipped`); immediate isolated rerun passed at `p50=52.49 ms`, `p95=53.56
  ms`;
- fresh full-suite rerun: `541 passed, 6 skipped, 2 warnings in 44.89s`;
- final isolated performance gate: `p50=47.73 ms`, `p95=p99=48.46 ms`, `1
  passed in 0.90s`;
- explicit real-source read-only smoke: `1 skipped in 1.71s` because neither
  opt-in environment variable was set; therefore it executed no 7-Zip process
  and wrote no destination;
- `compileall`, `pip check`, `git diff --check`, and tracking gates passed.

The warnings are the pre-existing Starlette/httpx deprecation and joblib
physical-core detection fallback. `data/public/sources.json` retained Git blob
hash `56a6c9c850366c93f4dbf53bdab6830066a6a6b0`. No downloaded archive,
prepared directory, operational artifact, production CLI, experiment, NASA,
or deploy file was changed.

## Independent re-review fix wave 2 on `8a1a2cd`

Status: IMPLEMENTED AND LOCALLY VERIFIED; awaiting another independent
re-review. No real XJTU-SY extraction, direct 7-Zip invocation, download,
push, or merge was performed.

### Reviewer tracers and RED evidence

The exact focused tracer selection returned `9 failed, 85 deselected` before
any production change:

- six deletion-window cases (empty/nonempty quarantine crossed with
  `RuntimeError`, `KeyboardInterrupt`, and `SystemExit`) showed that a
  controller replacement created after the last identity check was deleted by
  pathname while the displaced owned tree survived;
- a second idempotent call extracted again and entered staging cleanup;
- a final generation mutated immediately after its first idempotent manifest
  traversal was returned as successful;
- a file inserted after the first `scandir` snapshot was omitted from the
  manifest without error.

After the minimum production changes, the same selection returned `9 passed,
85 deselected`. The first complete focused run then exposed 40 old assertions
that still required destructive cleanup. Those tests were migrated to the new
fail-safe contract: they require one preserved quarantine plus a sanitized
note on the exact primary exception object. The complete preparation module
then passed at `93 passed, 1 skipped`.

### Cleanup disposition

The local Windows/Python runtime reports:

- `shutil.rmtree.avoids_symlink_attacks = False`;
- `os.rmdir in os.supports_dir_fd = False`;
- `os.unlink in os.supports_dir_fd = False`.

No identity/handle-bound recursive directory removal primitive is therefore
available within the authorized Python boundary. The implementation no longer
calls `rmtree` or `rmdir`. It moves the single located owned identity to a
fresh cryptographic quarantine name, re-locates and revalidates it, and then
preserves it. Cleanup reports only a sanitized exception-class note on the
original `BaseException`; it never replaces that object. Tracers swap the
quarantine after the final identity check and prove the owned tree, controller
replacement, and sentinel all survive for empty and nonempty trees across all
three exception classes.

This deliberately trades disk reclamation for the priority invariant that no
non-owned pathname is deleted. A failed real preparation can therefore leave
a large local quarantine for controller-reviewed manual disposition.

### Idempotency and manifest reconciliation

- An exact existing generation is now validated before staging or extraction.
  The implementation reconstructs an immutable structural raw inventory from
  the final manifest, binds it to inspected path/size evidence, revalidates all
  CSV/PDF content, canonical metadata, canonical attestation, generation ID,
  and the complete final tree. It uses no additional private Task 2R1 import.
- A second exact call performs no extraction and has no staging-cleanup
  mutation window. Concurrent publication after this preflight fails closed
  and preserves the newly built staging quarantine rather than returning with
  an unaccounted side effect.
- Each manifest traversal performs a second complete recursive `scandir`
  re-enumeration and compares every relative child path and type. Links,
  reparse points, unknown object types, child-set changes, and scan errors all
  fail closed.
- Publication validation performs two complete manifests per reconciliation.
  Staging is reconciled once after construction and again immediately before
  promotion. The promoted or idempotent final is reconciled against immutable
  expected bytes as the last operation before returning, with the originally
  validated root identity bound into that check.

### Fresh verification after fix wave 2

- reviewer tracer selection: `9 passed, 85 deselected in 2.56s`;
- complete preparation module: `93 passed, 1 skipped in 9.44s`;
- focused preparation plus adapter: `100 passed, 1 skipped in 9.51s`; final
  post-report rerun: `100 passed, 1 skipped in 9.39s`;
- focused public-fault CLI regression: `14 passed in 32.95s`;
- research suite: `335 passed, 4 skipped, 1 warning in 38.24s`;
- full Python suite: `550 passed, 6 skipped, 2 warnings in 47.53s`; final
  post-report rerun: the same `550 passed, 6 skipped, 2 warnings in 61.06s`;
- isolated performance gate: `p50=49.51 ms`, `p95=p99=53.97 ms`, `1 passed
  in 0.96s`; final post-full rerun passed at `p50=50.51 ms`,
  `p95=p99=52.30 ms` in `1.04s`;
- explicit real-source read-only smoke: `1 skipped in 1.69s` because the two
  opt-in environment variables were absent, so no 7-Zip process ran;
- `compileall`, `pip check`, `git diff --check`, and tracking gates passed.

The two broad-suite warnings remain the pre-existing Starlette/httpx
deprecation and joblib physical-core fallback. `data/public/sources.json`
retained Git blob hash
`56a6c9c850366c93f4dbf53bdab6830066a6a6b0`. No downloaded archive,
prepared directory, operational artifact, production CLI, experiment, NASA,
or deploy file was changed.

## Independent re-review fix wave 3 on `d7bcfc`

Status: IMPLEMENTED AND LOCALLY VERIFIED; awaiting another independent
re-review. No real XJTU-SY data, 7-Zip process, extraction, download, push, or
merge was used.

This section supersedes the cleanup/quarantine disposition described for the
earlier implementation SHAs. Those sections remain historical evidence only:
the current contract performs no error-path rename, move, or deletion. Failed
preparation state is preserved at its current pathname for controller-reviewed
manual disposal.

### Reviewer reproductions and RED evidence

Before production changed, the focused selection returned `13 failed, 87
deselected in 4.70s`:

- 12 cases crossed nonempty/empty staging, `RuntimeError`/
  `KeyboardInterrupt`/`SystemExit`, and `Path.rename`/`os.rename` tracers. The
  old quarantine path invoked rename and the tracer could move a controller
  replacement through the cleanup pathname;
- the idempotent fast path reconstructed files as the private lookalike
  `_ReconstructedRawFile`, so the second result did not have the exact public
  `RawFile` values or `RawInventory` equality of the first result.

After the minimum production changes, the identical selection returned `13
passed, 87 deselected in 3.29s`. The obsolete 12-case matrix whose asserted
contract required a quarantine rename was removed; the current 12-case matrix
requires zero calls to both rename APIs. This replaces the prior six-case
swap tracer and accounts for the net reduction of six collected module cases.
The final post-migration selection returned `13 passed, 75 deselected in
2.82s`.

### Error disposition and public inventory type

- Once staging exists, the `BaseException` handler performs no pathname
  lookup, identity check, rename, move, delete, quarantine, `rmtree`, or
  `rmdir`. It adds one constant path-free note and uses a bare `raise`, so the
  observed exception remains the exact primary object by `is`.
- The note helper catches every `BaseException` from missing or hostile
  `add_note`; a note failure can never mask the primary. The message exposes no
  local path, exception detail, host value, or credential.
- The reviewer tracers prove zero `Path.rename` and zero `os.rename` calls in
  error handling. The owned directory, its nonempty sentinel (or empty state),
  the controller replacement, and its sentinel all remain at their original
  paths for all three exception classes. No cleanup/quarantine path is
  created.
- Normal successful publication retains its single atomic staging-to-final
  rename. If that promotion mutates and then raises, error handling leaves the
  promoted state exactly where the filesystem placed it and annotates the
  primary for manual disposition.
- `RawFile` is now the explicitly authorized sixth public `downloads.py`
  import. The idempotent fast path constructs `RawInventory.files` from real
  `RawFile` objects; the second result now has exact file types and dataclass
  equality with the first result. `_ReconstructedRawFile` was removed, and no
  private Task 2R1 helper is imported.
- Exact-generation idempotency still validates the complete generation before
  returning, performs no second extraction, creates no staging directory, and
  never enters the error-preservation note path.

### Fresh verification after fix wave 3

- focused preparation module: `87 passed, 1 skipped in 8.54s`;
- focused preparation plus adapter: `94 passed, 1 skipped in 7.71s`;
- focused public-fault CLI regression: `14 passed in 21.86s`;
- research suite: `329 passed, 4 skipped, 1 warning in 39.04s`;
- first full run on the final test diff had all functional tests pass but the
  known environment-sensitive performance case missed by 1.93 ms
  (`p95=101.93 ms`; `1 failed, 543 passed, 6 skipped`); its immediate isolated
  rerun passed at `p50=48.07 ms`, `p95=p99=49.15 ms` in `0.98s`;
- fresh full Python rerun: `544 passed, 6 skipped, 2 warnings in 49.70s`;
- explicit real-source smoke: `1 skipped in 1.91s`; both opt-in environment
  variables were absent, so no real archive was read and no 7-Zip process or
  destination was created;
- `compileall`, `pip check`, `git diff --check`, and tracking gates passed.

The broad-suite warnings remain the pre-existing Starlette/httpx deprecation
and joblib physical-core fallback. `data/public/sources.json` retained Git blob
hash `56a6c9c850366c93f4dbf53bdab6830066a6a6b0`. The only current concern is
intentional and fail-safe: a failed real preparation can preserve a large
staging or post-promotion tree in place, which requires explicit manual
disposition after identity and content review. No downloaded archive,
prepared directory, operational artifact, CLI production code, experiment,
NASA, or deploy file changed in this wave.

## Real-runtime official-header correction after `1bd291e`

Status: IMPLEMENTED AND LOCALLY VERIFIED; awaiting independent re-review. The
preserved real staging was not read, mutated, moved, deleted, promoted, or
re-executed during this corrective implementation.

### Fail-closed real-runtime evidence

The controller-authorized real operation first passed exact worktree, ignore,
disk, six-volume size/SHA-256, and trusted 7-Zip preflight. It materialized the
expected `9,217` files (`9,216` CSV plus one PDF) and exactly
`12,220,812,451` bytes, then failed closed after `1,220.872 s` with the exact
primary error `XJTU-SY CSV contains nonnumeric data: 1.csv`. No metadata,
attestation, or final generation was published; the implementation added the
sanitized note `XJTU-SY preparation state preserved in place for manual
disposal` and left the single ignored staging tree in situ.

Independent read-only diagnosis proved that all `9,216` CSVs begin with the
same exact ordered ASCII header:
`Horizontal_vibration_signals,Vertical_vibration_signals`. The first inspected
file had `32,769` physical lines: one header plus `32,768` samples. The six
source RARs and the trusted 7-Zip executable were rehashed after the failed
operation and remained byte-identical. The sanitized runtime log SHA-256 is
`cef289cd28f3ea2fda1fbaceb3ad2c350ae914dce69c11f85eaabc38eb52bcb9`.

This evidence supersedes the historical headerless/header-unknown statements
earlier in this report. It does not resolve the acceleration unit, timestamps,
window labels, onset, severity, physical failure time, `lifeFraction`, or RUL;
all corresponding semantic and metric gates remain closed.

### Corrective TDD evidence

- Content-boundary RED: the isolated header/row/body selection returned
  `8 failed, 7 passed, 88 deselected`. The official header was converted to a
  float, a missing header was accepted, malformed-header failures lacked the
  required header boundary, and both off-by-one cases failed before row-count
  validation.
- Content-boundary GREEN: the identical selection returned
  `15 passed, 88 deselected`. The validator now requires exactly one official
  ordered ASCII header, excludes it from sample count, rejects a duplicate,
  and retains strict two-column numeric/finitude validation plus byte/hash
  binding.
- Metadata/adapter RED: the focused end-to-end metadata test returned
  `1 failed` only because preparation still emitted positional `0/1` columns
  with `hasHeader: false`.
- Metadata/adapter GREEN: the same test returned `1 passed` after emitting the
  two exact source header names mapped to `horizontal`/`vertical` with
  `hasHeader: true`. The adapter reads those named columns, skips the header,
  and preserves window count plus global `(runId,bearingId,sequenceIndex)`.
- Synthetic literal-scale tests separately accept `32,768` data rows and
  reject `32,767` and `32,769`; the malformed matrix covers absent, incorrect,
  duplicated, reordered, and extra-column headers plus one/three data columns,
  blank/ragged/nonnumeric/NaN/Inf bodies.
- A second real smoke is explicitly opt-in through
  `TWINOPS_XJTU_SAMPLE_CSV_COPY`, requires a controller-provided single-file
  copy outside prepared staging, validates it read-only, and checks stable file
  identity/size/mtime. It skips when unset.

### Fresh verification after the header correction

- preparation plus adapter: `112 passed, 2 skipped in 8.35s`;
- focused public-fault CLI regression: `14 passed in 25.52s`;
- research suite: `347 passed, 5 skipped, 1 warning in 39.58s`;
- full Python suite: `562 passed, 7 skipped, 2 warnings in 56.92s`;
- isolated performance gate: `p50=47.17 ms`, `p95=p99=48.98 ms`,
  `1 passed in 0.91s`;
- `compileall`, `pip check`, `git diff --check`, scope, and tracking gates
  passed; pip reported no broken requirements;
- both real smokes skipped because their explicit opt-in variables were unset,
  so this correction invoked no real 7-Zip process and performed no real-data
  I/O;
- `data/public/sources.json` retained Git blob hash
  `56a6c9c850366c93f4dbf53bdab6830066a6a6b0`; downloaded and prepared XJTU
  paths remain ignored/untracked, and operational artifacts, production CLI,
  experiments, NASA, Plan05, and deploy files were unchanged.

The remaining operational concern is deliberate: the failed real staging must
stay preserved until the controller explicitly approves its disposition. A
new real preparation is forbidden until this corrective SHA receives an
independent 0 Critical / 0 Important review.

## Consumer-compatible numeric grammar correction after `7c8bf34`

Status: IMPLEMENTED AND LOCALLY VERIFIED; awaiting independent re-review. No
real archive, extracted CSV, preserved staging, or 7-Zip process was accessed
or invoked during this correction.

The reviewer identified a producer/consumer mismatch: Python `float()` accepts
digit separators such as `1_0`, allowing preparation to publish bytes that the
pandas adapter rejects through `pd.to_numeric(errors="raise")`. The validator
now strips surrounding token whitespace, requires the exact ASCII decimal
grammar `^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$`, and only then runs
the existing float and finiteness gates. Underscores, locale punctuation, and
Unicode numerals fail closed; ordinary surrounding whitespace and exponents
remain valid.

### TDD and fresh verification

- RED on the unchanged production code: the two-test E2E selection returned
  `1 failed, 1 passed in 3.47s`; the underscore case failed with
  `Failed: DID NOT RAISE <class 'ValueError'>`, while the whitespace/exponent
  publication-and-adapter round trip already passed.
- First GREEN plus malformed matrix: `14 passed in 3.42s`. The underscore case
  now raises before final publication, preserves synthetic staging in place,
  and creates no `xjtu-sy-v1-*` generation. Named locale-comma and Unicode
  cases also reject.
- preparation plus adapter: `116 passed, 2 skipped in 9.09s`;
- research suite: `351 passed, 5 skipped, 1 warning in 38.07s`;
- full Python suite: `566 passed, 7 skipped, 2 warnings in 44.36s`;
- isolated performance gate: `p50=49.39 ms`, `p95=p99=58.28 ms`,
  `1 passed in 1.13s`;
- `compileall` and `pip check` passed; pip reported no broken requirements.

The broad-suite warnings remain the pre-existing Starlette/httpx deprecation
and joblib physical-core fallback. Header validation, exact 32,768-row count,
two finite columns, raw byte/hash binding, metadata, adapter identity/count,
determinism, atomic publication, and preserve-in-place failure behavior remain
covered. Final diff/tracking gates are recorded against the committed SHA.

## Shared decimal parser correction after `2fad384`

Status: IMPLEMENTED AND LOCALLY VERIFIED; awaiting independent re-review. No
real archive, extracted CSV, preserved staging, or 7-Zip process was accessed
or invoked during this correction.

The independent re-review found one remaining producer/consumer mismatch:
`18446744073709551616` matches the decimal grammar and converts to a finite
Python float, so preparation published it, but pandas' integer inference made
`pd.to_numeric(errors="raise")` fail with `Integer out of range`. The fix does
not add an arbitrary integer range. A single internal parser now owns strip,
ASCII grammar, float conversion, and finiteness for both preparation and the
adapter. The adapter reads CSV cells as strings with pandas NA and blank-line
inference disabled, then parses every preserved lexeme through that helper.

### TDD and fresh verification

- RED on unchanged production code: `1 failed, 13 passed in 2.97s`.
  Preparation published the synthetic generation and the E2E test then failed
  at `iter_xjtu` with `ValueError: Integer out of range. at position 0`.
- First GREEN across the large finite integer, whitespace/exponent,
  underscore, locale, Unicode, and overflow cases: `16 passed in 2.61s`.
  The large integer is now published and consumed as a float; `1e309` remains
  rejected before publication with synthetic staging preserved.
- final preparation plus adapter rerun: `118 passed, 2 skipped in 8.25s`;
- research suite: `353 passed, 5 skipped, 1 warning in 35.49s`;
- full Python suite: `568 passed, 7 skipped, 2 warnings in 43.32s`;
- the first isolated performance run missed the environment-sensitive gate at
  `p50=66.92 ms`, `p95=p99=118.11 ms`; no limit or scorer code changed. Its
  immediate isolated rerun passed at `p50=48.46 ms`, `p95=p99=53.64 ms`,
  `1 passed in 0.95s`;
- `compileall` and `pip check` passed; pip reported no broken requirements.

The broad-suite warnings remain the pre-existing Starlette/httpx deprecation
and joblib physical-core fallback. Header validation, exact 32,768-row count,
two finite columns, byte/hash binding, metadata, axis/unit/identity behavior,
determinism, atomic publication, and preserve-in-place error handling remain
covered. Final diff/tracking gates are recorded against the committed SHA.

## Canonical line-ending correction after `9d8faa5`

Status: IMPLEMENTED AND LOCALLY VERIFIED; awaiting independent re-review. No
real archive, extracted CSV, preserved staging, or 7-Zip process was accessed
or invoked during this correction.

The independent re-review found that generic `str.strip()` admitted carriage
returns around otherwise valid decimal tokens. Preparation also used generic
`bytes.strip()` on each raw data line, so a leading CR or an extra CR before a
canonical line ending could disappear before the shared parser. Such bytes
could publish successfully while pandas interpreted CR as a row boundary and
the adapter then failed its row-count gate.

The shared parser now normalizes only ASCII space and tab. Preparation removes
exactly one canonical LF or CRLF terminator from the header and each data row,
uses only space/tab to identify blank rows, and leaves every residual control
character for strict parser rejection. Canonical LF and CRLF files remain
interoperable with the adapter; CR before a comma, leading CR, and CRCRLF all
fail before publication with synthetic staging preserved in place.

### TDD and fresh verification

- RED on unchanged production code: `9 failed, 3 passed in 3.48s`. Generic
  strip incorrectly accepted CR leading/trailing, LF, vertical tab, form feed,
  and Unicode NBSP; all three residual-CR E2E fixtures published instead of
  raising. NUL already rejected, while canonical LF/CRLF controls passed.
- First GREEN on the identical selection: `12 passed in 2.15s`.
- final preparation plus adapter rerun: `129 passed, 2 skipped in 8.62s`;
- research suite: `364 passed, 5 skipped, 1 warning in 37.08s`;
- full Python suite: `579 passed, 7 skipped, 2 warnings in 45.39s`;
- isolated performance gate: `p50=47.15 ms`, `p95=p99=48.37 ms`,
  `1 passed in 0.89s`;
- `compileall` and `pip check` passed; pip reported no broken requirements.

The broad-suite warnings remain the pre-existing Starlette/httpx deprecation
and joblib physical-core fallback. Official header, exact 32,768-row count,
two finite columns, byte/hash binding, shared producer-consumer parsing,
metadata, identity, deterministic generation, atomic publication, and
preserve-in-place error handling remain covered. Final diff/tracking gates are
recorded against the committed SHA.

## Real preparation publication and semantic-gate outcome (Task 2R4)

Status: REAL PREPARATION EVIDENCE PUBLISHED; SUPERVISED LAB REMAINS
FAIL-CLOSED. All earlier `awaiting review`, header-unknown, preparation-not-run,
and no-extraction statements in this report are historical and superseded by
this section. The failed staging `.xjtu-sy-generation-7x6h7sqm` remains exactly
in place and was neither read as source of truth nor moved, deleted, promoted,
or re-executed in Task 2R4.

### Successful XJTU-SY generation

The real preparation published immutable generation
`xjtu-sy-v1-8c7e9d8b7c272002a4d44b021931aaf6500f013574db60839bae2af3aa0fee1a`.
Its attestation SHA-256 is
`49de3ae74df4de489a966a77ccf6af647a58e60ceb2515934b9c62bf299277a5`
and its metadata SHA-256 is
`4876cc6540a8c972c63b890d111d1a4d60322f5addd2a317b0b058246020e8f8`.
The raw inventory contains 9,217 files (9,216 CSVs plus one source PDF),
12,220,812,451 bytes, and SHA-256
`42d68aa3fa65c28d0a15fd4bdb969ca7c9cc828827f4ab7a4dda62dfd42bd8db`.
The source PDF SHA-256 is
`b0e0fa3548e531a7b6570954190050d70019d3eeebfca172edca707a126d724f`;
the independent publication manifest has 9,239 entries and SHA-256
`cdb2fa353e88bf9a9329b9c7fab4feb1ee19945f7b0604b5a7ad872dea2e75d9`.

The real prepare completed with exit 0 in 2,061.44 seconds. Independent audit
passed in 433.312 seconds. The idempotent fast path completed with exit 0 in
1,065.401 seconds while an external 10 Hz monitor recorded 7,205 samples,
zero 7-Zip processes, and zero new staging observations. The post-fast audit
passed in 148.031 seconds.

Every CSV has the exact ordered header
`Horizontal_vibration_signals,Vertical_vibration_signals`, 32,768 numeric
rows, two author-confirmed H/V orientations, 25.6 kHz sampling, and one-minute
observation cadence. The 15 bearings are split across three conditions with
616, 1,566, and 7,034 contiguous windows. Bearing terminal outcomes remain
bearing-scope evidence only. Acceleration unit, absolute timestamps/timezone,
window label, onset, severity, life fraction, physical failure time, and true
RUL remain unknown.

### NASA IMS retained generation

Generation
`nasa-ims-v1-71cbedb9ec12f18af68eb175ba536c27df9c5de9a96fb4ac36d010f40e70ac0c`
and attestation
`b0da8f95a9f877e8a04c7c247dd4cbdf9d3ffc4fd93ee43c3c9f01e026253eb6`
remain the audited source of truth. Run 1 has 2,156 files, 2,477,767,237
bytes, inventory
`347863ccf244fb88d6f89303183bfb5af3405fa93f88f0d2f596baf27bc9b42f`,
and metadata
`21a12273c9575a57a8d816ddf3fd9f134867cfed5fd6af79a2b68138a401bfae`.
Run 2 has 984 files, 544,618,480 bytes, inventory
`94bd9093c2301c16cbae27e2c1695207b91c3acfa6bf90187a2f88ae3070ebff`,
and metadata
`3ff3ce76aee53f0aa57aa193ea6a609d7371100a5bef1db6cbaf4a1eef3b2958`.
Run 3 remains unextracted and quarantined at 4,448 documented versus 6,324
observed files. Its confirmatory, supervised, transfer, and RUL use remains
disabled.

### Scientific and loader gate

Both sources remain `prepared_semantically_gated`; neither is
`approved_for_research`. All scientific metrics remain `null` /
`not_available`, and `dataActuallyUsed` is empty. The Forzy GET payload has no
audited acceleration statistic, physical axis, or internal window contract.
The existing lab loader accepts one pristine ZIP/TAR per source and requires
an empty extraction destination, so it cannot consume the prepared XJTU
multipart generation or the two-run NASA generation. The real lab CLI was not
executed and no full/aggregate/Forzy delta, cross-bench result, or RUL evidence
was produced.

The read-only dry-run returned exit 0 with status
`not_run_external_data_gate` and `writesPerformed: false`. Its issues named
the unconfirmed Forzy policy, both gated source statuses, the absent singular
XJTU archive boundary, and the absent singular NASA metadata/archive boundary.
This legacy status string is CLI behavior; the versioned scientific artifacts
publish the more precise `not_run_semantic_gate` state.

### Fresh Task 2R4 verification

- RED factual assertion failed because the previous XJTU status and both
  versioned artifact statuses still described the obsolete external-data gate;
- GREEN JSON/schema/fact assertions passed after the evidence publication;
- exact primary-root hashes for both attestations and all three metadata files
  matched their recorded SHA-256 values without hashing CSV/RAR trees;
- public-fault CLI regression: initial `14 passed in 23.01s`; final staged
  rerun `14 passed in 24.83s`;
- research suite: `364 passed, 5 skipped, 1 warning in 48.57s`;
- the warning is the existing joblib physical-core fallback;
- no real lab execution, extraction, download, cleanup, deploy, production ML,
  or operational artifact mutation occurred.
