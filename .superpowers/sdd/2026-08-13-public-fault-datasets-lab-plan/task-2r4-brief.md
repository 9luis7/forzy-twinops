# Task 2R4: Publish real preparation evidence and close the semantic gate honestly

## Objective

Replace the obsolete pre-download/pre-preparation story with the exact, independently
verified NASA IMS and XJTU-SY preparation facts. Do not manufacture labels, units,
Forzy comparability, cross-bench metrics, or RUL evidence. The final versioned state
must make it obvious that the real data are prepared and immutable while the planned
supervised laboratory remains blocked by scientific semantics and by the legacy
ZIP/TAR-only lab-loader boundary.

## Base and ownership

- Worktree: `C:/Users/Luis/Documents/ChatGPT/forzy twinops/.worktrees/public-fault-real-data`
- Required base: `9903011f95e576be506a0f95fee49cd42aa0799b`
- Owned files:
  - `data/public/sources.json`
  - `data/public/README.md`
  - `artifacts/ml-public/ablation-report.json`
  - `artifacts/ml-public/dataset-manifest.json`
  - `docs/jornada/experimento-datasets-publicos.md`
  - `.superpowers/sdd/2026-08-13-public-fault-datasets-lab-plan/task-2r3-report.md` (append only)
  - `.superpowers/sdd/2026-08-13-public-fault-datasets-lab-plan/task-2r4-report.md` (new)
  - this brief (force-add because `.superpowers/` is ignored)
- No-touch: real/downloaded/prepared data, either XJTU staging, `scripts/`, production
  ML, adapters, feature extraction, deployment work, and Plan05.
- You are not alone in this repository. Preserve all edits outside this ownership and
  do not revert, move, delete, or rewrite other agents' work.

## Non-negotiable rulings

1. The failed XJTU staging
   `.xjtu-sy-generation-7x6h7sqm` stays exactly in place. Never read it as the source
   of truth, move it, delete it, promote it, or list its full contents.
2. The successful XJTU generation is
   `xjtu-sy-v1-8c7e9d8b7c272002a4d44b021931aaf6500f013574db60839bae2af3aa0fee1a`.
   Record only already-audited facts; do not rehash 12.22 GB.
3. Keep both datasets `prepared_semantically_gated`, never
   `approved_for_research`.
4. All scientific metrics remain `null` / `not_available`. Do not infer per-window
   labels from terminal bearing outcomes, sequence position, filename order, or the
   final observation. Do not infer true RUL or life fraction.
5. Acceleration unit remains `unknown`. XJTU H/V is author-confirmed orientation,
   not a unit. NASA channels remain opaque. The Forzy GET payload exposes values but
   no audited acceleration statistic/window/axis contract, so
   `accelerationRmsSemanticsConfirmed` stays false.
6. The original lab CLI is not executed in real mode. It only accepts one pristine
   ZIP/TAR per source and an empty extraction destination; the real sources are one
   prepared multipart-RAR generation plus a two-run prepared NASA generation.
7. Production artifacts under `artifacts/ml/real-forzy` and production code under
   `services/twinops/src/twinops/ml` must have zero diff.

## Exact evidence to persist

### XJTU-SY

- status: `prepared_semantically_gated`
- generation ID: `xjtu-sy-v1-8c7e9d8b7c272002a4d44b021931aaf6500f013574db60839bae2af3aa0fee1a`
- prepared path: `xjtu-sy/prepared/<generationId>`
- attestation path: `<preparedPath>/attestation.json`
- attestation SHA-256:
  `49de3ae74df4de489a966a77ccf6af647a58e60ceb2515934b9c62bf299277a5`
- metadata path: `<preparedPath>/metadata.json`
- metadata SHA-256:
  `4876cc6540a8c972c63b890d111d1a4d60322f5addd2a317b0b058246020e8f8`
- raw inventory: 9,217 files = 9,216 CSV + one source PDF,
  12,220,812,451 bytes, SHA-256
  `42d68aa3fa65c28d0a15fd4bdb969ca7c9cc828827f4ab7a4dda62dfd42bd8db`
- source PDF SHA-256:
  `b0e0fa3548e531a7b6570954190050d70019d3eeebfca172edca707a126d724f`
- publication manifest: 9,239 entries, SHA-256
  `cdb2fa353e88bf9a9329b9c7fab4feb1ee19945f7b0604b5a7ad872dea2e75d9`
- real prepare: exit 0, 2,061.44 seconds
- independent audit: PASS, 433.312 seconds
- idempotent fast path: exit 0, 1,065.401 seconds; external 10 Hz monitor,
  7,205 samples, zero 7-Zip and zero new staging observations
