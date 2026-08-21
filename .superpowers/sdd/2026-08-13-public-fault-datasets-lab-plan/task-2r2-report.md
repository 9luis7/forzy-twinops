# Task 2R2 report — attested NASA IMS runs 1/2 and quarantined run 3

## Status

IMPLEMENTATION DONE — independent review pending.

Base SHA: `d9388cda89b398c1067608fd8d7e8a95af7f4050`.

## Decisions

- Added an immutable `NasaImsPreparationConfig`/`NasaImsPreparationResult` surface and `prepare_nasa_ims(config)` without disk search, globbing, download, default archive selection, or local-path serialization.
- Bound the three caller-supplied absolute single-volume RAR paths to the official SHA-256 values and required a caller-supplied absolute trusted 7-Zip executable.
- Inspected and validated all three source boundaries before creating `prepared/` output. Runs 1 and 2 are extracted once each through the reviewed Task 2R1 public API; run 3 is never extracted.
- Enforced 2,156/984/6,324 regular files, total member counts 2,157/985/6,326, exact source prefixes and first/last filenames, and the run-3 `4,448 + 1,876` contradiction boundary through `2004.04.18.02.42.55`.
- Stream-validated every prepared numeric file for exact rows/columns, blank/ragged/non-finite data, raw byte count and SHA-256, then re-attested the complete filesystem tree.
- Published runs 1 and 2, both metadata files and the attestation as one content-addressed generation directory. Exact existing generations are manifest-verified idempotently; mismatches are preserved and rejected.
- Kept the scientific gates closed: `accelerationUnit="unknown"`, opaque `source-channel-*` axes, no timezone/UTC conversion, unknown window state/onset/severity/RUL, and null `lifeFraction`/per-window terminal mode.
- Kept 2,000 rpm and 6,000 lb at rig scope. Terminal outcomes live only in run/bearing evidence. Run-1 bearing-4 retains both source-authored observations.
- Bound bearing-4 provenance to `nasa-ims-internal-readme-cf46d37c` (local PDF plus exact hash) and `qiu-et-al-jsv-2006` (Journal of Sound and Vibration DOI/URL); no generic or invented source label remains.
- Tightened `iter_ims` to require a positive integer `samplesPerWindow`, exact matrix rows, globally unique bearing IDs across runs, and `(run_id, bearing_id, sequence_index)` uniqueness.
- Added the ignored `data/public/*/prepared/` boundary. Generated raw/prepared/metadata payloads remain local and untracked.

## Files

- `.gitignore`
- `data/public/README.md`
- `services/twinops/src/twinops/research/datasets/ims_preparation.py`
- `services/twinops/src/twinops/research/datasets/ims.py`
- `services/twinops/tests/research/test_ims_preparation.py`
- `services/twinops/tests/research/test_ims_adapter.py`
- `services/twinops/tests/research/test_public_fault_cli.py` — only the authorized synthetic NASA metadata fixture update
- `.superpowers/sdd/2026-08-13-public-fault-datasets-lab-plan/task-2r2-report.md`

`data/public/sources.json` is a separately owned, pre-existing workspace modification. It remains unstaged and excluded from this commit.

## RED evidence

- Adapter tracer: `6 failed, 3 passed`; absent/invalid `samplesPerWindow` and wrong matrix rows were accepted.
- Initial 2R2 tracer: collection failed because `twinops.research.datasets.ims_preparation` did not exist.
- Orchestration tracer: collection failed because `NasaImsPreparationResult`/`prepare_nasa_ims` did not exist.
- Global-bearing tracer: `1 failed, 9 passed`; a bearing ID reused across two runs was accepted.
- CLI regression: the existing synthetic NASA fixture omitted `samplesPerWindow` and the success path returned `failed_precondition`.
- Fixture correction tracer: the provisional value `4` failed honestly because `_signal()` produces 128 raw rows. The final fixture value `128` is derived from its bytes and is not a production default.
- Bearing-4 provenance tracer failed while generic source refs remained; the exact PDF/Qiu registry made it green.
- Staging-acquisition tracer: `3 failed`; `RuntimeError`, `KeyboardInterrupt`, and `SystemExit` during the first staging identity observation left empty generation directories.

## GREEN and regression evidence

- `python -m pytest services/twinops/tests/research/test_ims_preparation.py services/twinops/tests/research/test_ims_adapter.py -q`
  - `33 passed, 1 skipped in 2.94s`.
- `python -m pytest services/twinops/tests/research/test_public_fault_cli.py::test_cli_success_path_extracts_binds_provenance_and_reports_both_directions -q`
  - `1 passed in 3.73s`.
- `python -m pytest services/twinops/tests/research -q`
  - `210 passed, 2 skipped, 1 warning in 30.19s`.
- `python -m pytest services/twinops/tests -q`
  - `425 passed, 4 skipped, 2 warnings in 41.38s`.
