# Task 2R1 report — safe RAR3/RAR5 and exact multipart boundary

## Status

DONE

## Decisions

- Added a separate RAR API so the existing ZIP/TAR public APIs remain unchanged.
- Made archive parts and extraction limits immutable value objects. Multipart input is only an ordered caller-supplied sequence of exact path/SHA-256 pairs.
- Kept `rarfile>=4.5,<5` in the `research` optional dependency only. Installed `rarfile 4.5` only in `services/twinops/.venv` for this task.
- Used the first authorized volume with `rarfile`, `errors="strict"`, `crc_check=True`, and exact canonical `volumelist()` equality.
- Used 7-Zip only as a per-member streaming decoder. Python owns every `O_EXCL` target and the final atomic promotion.
- Defaults are intentionally conservative while admitting the largest verified NASA RAR: 10,000 files, 1 GiB per file, 8 GiB total, ratio 1,000, and 120 seconds per member.

## Files

- `services/twinops/src/twinops/research/downloads.py`
- `services/twinops/pyproject.toml`
- `services/twinops/tests/research/test_rar_downloads.py`
- `data/public/README.md`
- `.superpowers/sdd/2026-08-13-public-fault-datasets-lab-plan/task-2r1-report.md`

`data/public/sources.json` is modified by a separate coordinated task and is explicitly outside this task's ownership and commit.

## RED

- `python -m pytest services/twinops/tests/research/test_rar_downloads.py -q`
  - Initial tracer: collection error because `ArchivePart` did not exist.
- Same focused command after adding unsafe-name cases:
  - `9 failed, 10 passed`; control characters, Windows-invalid characters, wildcards, and listfile-leading names were still accepted.
- Same focused command for the extraction tracer:
  - Collection error because `safe_extract_rar_archive` did not exist.

## GREEN

- `python -m pytest services/twinops/tests/research/test_rar_downloads.py -q`
  - `62 passed, 1 skipped in 1.62s`.
  - Skip is explicit: set `TWINOPS_NASA_RAR_PATH` to opt into real NASA RAR inspection.
- `python -m pytest services/twinops/tests/research/test_rar_downloads.py services/twinops/tests/research/test_provenance.py -q`
  - `79 passed, 1 skipped in 2.20s`.

## Suites

- `python -m pytest services/twinops/tests/research/test_provenance.py -q`
  - `17 passed in 1.83s`; existing ZIP/TAR provenance behavior remained green.
- `python -m pytest services/twinops/tests/research -q`
  - `120 passed, 1 skipped, 1 warning in 27.63s`.
- `python -m pytest services/twinops/tests -q`
  - `335 passed, 3 skipped, 2 warnings in 35.02s`.
- `python -m pytest services/twinops/tests/ml/test_scorer.py::test_features_and_inference_p95_is_at_most_100_ms -q -s`
  - `p50=48.17 ms`, `p95=48.94 ms`, `1 passed in 0.91s`.
- `python -m compileall -q services/twinops/src services/twinops/tests`
  - Passed.
- `python -m pip check`
  - `No broken requirements found.`
- `git diff --check`
  - Passed; only Git's existing LF-to-CRLF notices were emitted.
- `git ls-files 'data/public/**/downloads/**' 'data/public/**/raw/**' 'data/public/**/*.rar' 'data/public/**/*.zip' 'data/public/**/*.7z'`
  - No tracked raw/archive files.

## Security self-review

- Rejects absent, duplicate, extra, reordered, middle-first, hash-mismatched, changed, linked, or reparse archive parts; no globbing or part guessing exists.
- Rejects traversal, absolute/drive/ADS paths, NUL/control characters, Windows-invalid characters, wildcard/listfile syntax, reserved devices, trailing dot/space, and case/file-directory collisions including implicit parent directories.
- Rejects symlinks, every `file_redir`, passwords/encrypted headers, unknown types, invalid sizes, over-count, oversized files/totals, and excessive member/archive compression ratios before output creation.
- 7-Zip receives a string argument list with `shell=False`, `--`, `-spd`, suppressed log/progress switches, no output-path switch, a per-member timeout, and stdout bound to a Python-created `O_EXCL` file.
- Nonzero status and any stderr diagnostic fail with sanitized messages. Byte count and SHA-256 are computed after streaming.
- The real tree is rescanned for regular files/directories, links/reparse points and extra/tampered entries; streamed, inspected, and filesystem inventories must agree.
- Every source part is rehashed immediately before atomic promotion. Any `BaseException` stops the child process where applicable, removes only the task-created temporary directory, preserves the original exception, and leaves no promoted partial tree.
- No `extractall`, bulk 7-Zip disk extraction, shell-built command, password fallback, mirror, data download, or operational artifact edit was introduced.

