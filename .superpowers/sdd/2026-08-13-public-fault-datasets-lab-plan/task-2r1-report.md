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
