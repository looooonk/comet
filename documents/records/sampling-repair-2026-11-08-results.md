# Corrected-sampler paired diagnostic results

Both declared configurations are now terminal and separately scored: **0/6 task
successes for each**. The guard bounded several execution-error loops, but this
small diagnostic observed no task-solving gain. The [evidence](sampling-repair-2026-11-08-results.json)
contains all twelve outcomes, trajectory audit summaries, first-response hashes,
artifact hashes, and interruption-finalization evidence.

| Configuration | Normal completion, unsuccessful | Context limit | Error limit | Interrupted | Task successes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Corrected sampler, existing protocol | 1 | 5 | 0 | 0 | 0/6 |
| Corrected sampler, guarded protocol | 2 | 0 | 3 | 1 | 0/6 |

Both use clean source `396e7743bab1062d523dbf5e36b78758942dd806`, Qwen3-8B
BF16 and an NVIDIA L40S, with the [declared tasks, settings and budgets](sampling-repair-2026-11-07-plan.md).
The [GPU validation](sampling-repair-2026-11-08-validation.md) remains applicable.
The original 38-rollout experiment is separate and unchanged.

## What the test establishes

The real model's first responses differ between seeds 17 and 18 on all three
tasks. For each task and seed, that first response is identical across the two
protocol arms. Together with the live RNG checks, this supports the repaired
sampling path and initial pairing; seed variation alone does not imply correct
actions or task success.

The existing protocol still fills the context on five of six rollouts. Its saved
trajectories contain 665 response turns and 592 error turns. The guarded protocol
has 49 saved turns and 27 error turns, including the three-turn prefix of the
interrupted rollout. Three guarded attempts ended at exactly five consecutive
execution/action errors, as configured. These lower counts are affected by early
failure stops and one infrastructure interruption; they are not a success metric
or a clean estimate of performance improvement.

The three normally completed attempts across both arms all failed AppWorld's
evaluator. The next behavior investigation should inspect ordinary task coverage
and completion actions in those traces, alongside remaining API/format errors.
Do not expand a retention sweep or declare a stronger baseline from these results.
The subset is targeted dev data, and the interrupted cell further limits the
paired comparison. All failures remain in the denominator; there is no free
replacement rollout or post-hoc favorable task removal.

## Preemption and finalization

Slurm preempted job `13836336` on the L40S node at 13:01:24 Eastern, after all six
control cells and five guarded cells finished. The sixth guarded cell,
`57c3486_1`/seed 18, had saved three tool turns. Automatic requeue restarted the
batch script on another node at 13:07:52; the wrapper rejected its existing
control output directory and exited immediately. Its dependent scorer was
cancelled. The original scheduler stdout was truncated on restart, while saved
run manifests, trajectories, environment artifacts and launch metadata survived.

No inference remained eligible after interruption: the only nonterminal cell was
already inflight and therefore consumes its remaining budget under COMET's
existing interruption policy. A compatible GPU resume was initially queued, then
cancelled while still pending when its multi-hour wait proved unnecessary for
this metadata-only operation.

CPU job `13837310` checked the original source, installed packages and resolved
configuration using the runner's resume validation. A thin operational helper
then called the original `_run_cell` interruption path with no engine and marked
the manifest complete only after every cell was terminal. It asserted that exactly
one pending cell was inflight and that no engine, environment, or replacement
attempt could be created. This is not a validation of resumed model inference.

All 56 files belonging to the five completed guarded cells retained their hashes,
as did the interrupted trajectory. The interrupted attempt is recorded in both
cell and attempt artifacts, and its cell is charged 600 seconds. Its
`reserved_budget_seconds: 600` is conservative accounting, not measured latency;
unavailable inference timings and memory measurements were not invented.
The finalization helper and its audit reports are identified by hashes in the
evidence JSON. The completed control artifacts were not changed by finalization.

CPU scoring job `13837311` subsequently completed both evaluators, schema-2
trajectory audits and separate analyses at 14:35:06 Eastern. Scoring began only
after both execution manifests were terminal. No evaluator feedback was supplied
to execution or used to rerun attempts.

## Launcher correction

Commit `e90e503` makes all shared Slurm wrappers disable automatic requeue and
append logs. Preemption now requires an explicit compatible resume, preserving
failure logs and budget accounting. The setup guide explains how multi-config
jobs must resume existing runs before starting any uncreated output. Shell syntax
checks passed; the live finalization and scoring jobs also exercised those Slurm
flags. No model, package pin, prompt, budget, or research setting changed.

Artifacts remain `sampling-control-qwen8b-20261107-13836336` and
`agent-guard-qwen8b-20261107-13836336`. Guard run ID:
`73c57a98-0801-4f4c-aa80-19c2c6c188e6`.
The filenames retain the original plan's date; execution and scoring occurred
on November 8.