## Commit

- Message: `feat: safely prepare official rar datasets`
- Scope: the five Task 2R1 files listed above; the SHA is reported by Git after this report is committed.

## Concerns

- The opt-in real NASA smoke was skipped because `TWINOPS_NASA_RAR_PATH` was absent, as designed. The real source archive was not read or modified.
- Full-suite warnings are pre-existing/environmental: Starlette/httpx deprecation and joblib physical-core detection fallback.
- `data/public/sources.json` remains an uncommitted, separately owned workspace change and is excluded from this task's commit.

## Fix wave — publication race closure

### Status

DONE

### Decisions

- Moved the final staging filesystem attestation after every source-part re-hash and return that final attested inventory.
- Captured stable filesystem identity (`st_dev`, `st_ino`) for the task-created staging directory and any pre-existing empty destination.
- Treat a rename as successful only when the destination has the staging identity and the temporary path is absent.
- On any `BaseException`, remove only the temporary or destination path that still has the staging identity, verify removal, and restore a pre-existing empty destination state.
- Preserve the original exception object. Cleanup or restore failures are sanitized and appended with `BaseException.add_note()`.
- Reject an empty destination whose identity changes before promotion; never remove the replacement path.

### Files

- `services/twinops/src/twinops/research/downloads.py`
- `services/twinops/tests/research/test_rar_downloads.py`
- `.superpowers/sdd/2026-08-13-public-fault-datasets-lab-plan/task-2r1-report.md` (append only)

`data/public/sources.json` remains separately owned and excluded from this fix commit.

### RED

- Final-source-hash tampering regression:
  - `1 failed, 63 deselected`; no exception was raised and tampered staging was promoted.
- Rename-after-mutation regression:
  - `1 failed, 64 deselected`; `KeyboardInterrupt` was preserved but the destination remained published.
- Empty-destination identity replacement regression:
  - `1 failed, 75 deselected`; a different empty directory was removed and overwritten.
- Verification-required temporary reversion to the old cleanup handler:
  - `3 failed, 72 deselected`; cleanup failure masked the primary exception, no-op was silent, and an identity-replaced staging path was deleted.

### GREEN

- Focused publication/cleanup regressions:
  - `13 passed, 63 deselected in 1.55s`.
- Cleanup failure/no-op and changed-identity regressions after restoring the fix:
  - `3 passed, 72 deselected in 1.30s`.
- Final focused suite:
  - `75 passed, 1 skipped in 1.89s`.
- Real NASA inspection smoke with `TWINOPS_NASA_RAR_PATH=C:\Users\Luis\Documents\ChatGPT\forzy twinops\data\public\nasa-ims\raw\IMS\1st_test.rar`:
  - `1 passed in 3.81s`; read-only inspection, no extraction or data modification.

### Suites

- Existing ZIP/TAR provenance: `17 passed in 1.68s`.
- Research suite: `133 passed, 1 skipped, 1 warning in 27.34s`.
- Full Python suite: `348 passed, 3 skipped, 2 warnings in 34.97s`.
- Performance check immediately after the full suite:
  - Parallel sample: `p95=99.58 ms`, passed.
  - Isolated rerun: `p50=48.11 ms`, `p95=49.15 ms`, passed in `0.90s`.
- `python -m compileall -q services/twinops/src services/twinops/tests`: passed.
- `python -m pip check`: `No broken requirements found.`
- `git diff --check`: passed; only LF-to-CRLF notices were emitted.
- Raw/archive tracking query: no tracked ZIP, RAR, 7z, downloads, or raw files.

### Security self-review

- The source hashes now precede the final filesystem inventory, closing the reproduced stale-return/staging-tamper window.
- Pre- and post-mutation `Path.replace` failures were covered for `RuntimeError`, `KeyboardInterrupt`, and `SystemExit`; the exact original exception is re-raised.
- Rollback recognizes the task tree at either temporary or destination path by stable identity, checks that cleanup actually removed it, and never deletes an identity-replaced path.
- A failed or no-op `rmtree` cannot be silent: the original exception receives a sanitized cleanup note and remains primary.
- A destination that existed empty is recreated empty after rollback. A destination created or identity-replaced by another actor is preserved and causes fail-closed behavior.
- The legacy ZIP/TAR cleanup was not changed; this wave remains limited to the RAR boundary.

### Commit

