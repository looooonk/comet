# Fifty-family Blackwell study

On November 9, 2026, the user authorized expanding the compression/success curve
to 50 tasks, using available Insomnia GPUs, and committing/submitting the work
on `dev/yenna`. This version increases task coverage of the supplemental fine
grid. It does not replace the earlier recovery study or pool its observations.

## Frozen comparison

The [parent configuration](../../../configs/qwen9b/blackwell/test50-v1.json)
contains 50 `test_normal` tasks, seed 17, and 26 conditions: full-cache N=1 and
N=2 controls, plus StreamingLLM, R-KV and AgentKV at 25%, 30%, 40%, 50%, 60%,
70%, 80% and 90% retention without recovery. All 1,300 task/condition cells have
120 seconds shared across at most two sequential attempts. First-attempt and
oracle success are reported separately; oracle selection remains an upper bound.

Qwen3.5-9B, its pinned hybrid backend, BF16, the v4 prompt, sampling, 16,384-token
context and 24 GiB total-VRAM cap match the qualified Blackwell fine grid. Each
worker receives one RTX PRO 6000 Blackwell Server Edition GPU, four host CPUs,
24 GiB host RAM and four CPU threads. Device capacity is not the experimental
memory cap. Different sources, hosts and task distributions preclude treating
historical timings or outcomes as a controlled comparison with this cohort.

The parent was frozen from the completed Blackwell train fine grid and separate
dev confirmation, before any execution on the new task subset. Its pilot records
preserve the original manifests and configuration digests. Fresh live checks
and a predeclared dev smoke must also succeed on each allocated worker before
that worker executes test cells. Smoke success rate does not select or retune
the frozen test matrix.

## Task selection

The pinned split contains 168 tasks in 56 families. Exclude `042a9fc` and
`59fae45`, whose outcomes/trajectories were examined in the previous L4 test.
Using namespace `comet-test50-v1:20261109`, rank the remaining family IDs by
SHA-256 of `namespace + ":family:" + family` and take the first 50. Within each
family, choose the task minimizing SHA-256 of `namespace + ":variant:" + task_id`.
Selection reads split identifiers only, without instructions, outcomes or
difficulty metadata. There are 18 variant-1, 20 variant-2 and 12 variant-3 tasks.
The [selection record](test50-selection.json) preserves the input split hash and
complete task list. One task per family avoids counting related variants as
independent families. Bootstrap the 50 paired tasks with their conditions and
attempts; repeated smoke tasks and retries are not additional samples.

## Execution and validation

The [eight condition partitions](../../../configs/qwen9b/blackwell/test50-v1-parts/index.json)
cover every parent cell exactly once, retaining all 50 tasks and the shared seed.
Two partitions contain 200 cells each; six contain 150. Their maximum nominal
cell time is respectively 6h40m and 5h, plus setup, validation and saving.
Each Slurm worker has an 8h30m allocation limit and automatic requeue disabled.
Up to eight independent one-GPU workers may run concurrently.

Each worker checks all eight retention fractions, persistent state, compressed
and recovered replay, numerical reference agreement, 16K capacity/recovery,
AppWorld isolation/tool effects and process-interruption accounting at the
24 GiB cap. A four-condition, one-task dev smoke uses the frozen numerical
settings. The shared runtime and model caches are reused; job-local staging
keeps large imports and model loading off the shared filesystem during execution.

An independent CPU job waits for all workers to exit successfully, then scores
their saved outcomes offline, verifies exact frozen-parent coverage, and creates
the analysis and aggressivity/resource plots. Incomplete or failed jobs block
this step. They receive no replacement task budgets; any subsequent resume must
preserve the original source, runtime, configurations and consumed work.

Local managed CPU checks at execution source `068f9b7` passed 349 tests, with two
optional Torch modules skipped and 17 live tests deselected. This establishes
CPU regression coverage only; submitted live checks are separate evidence.
Job IDs, actual starts and completion estimates belong in the submission record.