- `python -m pytest services/twinops/tests/ml/test_scorer.py::test_features_and_inference_p95_is_at_most_100_ms -q -s`
  - `p50=50.58 ms`, `p95=53.59 ms`, `p99=53.59 ms`; passed.
- `python -m compileall -q services/twinops/src services/twinops/tests`
  - Passed.
- `python -m pip check`
  - `No broken requirements found.`
- `git diff --check`
  - Passed; only existing Windows LF-to-CRLF notices were emitted.
- Raw/archive/prepared tracking query
  - No tracked ZIP, RAR, 7z, download, raw, or prepared file.

## Real-source smoke gate

The new read-only smoke requires both `TWINOPS_NASA_RAR_DIRECTORY` and `TWINOPS_TRUSTED_7Z_PATH`. It was deliberately not executed because the controller explicitly prohibited real execution in Task 2R2. Fresh explicit result:

- `1 skipped in 1.75s` with the reason to set both variables.
- No source RAR, `data/public/nasa-ims/raw`, or prepared generation was modified.

## Atomicity and semantic self-review

- All three inspections complete before `destination_root` or staging is created.
- Run 3 has no extraction call or output path; its compact quarantine attestation marks every metric family excluded.
- Runs 1/2 are one containing generation. Every pre-promotion `BaseException` removes only the task path: by captured filesystem identity after acquisition, or by verified plain-empty semantics in the narrow pre-identity window.
- The first identity failure is covered for ordinary and process-control exceptions. Cleanup failure remains secondary via a sanitized exception note; the original object is re-raised.
- Existing generation content is never merged. Exact content is verified by the whole-tree path/size/hash manifest; any difference is rejected while preserving the existing path.
- Post-rename identity and manifest are rechecked before returning. Raw files are hashed while numeric rows are streamed; no full run is held in memory.
- Metadata JSON uses canonical key ordering/separators. IDs bind the official archive hash and raw inventory hash; generation binding includes both prepared inventories and all three archive hashes.
- Metadata `files` exactly equals each `RawInventory`. Every raw column is mapped once, bearing IDs include run identity, and timestamp filename components remain local evidence with timezone unknown.
- No terminal outcome is copied to a window/channel label. No unit, axis physics, timezone, fault onset, severity, life fraction, or RUL is inferred.
- No Task 2R1 private helper, bulk extractor, `extractall`, shell command, download, CLI logic, feature/experiment logic, operational artifact, deployment file, push, or merge was introduced.

## Concerns

- Full extraction/shape validation of the 3,140 real run-1/run-2 files remains intentionally unexecuted until the controller authorizes the exact real-source paths. Unit/orchestration tests use bounded numeric fixtures and faked public RAR APIs.
- The high-level pre-identity cleanup deliberately removes only a plain still-empty staging directory. If ownership becomes ambiguous through replacement/tamper, cleanup fails closed and preserves the path for review rather than deleting uncertain data.
- The expected Starlette/httpx deprecation and joblib physical-core fallback warnings remain unchanged.
- The Qiu article is referenced by DOI/URL as source evidence; no local article copy was downloaded or committed.

## Commit

Message: `feat: prepare attested NASA IMS runs`.

The final SHA is reported by Git after this report is included in the atomic commit.

## Fix wave - independent review closure (2026-08-21)

### Scope and result

This strict TDD wave starts from `504632e4354b45ea327a2962d6114eb43fbe5817`
and closes the independent review's four Important findings (zero Critical). The
public constructor and result serialization remain compatible: the executable
attestation is a private `init=False`, `repr=False`, `compare=False` config field,
and no executable path or local identity is added to the public attestation.

### RED evidence

- Post-mutation `Path.rename()` fault injection left the promoted final generation
  behind for `RuntimeError`, `KeyboardInterrupt`, and `SystemExit`: `3 failed, 3
  passed`. The three pre-mutation cases were the control passes.
- Zero-inode and unstable-identity tracers were both accepted, and a swapped empty
  staging replacement was erased for all three BaseException families: `5 failed`.
- Simulated symlink-mode and reparse-attribute final roots reached manifest/
  idempotency without root validation: `2 failed, 1 skipped` (the additional real
  Windows directory-symlink tracer lacked local privilege).
- The 7-Zip boundary accepted reparse executable/ancestor paths, had no config
  attestation, accepted changed bytes and same-byte file/parent replacements, and
  invoked the second extraction after substitution: `7 failed`.

### Corrections and safety decisions

- Cleanup now searches only the known staging/final candidates for the captured
  filesystem identity. A rename that mutates and then raises rolls back the owned
  final tree; a pre-mutation raise removes the owned staging tree. The exact original
  exception object is re-raised, and a sanitized note is added only if cleanup fails.
- Directory ownership requires positive integer device/inode values observed stably.
  The just-created path also receives a stable creation guard before ownership. If
  that path is replaced, cleanup refuses to erase the replacement and records the
  cleanup failure on the original exception.