- Message: `fix: close rar extraction publication races`
- Scope: the three fix-wave files listed above; Git reports the SHA after committing this append.

### Concerns

- The expected Starlette/httpx deprecation and joblib physical-core fallback warnings remain unchanged.
- The parallel performance sample approached the 100 ms limit under contention; the immediate isolated rerun returned to 49.15 ms p95, matching the ledger's prior environmental ruling.
- No real RAR extraction was requested or performed; the required real-source smoke inspected the authorized NASA RAR read-only.

## Fix wave - uninitialized staging cleanup

### Status

DONE

### Decisions

- Wrapped RAR staging creation and both identity observations in a dedicated acquisition handler so `RuntimeError`, `KeyboardInterrupt`, and `SystemExit` cannot bypass cleanup handling.
- Captured a provisional `st_dev`/`st_ino` identity immediately after `mkdtemp`, then required the normal identity observation to match before returning the staging directory.
- Limited pre-extraction cleanup to `Path.rmdir()` after proving the path still has the provisional identity and is empty; no recursive deletion is used in this window.
- Verified that `rmdir` actually removed the staging path. A thrown or no-op cleanup remains secondary, is recorded with a sanitized `BaseException.add_note()`, and never masks the exact original exception object.
- Refused cleanup when the path is a symlink, reparse point, identity replacement, or non-empty directory.

### Files

- `services/twinops/src/twinops/research/downloads.py`
- `services/twinops/tests/research/test_rar_downloads.py`
- `.superpowers/sdd/2026-08-13-public-fault-datasets-lab-plan/task-2r1-report.md` (append only)

`data/public/sources.json` remains separately owned and is excluded from this commit.

### RED

- Initial-identity failure tracer for `RuntimeError`, `KeyboardInterrupt`, and `SystemExit`:
  - `3 failed, 76 deselected`; each failure left an empty `.raw-rar-extract-*` staging directory.

### GREEN

- Initial-identity cleanup matrix: `3 passed, 76 deselected`.
- Throwing/no-op `rmdir` regressions: `2 passed, 79 deselected`.
- Symlink/reparse/unowned/non-empty refusal regressions: `4 passed, 81 deselected`.
- Final focused RAR suite: `84 passed, 1 skipped in 1.97s`.
- Real NASA inspection smoke with `TWINOPS_NASA_RAR_PATH=C:\Users\Luis\Documents\ChatGPT\forzy twinops\data\public\nasa-ims\raw\IMS\1st_test.rar`:
  - `1 passed in 4.44s`; read-only inspection, no extraction or data modification.

### Suites

- Existing ZIP/TAR provenance: `17 passed in 1.67s`.
- Research suite: `142 passed, 1 skipped, 1 warning in 27.98s`.
- Full Python suite: `357 passed, 3 skipped, 2 warnings in 35.97s`.
- Performance check immediately after the full suite: `p50=48.37 ms`, `p95=49.31 ms`, `p99=49.31 ms`; `1 passed in 0.93s`.
- `python -m compileall -q services/twinops/src services/twinops/tests`: passed.
- `python -m pip check`: `No broken requirements found.`
- `git diff --check`: passed; only LF-to-CRLF notices were emitted.
- Raw/archive tracking query: no tracked ZIP, RAR, 7z, downloads, or raw files.

### Security self-review

- Cleanup covers ordinary exceptions and process-control `BaseException` subclasses while re-raising the exact original object.
- A successful cleanup removes only the newly created, still-empty directory with the captured filesystem identity and verifies absence afterward.
- Cleanup failure details are reduced to the exception class in the note; sensitive exception text and paths are not propagated.
- Symlink, reparse, identity-replaced, and non-empty paths survive for manual review and receive a sanitized cleanup note.
- The three publication-race fixes from the prior wave remain covered by the final focused and full suites.
- The legacy ZIP/TAR path and downloaded data were not changed.

### Commit

- Message: `fix: clean uninitialized rar staging`
- Scope: the three fix-wave files listed above; Git reports the SHA after committing this append.

### Concerns

- If even the provisional identity cannot be established, deletion is deliberately refused because ownership cannot be proven; the original exception receives a sanitized cleanup note and the empty path is left for manual review.
- The expected Starlette/httpx deprecation and joblib physical-core fallback warnings remain unchanged.
- No real RAR extraction was requested or performed; the required real-source smoke inspected the authorized NASA RAR read-only.

## Fix wave - capability-bound first identity cleanup

### Status

DONE

### Decisions

