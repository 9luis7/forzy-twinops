# Task 2R4 report: real preparation evidence and semantic gate

## Outcome

Status: IMPLEMENTED AND LOCALLY VERIFIED. The obsolete pre-download and
pre-preparation story was replaced by the exact audited XJTU-SY and NASA IMS
generations. Both sources remain `prepared_semantically_gated`; neither was
promoted to `approved_for_research`. The experiment was not run, its metrics
remain null, and `dataActuallyUsed` remains empty.

## Evidence published

### XJTU-SY

- generation:
  `xjtu-sy-v1-8c7e9d8b7c272002a4d44b021931aaf6500f013574db60839bae2af3aa0fee1a`;
- attestation:
  `49de3ae74df4de489a966a77ccf6af647a58e60ceb2515934b9c62bf299277a5`;
- metadata:
  `4876cc6540a8c972c63b890d111d1a4d60322f5addd2a317b0b058246020e8f8`;
- raw inventory: 9,217 files (9,216 CSV plus one source PDF),
  12,220,812,451 bytes,
  `42d68aa3fa65c28d0a15fd4bdb969ca7c9cc828827f4ab7a4dda62dfd42bd8db`;
- source PDF:
  `b0e0fa3548e531a7b6570954190050d70019d3eeebfca172edca707a126d724f`;
- publication manifest: 9,239 entries,
  `cdb2fa353e88bf9a9329b9c7fab4feb1ee19945f7b0604b5a7ad872dea2e75d9`;
- real prepare: exit 0 in 2,061.44 seconds;
- independent audit: PASS in 433.312 seconds;
- idempotent fast path: exit 0 in 1,065.401 seconds, externally observed at
  10 Hz for 7,205 samples with zero 7-Zip and zero new staging observations;
- post-fast audit: PASS in 148.031 seconds.

The published content contract records the exact ordered ASCII header,
32,768 numeric rows, two H/V orientations, 25.6 kHz sampling, one-minute
cadence, three conditions, 15 bearings, and 616/1,566/7,034 contiguous windows
by condition. It does not infer an acceleration unit, timestamps, per-window
labels, onset, severity, life fraction, physical failure time, or true RUL.
Terminal outcomes remain bearing-scope evidence.

### NASA IMS

- generation:
  `nasa-ims-v1-71cbedb9ec12f18af68eb175ba536c27df9c5de9a96fb4ac36d010f40e70ac0c`;
- attestation:
  `b0da8f95a9f877e8a04c7c247dd4cbdf9d3ffc4fd93ee43c3c9f01e026253eb6`;
- run 1: 2,156 files, 2,477,767,237 bytes, inventory
  `347863ccf244fb88d6f89303183bfb5af3405fa93f88f0d2f596baf27bc9b42f`,
  metadata
  `21a12273c9575a57a8d816ddf3fd9f134867cfed5fd6af79a2b68138a401bfae`;
- run 2: 984 files, 544,618,480 bytes, inventory
  `94bd9093c2301c16cbae27e2c1695207b91c3acfa6bf90187a2f88ae3070ebff`,
  metadata
  `3ff3ce76aee53f0aa57aa193ea6a609d7371100a5bef1db6cbaf4a1eef3b2958`;
- run 3: quarantined and unextracted at 4,448 documented versus 6,324
  observed files, excluded from every scientific metric.

The factual 20 kHz and 20,480 rows/window contract is recorded. Acceleration
unit, physical axes, timezone, per-window state/onset/severity, life fraction,
and true RUL remain unknown.

## Gate decision

The prepared data were not loaded into an experiment. Two independent
blockers remain:

1. no audited common per-window labels, acceleration unit, or Forzy
   statistic/window/axis semantics;
2. the current loader consumes one pristine ZIP/TAR per source into an empty
   destination, not the immutable prepared multipart XJTU and multi-run NASA
   generations.

The next valid execution requires a reviewed read-only prepared-generation
loader plus an explicit audited scientific policy. Alternatively, the team
may explicitly approve and design a separate unsupervised lifecycle-drift
study; that would be a new scientific design, not a silent redefinition of
this supervised plan.

## Verification

- base/HEAD before edits:
  `9903011f95e576be506a0f95fee49cd42aa0799b`, clean worktree;
- RED factual gate: exit 1 on the obsolete source/artifact statuses;
- GREEN JSON/schema/fact gate: `FACT_ASSERTIONS=PASS`;
- primary-root exact-file verification: XJTU attestation/metadata and NASA
  attestation/run-1 metadata/run-2 metadata all existed and matched their
  recorded SHA-256; no CSV or RAR tree was hashed;
- CLI dry-run: exit 0, `not_run_external_data_gate`,
  `writesPerformed: false`; issues were the unconfirmed Forzy policy, the two
  gated statuses, and the legacy singular archive/metadata boundaries;
- public-fault CLI regression: initial `14 passed in 23.01s`; final staged
  rerun `14 passed in 24.83s`;
- research suite: `364 passed, 5 skipped, 1 warning in 48.57s`;
- warning: pre-existing joblib physical-core fallback.

The failed XJTU staging `.xjtu-sy-generation-7x6h7sqm` was preserved exactly
in place and never used as source of truth. No real lab run, data extraction,
download, cleanup, merge, push, deploy, production ML, operational artifact,
Plan05, or script change was made.

## Residual concerns

- Source terms remain as observed at access time; the XJTU author page still
  does not expose an unambiguous data license.
- The CLI dry-run uses the historical status name
  `not_run_external_data_gate`; versioned artifacts use the more precise
  `not_run_semantic_gate` without changing production code in this task.
- A future supervised comparison is scientifically blocked until authoritative
  semantics and a prepared-generation loader are reviewed.
