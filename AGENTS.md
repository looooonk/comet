# Agent instructions

## Before changing experiments

Read [README.md](README.md), [the research contract](documents/research-direction.md)
and sections 5-8 of [the proposal](documents/proposal.pdf). The selected
Qwen3.5-9B hybrid backend and qualified alternative GPUs supersede the proposal's
original model, engine and hardware assumptions. Other architectures remain
unsupported; do not weaken the model/backend guards or resume legacy pilots.

Inspect the implementation, [workflow](documents/experiments.md),
[validation guide](documents/validation/README.md) and applicable
[evidence](documents/records/README.md). Recorded qualification applies only to
its source, runtime, device, cap and workload. Passing fixtures alone does not
establish live integration or research results.

Implement the agreed study before expanding it. Changes to models, benchmarks,
engines, methods, metrics or budget semantics require an explicit research
decision, recorded with rationale and affected comparisons. Routine implementation
choices do not. Do not change active or frozen configurations; changed settings
require a new version.

## Experimental invariants

- Use one configuration-driven pipeline for full KV, StreamingLLM, R-KV and
  AgentKV. Attempts are sequential, batch size one. Keep device model/count,
  runtime, precision, tasks, prompts, sampling, paired seeds and caps matched.
- Retention is the fraction of full-cache attention KV at the same raw-token
  step. Preserve the documented rounding and mandatory-entry floors. Report
  realized KV and uncompressed recurrent state separately from total VRAM.
- Keep the full raw transcript independently of compressed model state. Preserve
  every state type across turns and checkpoints; never silently re-prefill.
- Recovery re-prefills the full transcript and reapplies retention at most once
  per attempt. It never replays tools, rolls back the environment, restarts a
  task, summarizes or truncates history. Log inputs, decisions, cost and refusals.
- Enforce the same peak total-VRAM cap, including transient rebuild allocations.
  Refuse recovery that cannot fit; do not change precision or temporarily bypass
  the cap. Occupied KV and total GPU memory are different metrics.
- All attempts within a task/condition/seed share one wall-clock budget. Charge
  resets, tools, checkpoints, rebuilds, saving and cleanup. Exclude model loading
  and offline scoring consistently. An explicitly configured isolated train
  environment initialization/close may run once per launch outside task timing;
  record it separately, without model observations or tool calls.
- Checkpoint diagnostics branch from identical saved agent, environment, model
  and RNG state, then evolve independently. Charge preparation to each branch.
  Final evaluation always starts every attempt from the initial task state.
- Keep evaluation offline. Evaluator feedback cannot guide actions, triggers,
  attempt ranking or early stopping. Timeouts, OOM, interruptions and infeasibility
  remain in comparisons; never grant replacement budgets or free retries.
- Report oracle success within budget as a perfect-selection upper bound, plus
  first-attempt success, attempt counts, latency, throughput, estimated FLOPs,
  memory and recovery costs. Bootstrap tasks with their paired conditions and
  attempts; attempts are not independent tasks.
- Select tasks, operating regimes, finer retention/runtime grids and triggers
  on train/dev, confirm on separate dev coverage, then freeze before test.
  Preserve all declared points and failures, including flat curves. Do not select
  favorable test outcomes or imply unmeasured points are evidence.

## Implementation

| Location | Purpose |
| --- | --- |
| `src/comet/` | Shared execution, engines, scoring and analysis |
| `configs/` | Versioned studies, reusable bases and regression inputs |
| `scripts/`, `infra/` | Thin launchers, managed runtime and deployment setup |
| `tests/` | State, recovery, budget and evaluation checks |
| `documents/` | Shared decisions and operating guides |
| `documents/records/` | Compact results, validation evidence and selected figures |
| `experiments/` | Human-readable study ledger, periodically synchronized with repository evidence |

Inspect callers before changing shared interfaces. Update affected consumers
and documentation together; preserve configuration hashes, checkpoint formats
and result schemas unless the task explicitly changes them. Preserve others'
uncommitted work. Keep one shared runner and analysis path, with execution,
scoring and analysis separately callable. Avoid unrelated dependencies or a
framework when a small explicit interface suffices.

Use clear, succinct code. Expand dense expressions when that improves readability.
Comments should explain non-obvious reasoning or experimental constraints, use
only ASCII, and avoid delimiter lines and narration of obvious operations.

Keep the README short and human-oriented. General guides must be independent
of accounts, workspaces and run history. Put dated evidence in records, using
portable artifact IDs and hashes rather than private access/storage paths.
Delete obsolete plans and duplicate exports; Git preserves tracked history.
Keep unique completed run data outside tracked source. Do not retain temporary
logs, copied runtimes or generated archives just to document their existence.

## Setup, validation and handoff

Use `scripts/setup_runtime.sh` and `scripts/run_checks.sh`. Before direct runtime
commands, source `scripts/activate_runtime.sh` with the matching profile. Never
synchronize a GPU environment with `uv run`. Keep a separate owned environment
per checkout/profile, reuse persistent caches, and preserve pinned dependencies
and local engine patches. Slurm and GCP share the experiment launcher.

Before launches, qualify the intended device/cap and audit storage. Keep jobs
bounded; use small fixtures and train/dev smoke runs before sweeps. The cloud
ceiling and unreconciled allowances are in the [cloud ledger](documents/records/qwen9b/cloud-ledger.json).
Do not treat scheduler limits or GPU capacity as experimental budgets.

For pipeline changes, run the applicable checks for eviction/counts, persistent
state and checkpoint replay, fresh resets, one-time recovery without tool effects,
shared budget/resume accounting, transient memory caps and offline evaluation.
Use fresh evidence directories. Report which checks ran and which require
unavailable GPU or AppWorld infrastructure. Documentation-only changes do not
need behavioral tests.

Preserve each run's source and local changes, dependency/model/tokenizer revisions,
hardware, resolved configuration, task/split/seed/attempt/condition identifiers,
raw transcripts, actions/observations, needed checkpoints, evaluator-compatible
outcomes, timings, memory and failures. Resume only compatible runs, preserving
consumed budget and completed work. Keep different runs and stages separate.

Handoffs should state the change, affected interface/experiment, validation and
remaining limitations. Never claim success without saved results. Human
contributors review generated code and behavior; preserve authors' meaning in
research prose and distinguish observations from hypotheses.