- post-fast audit: PASS, 148.031 seconds
- content: exact ordered ASCII header
  `Horizontal_vibration_signals,Vertical_vibration_signals`, 32,768 numeric rows,
  two axes, 25.6 kHz, one observation per minute; 3 conditions and 15 bearings with
  contiguous sequence counts 616/1,566/7,034 by condition
- terminal outcomes exist only at bearing scope; every window label, onset, severity,
  life fraction, physical failure time, absolute timestamp/timezone, and true RUL
  remains unknown.

### NASA IMS

- retain the existing successful generation and hashes exactly as already recorded:
  generation `nasa-ims-v1-71cbedb9ec12f18af68eb175ba536c27df9c5de9a96fb4ac36d010f40e70ac0c`,
  attestation SHA
  `b0da8f95a9f877e8a04c7c247dd4cbdf9d3ffc4fd93ee43c3c9f01e026253eb6`
- run 1: 2,156 files, 2,477,767,237 bytes, inventory
  `347863ccf244fb88d6f89303183bfb5af3405fa93f88f0d2f596baf27bc9b42f`,
  metadata `21a12273c9575a57a8d816ddf3fd9f134867cfed5fd6af79a2b68138a401bfae`
- run 2: 984 files, 544,618,480 bytes, inventory
  `94bd9093c2301c16cbae27e2c1695207b91c3acfa6bf90187a2f88ae3070ebff`,
  metadata `3ff3ce76aee53f0aa57aa193ea6a609d7371100a5bef1db6cbaf4a1eef3b2958`
- run 3 remains quarantined: 4,448 documented versus 6,324 observed; no extraction
  and no confirmatory, supervised, transfer, or RUL use
- 20 kHz and 20,480 rows/window are factual; acceleration unit, physical axes,
  source timezone, window label/onset/severity/life fraction/RUL remain unknown.

## Artifact contract

- Update both `artifacts/ml-public` JSON files from the obsolete
  `not_run_external_data_gate` story to `not_run_semantic_gate`.
- Keep `metrics: null`, all scientific claims null/false, and `dataActuallyUsed: []`.
- State that data were prepared/audited but not loaded into an experiment.
- Include the exact generation, metadata, attestation, and inventory hashes needed to
  reproduce the gate decision. Keep the two JSONs internally consistent and use one
  factual generated timestamp for this evidence publication.
- The reason must name both blockers:
  1. no audited common per-window labels/unit/Forzy measurement semantics;
  2. the current lab loader does not consume prepared multipart/multi-run generations.
- The resume conditions must require a reviewed prepared-generation loader plus an
  explicit audited scientific policy. Do not present the current real-run command as
  safe or ready.

## Documentation contract

- Rewrite the experiment narrative in four explicit sections: Evidence, Result,
  Limitation, Next experiment.
- Correct every stale statement that downloads or preparation are pending.
- State that no full/aggregate/Forzy delta or cross-bench baseline comparison exists.
- Describe the next honest experiment as a separate design choice: either obtain
  authoritative labels/unit/Forzy semantics for the planned supervised comparison,
  or explicitly approve and design a different unsupervised lifecycle-drift study.
  Do not silently redefine this plan.
- Append the real-run and semantic-gate outcome to Task 2R3 report, marking all older
  `awaiting review`/`no extraction` statements historical and superseded.

## Verification

Run only read-only/lightweight checks; never rehash the real trees:

1. JSON parse and schema/fact assertions for `sources.json` and both artifacts.
2. Assert every referenced metadata/attestation file exists under the primary data
   root and its small JSON SHA matches the recorded value; do not hash CSV/RAR trees.
3. Assert XJTU/NASA statuses are `prepared_semantically_gated`, metrics are null,
   `dataActuallyUsed` is empty, and no source is `approved_for_research`.
4. Run public-fault CLI tests and research tests if documentation-only changes do not
   require production changes.
5. Run the CLI in `--dry-run` only and record its exact fail-closed status/issues. It
   may expose the legacy-loader incompatibility; that is evidence, not a reason to
   loosen the source status.
6. `git diff --check` plus protected-scope checks for production ML, Plan05, real raw,
   downloaded, and prepared paths.

## Delivery

- Self-review every factual hash and count against the bound attestation files.
- Create one atomic commit: `docs: publish real public dataset gate evidence`.
- Return the SHA, exact changed files, test/dry-run output, and any residual concern.
- No push, merge, deploy, download, extraction, cleanup, or real lab execution.
