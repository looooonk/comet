# Sampling repair validation and relaunched 8B diagnostic

The corrected runtime passed **130 tests** on pinned Qwen3-8B BF16 and an
NVIDIA L40S. The paired twelve-rollout diagnostic then started on the same node
at 12:06:36 Eastern on November 8, 2026, as Slurm job `13836336`.
The [evidence JSON](sampling-repair-2026-11-08-validation.json) records validation,
source and artifact hashes, storage measurements, and the launch snapshot.
Task scores for this corrected runtime remain pending.

The [completed-results follow-up](sampling-repair-2026-11-08-results.md) supersedes
the active-run snapshot below, including a later preemption and offline scoring.

## Overnight failure and recovery

The [initial submission](sampling-repair-2026-11-07.md) did not reach GPU testing.
Its package-isolation job `13834449` exceeded its thirty-minute reservation at
21:26 Eastern on November 7. The scheduler consequently cancelled GPU checks
`13834428`, paired execution `13834429`, scorer `13834430`, and storage audit
`13834455`. No experimental attempt ran in that chain, so the replacement does
not grant failed attempts extra time or replacements.

The resumed isolation procedure inventories files with fewer filesystem metadata
queries, can resume an interrupted copy, reports progress, and has a two-hour
reservation. Job `13836334` finished in 26 seconds: all 40,232 regular files were
already independent, with zero remaining hard links or partial-copy files. It
copied zero additional bytes and verified the original FlashInfer source hash.
The original run and its scorer had completed naturally the previous evening;
[their separate results](baseline-qwen8b-2026-11-08-completion.md) are preserved.

## Live validation

Job `13836335` finished successfully in 5m25s using clean source
`396e7743bab1062d523dbf5e36b78758942dd806`. All 130 selected tests passed; one
explicitly opt-in process-kill/resume test was skipped. The suite includes:

- All four sampler paths: the attempt-seeded CUDA generator advances; successive
  samples and different seeds differ; restored state exactly replays samples.
  Greedy decoding leaves RNG state unchanged.
- Actual-model sampled checkpoint replay, full-cache cached-versus-fresh output,
  persistent compressed KV, and one-time recovery for all three eviction methods.
- Rejected recovery that preserves state and continuation RNG, and a live allocator
  cap that rejects allocation while physical device memory remains available.
- Full-cache and AgentKV-80% continuation near the 32,768-token context limit,
  under the configured 40 GiB cap.
- Live AppWorld reset/checkpoint/evaluation, authentication and pagination, plus
  shared runner, budget, agent-error handling, numerical and analysis checks.

These are alternative-hardware integration results. They do not qualify the
required A100 research experiment or establish task-solving improvement.

## Active paired run

Job `13836336` runs the unchanged declared configurations sequentially on one
L40S allocation. It uses the same clean code revision as validation. The first
run's manifest records `torch_cuda_default_generator_v1`, and its first task/seed
cell has entered execution. The bounded-agent arm follows all six control cells;
o evaluator result can affect that execution. Job `13836337` scores and audits
both arms only after the paired execution finishes.

Artifact identifiers:

- `sampling-control-qwen8b-20261107-13836336`, run ID
  `02878799-362e-41d1-830f-c68ee409f9ec`.
- `agent-guard-qwen8b-20261107-13836336`, not yet started at this snapshot.

The date embedded in these identifiers refers to the original diagnostic plan;
the replacement job actually started on November 8. Configurations, tasks, seeds,
prompts, budgets and retention policies were not retuned using the original
run's newly collected scores. The total task-budget ceiling remains two hours,
plus loading, bookkeeping and offline scoring.

## Storage

CPU audit job `13836339` measured the complete project workspace at **73.50 GiB**,
including **35.58 GiB for COMET**, and home at **2.06 GiB / 18,913 inodes**.
Project storage contained 241,622 inodes. These are whole-tree measurements that
avoid double-counting hard-linked package files across directories.

The extra independently writable runtime accounts for approximately 8.6 GiB of
additional storage. No model snapshot was duplicated, and no original runtime,
source, model, or result was deleted. The standalone quota command returned no
entries after correcting its argument syntax, so these measurements do not
establish an individual project quota. Keep the original and corrected results
separate, and audit runtime retention again after the active comparison finishes.
