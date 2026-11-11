# Fifty-family Blackwell study

On November 9, 2026, the user authorized expanding the compression/success curve
to 50 tasks, using available Insomnia GPUs, and committing/submitting the work
on `dev/yenna`. This version increases task coverage of the supplemental fine
grid. It does not replace the earlier recovery study or pool its observations.

All 1,300 evaluations and final scoring completed on November 10, 2026.
See the [final results and plots](test50-final.md); the launch and repair history
below records how that frozen study was completed.

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
preserve the original manifests and configuration digests. Live checks
and a predeclared dev smoke must succeed before test execution. Identical
workers may reuse this qualification after verifying the execution source,
managed runtime, GPU model and cap. Smoke success rate does not select or retune
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
The qualified launch requested 8h30m for 200-cell workers and 6h30m for 150-cell
workers, with automatic requeue disabled and up to eight independent one-GPU
workers running concurrently.

The live qualification checks all eight retention fractions, persistent state, compressed
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

## Original submission

The [submission record](test50-submission.json) identifies GPU array `13844484`
(eight one-GPU workers) and dependent offline scoring/plotting job `13844488`.
CPU setup/check job `13844476` completed successfully on Insomnia, repeating
the 349-pass CPU suite. The GPU requests were moved, while still unstarted, to
the previously used `short` partition and `free` QoS with an explicit `R6000`
constraint. These allocations can be preempted; interrupted cells retain their
failure and budget charges, and automatic requeue is disabled.

Execution source remains pinned to `068f9b7`; the frozen configurations are
committed in `f3b75b2` and staged separately without changing their resolved
digests. Do not update the remote execution checkout while any study job remains
queued or running. Each worker has its own live-check, dev-smoke and final-run
directories. Shared source, immutable runtime archive and model caches are reused.

At the original submission, the scheduler's matching-request forecasts were approximately
16:17 ET for one GPU and 16:28 ET for eight GPUs on November 9. The array itself
was still pending without committed start timestamps. The planning target for
completed plots was **00:30 ET on November 10**, conditional on roughly those
starts, passing validation and no preemption. This includes the longest 6h40m
nominal cell budget, 30 minutes of setup/qualification and 45 minutes of scoring
and plotting. Scheduler forecasts are not capacity reservations.

That launch failed during qualification, before any final-study cells started.
Its ETA is superseded. Four workers failed; the remaining workers and dependent
scorer were cancelled. The original validation artifacts are preserved.

## Validation repair and resubmission

The [repair record](test50-validation-repair.json) tracks the replacement launch
and its live qualification evidence. The cleanup test now observes its own scoring
namespace instead of comparing a shared directory that other workers can change.
Hybrid checks exit their CUDA-owning process before the CLI interruption/resume
test starts; the latter also explicitly rejects an infeasible first cell.

The repair changes validation orchestration only. The frozen parent, all eight
partitions, smoke and resume configurations are byte-identical to the original
submission. Local and Insomnia CPU checks pass 351 tests, with two optional Torch
modules skipped and 17 live tests deselected. Replacement GPU workers must
pass the live checks and dev smoke or verify reusable evidence for the identical
execution source, managed runtime, GPU model and cap before final execution.

Execution stayed pinned to `f2413b4`; subsequent changes affected validation tests
and reporting, not the model runner or experiment settings. Worker `13844702_2`
passed all 24 live checks and the four-condition dev smoke before its final
partition. The seven other partitions were submitted as array `13845293`,
reusing that completed qualification. Job `13845304` was the originally dependent
scorer; the final scorer was replaced as described below without changing task
budgets or the frozen comparison.

An intermediate launch at `1255369` was stopped before final execution after an
added assertion was found to index an optional field directly. At `f2413b4`,
four workers then hit the agent's ordinary four-action-failure stop during the
fresh attempt, just before the 120-second timeout. The validation test incorrectly
accepted timeout but rejected that legitimate agent outcome. The corrected test
accepts this specific protocol failure while preserving every reset, paired-state
and budget check; unexpected infrastructure errors still fail validation.

Review of the four saved runs confirmed preserved completed cells, unchanged
interrupted trajectories, all 120 seconds charged to the interruption, identical
initial actions and 3,434-token prefixes, and three distinct environments. Their
original failed reports and task outcomes remain intact. Reusing the successful
qualification avoids screening the study on incidental agent behavior or repeating
identical GPU checks. No final-task budget was replaced.

The 200-cell workers retain 8h30m allocations; the six 150-cell workers request
6h30m, allowing 90 minutes beyond their five-hour nominal cell budgets.

## Partial reporting and final completion

During execution, isolated partial reports included only conditions with all
50 tasks complete, retaining every execution failure. The last partial snapshot
covered 21 conditions; those superseded exports remain in Git history. No
partial result was used to change ongoing execution. Partition 02 saved every
cell but failed during CUDA shutdown; metadata-only finalization preserved its
results. Replacement scorer `13847761` correctly refused to score the full study
while five other partitions still had eligible inference after allocation expiry.

The [November 10 resume record](test50-resume-20261110.json) preserves the 1,246
terminal cells and submits compatible resumes only for partitions 01 and 04-07.
Array `13853125` started at 16:06:05 ET after capacity returned and finished by
16:29:59 ET. It settled five interrupted journals with their original budget
charges and executed the 49 unstarted cells. No completed task was rerun.

Final scorer `13853128` successfully finalized all eight partitions, scored all
1,300 evaluations, verified exact parent coverage and generated the final analysis
and plots by 16:59:29 ET. All 26 conditions now have 50 paired task outcomes.
The [final evidence](test50-final-summary.json) records completion, source hashes,
failure counts and validation. No GCP resources were launched, and the November 12
start forecast no longer applies.
