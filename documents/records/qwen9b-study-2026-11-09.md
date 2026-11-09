# Qwen3.5-9B study: declared samples and execution

This is the new hybrid study, separate from legacy results. The user authorized
autonomous execution, smaller models first, queue-aware hardware selection and
reasonable difficulty adjustments. See [the backend decision](../hybrid-backend.md).

## Outcome-independent sampling

For each split, group IDs by the part before the final underscore. Rank families
by SHA-256 of `comet-qwen9b-v1:` followed by the family ID, then select variant
`_1`. Hashing defines a reproducible ordering; it is not a numerical acceptance
test. Do not inspect test outcomes to select tasks.

- Initial train capability/cost pilot: `34d9492_1`, `76f2c72_1`, `771d8fc_1`,
  `692c77d_1`. Covers file organization, file-based arithmetic, phone deletion,
  and Spotify updates.
- Reserved further train coverage: `e3d6c94_1`, `29caf6f_1`, `aa8502b_1`,
  `22cc237_1`.
- Dev tuning order: `b119b1f_1`, `fac291d_1`, `4fab96f_1`, `0d8a4ee_1`.
- Separate dev confirmation order: `4ec8de5_1`, `396c5a2_1`, `37a8675_1`,
  `d4e9306_1`.
- Reserved test order: `59fae45_1`, `042a9fc_1`, `83a7951_1`, `325d6ec_1`,
  `634f342_1`, `425a494_1`, `13547f5_1`, `09b0ee6_1`. Only split IDs were
  inspected when defining this order. Final count and settings remain unfrozen.

Legacy runs exposed train/dev tasks and informed general authentication and
pagination guidance. These are not pristine development tasks. No new-model
test outcome has been inspected. The small sample and one initial replicate
seed are feasibility choices, not evidence of broad benchmark performance.

## First configuration

`configs/qwen9b/train-baseline-v1.json` declares 300 seconds per task, one
attempt, seed 17, 8,192 raw tokens, 1,024 generated tokens per turn, BF16 and
a 40 GiB total-VRAM cap on one NVIDIA RTX A6000. Nonthinking sampling uses
temperature 0.7/top-p 0.8, with top-k disabled and no presence penalty. The
prompt gives general API/authentication/pagination guidance, not task answers.

The optional one-time train environment initialization must pass its live
isolation check before this configuration is executed. Every experimental
reset, tool call, checkpoint, recovery and cleanup remains charged.

## Evidence so far

- Runtime and selector packaging committed at `e3e9fcb`; local CPU checks:
  331 passed, one optional numerical module skipped, 15 live checks deselected.
- Hybrid implementation committed at `ee27663`; local CPU checks:
  333 passed, one numerical module skipped, 16 live checks deselected.
- Fresh managed Linux hybrid environment installed successfully. The official
  9B assets were downloaded at the pinned revision. An initial CLI pattern
  invocation fetched only part of the metadata; the shared downloader was
  corrected and the snapshot completed before GPU validation.
- An A6000 validation allocation started after correcting its scheduler QoS and
  fitting a 25-minute backfill window. GPU and AppWorld results remain pending.
- GCP quota/authentication check passed for one Spot L4. No paid job submitted.
- The first live AppWorld checks found that a newly resolved FastAPI version
  removed the `embed` argument used by pinned AppWorld. The hybrid input now
  constrains AppWorld dependencies to the existing AppWorld lock, retaining
  its validated FastAPI/Starlette versions. No task outcome was collected under
  the incompatible environment. The repair requires setup and live checks again.

Large outputs remain outside tracked source. Add measured results and portable
artifact identities here only after inspection.

The second live check (`hybrid-second`, source `d8b9765`) passed all six
AppWorld integration/isolation tests. The 9B weights loaded from local scratch
in about two seconds, after substantial cold shared-library import delays.
Synthetic warmup ran all four methods. The subsequent reference prompt exposed
a Transformers 5.22 API change: chat templating returns a mapping by default.
The runner and live checks now explicitly request token IDs with
`return_dict=False`. No task outcome was collected. Three additional launcher
fixture failures came from inherited local-staging settings and are repaired.
The run retained 329 passes, 18 skips and these four failures.

The local suite after staging/plot additions passed 336 tests, with one optional
numerical module skipped and 16 live checks deselected. A managed-runtime
archive now allows identical pinned packages to be staged on local scratch;
packing, activation and configuration validation were exercised locally.