- Any existing final generation root is validated as a stable plain directory (not
  symlink, junction, or reparse point) before manifest traversal, then revalidated
  after traversal. Unsafe roots and their external targets are preserved; only the
  owned staging candidate is eligible for cleanup.
- The config now attests the absolute 7-Zip path, every directory ancestor from the
  filesystem root, the regular executable identity, byte size, and SHA-256. Every
  component is checked with `lstat` and must be stable/non-symlink/non-reparse. The
  complete attestation is re-created and compared at preflight and immediately before
  each run-1/run-2 extraction; the extractor receives the path stored in the verified
  attestation. Same-byte replacements fail on object or ancestor identity. No local
  7-Zip path is hardcoded.

### Fresh GREEN and gate evidence

- Focused preparation: `43 passed, 2 skipped in 4.44s`.
- Research suite: `230 passed, 3 skipped, 1 warning in 36.73s`.
- Full Python suite: `445 passed, 5 skipped, 2 warnings in 46.27s`.
- Explicit real-source smoke remained read-only and opt-in: `1 skipped in 2.35s`;
  no real archive was extracted and no prepared generation was written.
- Performance gate had one concurrent-load outlier at `p95=100.87 ms`; the immediate
  isolated fresh rerun passed at `p50=50.86 ms`, `p95=p99=52.69 ms`.
- `compileall`, `pip check`, `git diff --check`, and the tracked raw/archive/prepared
  query passed. The only emitted diff notices were existing Windows LF/CRLF notices.

### Self-review and remaining boundary

- All new destructive cleanup remains identity-gated and limited to the task-owned
  staging/final candidates. Ambiguity preserves data and annotates the original error.
- The attested executable is revalidated with no application operation between that
  check and the Task 2R1 path-based extraction call. A kernel-handle execution API
  would be required to eliminate the final OS scheduling interval; changing the
  reviewed Task 2R1 public boundary is outside this wave's ownership.
- Full extraction of the 3,140 real run-1/run-2 files remains deliberately unexecuted.
  No raw, prepared, archive, deployment, CLI, experiment, or `sources.json` change is
  part of this fix commit.

Commit message: `fix: harden NASA IMS publication ownership`.

## Fix wave 2 - guard binding and exception preservation (2026-08-21)

### Re-review findings and RED evidence

This wave starts from `d26df0ec40df474a6db2319e10c5ae596a32b655` and
closes two further Important findings from independent re-review.

- A stable replacement inserted after the creation guard but before
  `_directory_identity()` became the owned directory. Across a later
  `RuntimeError`, `KeyboardInterrupt`, and `SystemExit`, cleanup erased that
  replacement and its sentinel. The no-injected-error case published the
  replacement, and a zero inode was rejected only after extraction/promotion:
  `5 failed`.
- If ambiguous cleanup failed and the primary exception's `add_note()` raised
  `RuntimeError`, `KeyboardInterrupt`, or `SystemExit`, that note failure masked
  the primary object: `3 failed`. Each tracer compared the observed exception
  to the original with `is`.

### Minimal corrections

- Ownership acquisition now validates the returned device/inode pair, captures
  a second stable full creation guard, compares every existing guard signal
  (device, inode, mode, file attributes, reparse tag, and ctime) plus the
  acquired identity, and only then constructs `_OwnedDirectory`. Any divergence
  fails before extraction. The actually-created displaced tree, replacement
  path, and replacement sentinel are all preserved because no uncertain object
  receives ownership.
- Cleanup-note attachment is isolated in a defensive helper. Missing,
  non-callable, or BaseException-raising `add_note` behavior is swallowed only
  for the secondary annotation attempt; the original outer `raise` always
  rethrows the exact primary object. Normal cleanup failures still receive the
  existing sanitized note.

### Fresh verification

- Focused preparation: `51 passed, 2 skipped in 5.27s`.
- Research suite: `238 passed, 3 skipped, 1 warning in 33.96s`.
- Full Python suite: `453 passed, 5 skipped, 2 warnings in 43.36s`.
- Real read-only executable-attestation smoke validated the versioned trusted
  executable, seven plain ancestors, size `576512`, and SHA-256
  `2bff20bd679d45166b8c2d039044a4ca16189e6d69ff9c82345b4c1306986ec4`;
  the destination remained absent and 7-Zip was not executed.
- Isolated performance gate passed at `p50=49.25 ms`, `p95=p99=50.69 ms`.
- `compileall`, `pip check`, `git diff --check`, and raw/archive/prepared
  tracking passed.

### Self-review

- The guard comparison occurs before any extraction call or ownership grant.
  Both stable-swap and invalid-identity paths are fail-closed.
- Ambiguous cleanup never deletes either the displaced mkdtemp tree or the
  replacement path. Hostile secondary annotation cannot change exception
  control flow.
- No real archive extraction, 7-Zip execution, raw/prepared output, source
  registry change, push, or merge was performed.

Commit message: `fix: bind NASA IMS staging ownership`.