- Bound cleanup to a capability created immediately after `mkdtemp` and before the first stable-inode observation: an `O_EXCL`, mode-0600 marker containing a random 32-byte token.
- Used optional `O_BINARY`/`O_NOFOLLOW` flags portably and flushed the marker before treating it as established.
- Required the staging path to remain a regular, non-reparse directory and the marker to be its unique regular, non-link entry with the exact token before unlinking it.
- Removed the marker, verified its absence and rechecked an empty plain staging directory before returning control to extraction, so the marker cannot enter streaming, filesystem attestation, `RawInventory`, or the promoted destination.
- On failures before a marker exists, attempted only `rmdir` of the exact newly created path after proving it is a plain empty directory; no recursive cleanup or path search is used.
- Preserved the exact original `RuntimeError`, `KeyboardInterrupt`, or `SystemExit`; cleanup failures add only a sanitized exception-class note.

### Files

- `services/twinops/src/twinops/research/downloads.py`
- `services/twinops/tests/research/test_rar_downloads.py`
- `.superpowers/sdd/2026-08-13-public-fault-datasets-lab-plan/task-2r1-report.md` (append only)

`data/public/sources.json` remains separately owned and is excluded from this commit.

### RED

- First-identity-observation tracer for `RuntimeError`, `KeyboardInterrupt`, and `SystemExit`:
  - `3 failed, 85 deselected`; all three retained an empty staging directory and added a cleanup note because no ownership identity had been captured.

### GREEN

- First-observation matrix after capability binding: `3 passed, 85 deselected`.
- Token-generation and pre-marker `O_EXCL` open failures: `3 passed, 88 deselected`.
- Partial marker-write refusal: `1 passed, 99 deselected`; the invalid marker/path survived with a sanitized note because ownership could not be proven.
- Pre-marker throwing/no-op `rmdir` plus symlink/reparse/swapped-non-empty/non-empty refusal: `6 passed, 100 deselected`.
- Missing/swapped/symlink/reparse/non-regular/unreadable marker, invalid token, and extra-entry refusal: `8 passed, 91 deselected`.
- Final focused RAR suite: `105 passed, 1 skipped in 2.40s`.
- Real NASA inspection smoke with `TWINOPS_NASA_RAR_PATH=C:\Users\Luis\Documents\ChatGPT\forzy twinops\data\public\nasa-ims\raw\IMS\1st_test.rar`:
  - `1 passed in 4.14s`; read-only inspection, no extraction or data modification.

### Suites

- Existing ZIP/TAR provenance: `17 passed in 1.83s`.
- Research suite: `163 passed, 1 skipped, 1 warning in 29.29s`.
- Full Python suite: `378 passed, 3 skipped, 2 warnings in 41.32s`.
- Performance check immediately after the full suite: `p50=54.81 ms`, `p95=75.68 ms`, `p99=75.68 ms`; `1 passed in 1.26s`.
- `python -m compileall -q services/twinops/src services/twinops/tests`: passed.
- `python -m pip check`: `No broken requirements found.`
- `git diff --check`: passed; only LF-to-CRLF notices were emitted.
- Raw/archive tracking query: no tracked ZIP, RAR, 7z, downloads, or raw files.

### Security self-review

- Cleanup after either identity observation fails no longer depends on that observation succeeding; the random marker capability is already established.
- Marker validation rejects a changed path, missing/replaced marker, symlink, reparse point, non-regular marker, invalid token, unreadable marker, or any additional entry without deleting the uncertain tree.
- An incomplete marker is not promoted to a capability. It remains for manual review with a sanitized note instead of being recursively removed.
- Before marker establishment, cleanup uses only non-following empty-directory semantics and verifies disappearance; throwing or no-op `rmdir` remains secondary to the original exception.
- The exact successful inventory and promoted tree contain only the inspected archive member, explicitly proving that the capability marker was consumed before extraction.
- Final focused and full suites retain coverage for source re-hash ordering, post-rename rollback, verified cleanup, and destination identity races closed in earlier waves.

### Commit

- Message: `fix: bind rar staging cleanup capability`
- Scope: the three fix-wave files listed above; Git reports the SHA after committing this append.

### Concerns

- The expected Starlette/httpx deprecation and joblib physical-core fallback warnings remain unchanged.
- The isolated performance p95 was 75.68 ms, below the 100 ms gate but above the prior low-contention samples.
- When marker contents are incomplete or any path/capability fact is unprovable, fail-closed behavior deliberately leaves the path for manual review and annotates the original exception.
- No real RAR extraction was requested or performed; the required real-source smoke inspected the authorized NASA RAR read-only.
