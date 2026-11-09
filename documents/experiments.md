# Experiment workflow

COMET uses the same runner for full KV, StreamingLLM, R-KV and AgentKV. The
[current research direction](research-direction.md) supersedes the original
model assumptions. The sample configurations are explicitly provisional train/dev
settings; they are runnable examples, not measured or
frozen research choices.

The [experiment resolution guide](experimental-resolution.md) describes
authorized supplemental retention, runtime-budget and trigger sweeps. Keep the
required core comparisons and declare each added grid before execution.

## Start small

The commands below describe the existing pipeline using a legacy schema example.
They are not instructions to restart canceled pilots. New Qwen support and its
experiment configuration must first be implemented and validated.

Follow [setup.md](setup.md) to install the pinned engine and AppWorld data, then:

```sh
source "$COMET_REPO/scripts/activate_runtime.sh" gpu
export COMET_CONFIG="$COMET_REPO/configs/examples/pilot-smoke.json"
export COMET_RUN="$COMET_STORAGE/runs/pilot-smoke-unique-id"
export COMET_MODEL=/path/to/pinned/model/snapshot
comet validate "$COMET_CONFIG"
bash "$COMET_REPO/scripts/run_experiment.sh"
comet evaluate "$COMET_RUN"
comet analyze "$COMET_RUN" --output "$COMET_RUN/analysis.json"
```

Run these commands inside an allocated GPU node. For a qualified research GPU, set `engine.device_name` to its exact reported
model name. Legacy configs without that field require A100 80GB. For unqualified
hardware checks, export `COMET_INTEGRATION_SMOKE=1`; those results remain separate
and cannot qualify a final experiment for freezing. Both Slurm and GCP wrappers
call the same launcher and managed runtime checks. Model loading is excluded from
the task budget. A deterministic synthetic warmup of all methods also runs as
model initialization, with its shapes and elapsed time recorded in the manifest;
later shape-dependent compilation remains charged. Attempts, resets, tools,
checkpoint work and recovery are charged.

New versioned configs may set `environment_warmup` to an explicit training
`task_id` and `seed`. Once per execution launch, the runner initializes and closes
that isolated environment without executing tools, presenting a prompt to the
model or loading evaluator feedback. This user-approved process setup is outside
task budgets and recorded in `launches[].environment_initialization`, including
failures and elapsed time. Every experimental reset, tool, checkpoint, rebuild
and cleanup remains charged. Resume records another setup without granting extra
task time or attempts; an already completed run does not repeat it. Omission
preserves historical behavior and config hashes. Analysis reports setup separately,
without amortizing it into task latency. The new path has CPU regression coverage;
its live AppWorld isolation check is still required before experimental use.

Evaluation is a separate command and is never called by execution.

For short allocations, `comet run ... --max-cells N` stops cleanly after at most
N newly terminal cells in the original condition/task/seed order. The shared
launcher exposes the same operational option as `COMET_MAX_CELLS`:

```sh
COMET_MAX_CELLS=2 bash "$COMET_REPO/scripts/run_experiment.sh"
COMET_RESUME=1 COMET_MAX_CELLS=2 bash "$COMET_REPO/scripts/run_experiment.sh"
```

Resume the identical source, runtime, configuration and output directory. The
option does not change the research configuration, seeds, attempts or cell
budgets; completed cells are skipped and interrupted cells retain their consumed
budget. It never stops within a cell or consults success. Allow enough scheduler
time for complete cell budgets plus model loading and shutdown. Clean launch records
include `max_cells`, `completed_cells`, `finished_at_unix` and `stop_reason`
(`max_cells` or `all_cells_completed`). Counts are persisted at clean stops and
caught exceptions; after an abrupt process kill, cell journals remain authoritative.
Checkpoint diagnostics prepare their declared source checkpoints before the
first branch segment. Later segments reuse those saved sources, including failed
preparations, and each branch retains the original preparation charge. The cell
limit counts continuations, not checkpoint preparation; reserve enough time for
all source preparations on the first launch. Copy the entire run directory when
moving a segmented run between otherwise identical workers.
A clean limited launch exits successfully
while its manifest remains `running`; score only after all cells finish and the
manifest becomes `completed`. Omitting the option retains the complete-run
behavior.

The retained schema examples are `configs/examples/pilot-smoke.json` (full KV
and three eviction methods) and `configs/examples/checkpoint-diagnostic.json`
(full KV and three recovery policies for AgentKV at 50%). They illustrate the
legacy configuration format; they are not queued runs or selected settings for
the new models. Obsolete full matrices and model-specific pilots are in Git
history. See [configuration guidance](../configs/README.md).

After analysis, select a separately managed CPU environment with the plotting
extra installed, then use the shared plotting command:

```sh
source "$COMET_REPO/scripts/activate_runtime.sh" cpu
comet plot runs/pilot/analysis.json \
  --output runs/pilot/figures/retention.svg \
  --title "AppWorld retention pilot"
```

This plots a full control and one eviction method at distinct retention levels,
with equal attempt limits and no recovery. The horizontal axis is
`100 * (1 - retention)`. Accuracy uses a conservative bounded-mean interval;
latency and mean per-cell peak KV use task-bootstrap intervals. The shared
analysis also records task-level standard errors and paired differences.
Intervals are pointwise, not simultaneous guarantees. Lines connect measured
points without imposing a monotone or smooth fit. See [evaluation.md](evaluation.md)
for definitions and coverage rules. Keep figures with their analysis, source
configuration, hardware description, and limitations in `records/`.

For a multi-method aggressivity figure, use `comet plot-aggressivity ANALYSIS
--output FIGURE.svg`. It uses percentage removed on the horizontal axis and
separates single-attempt success from oracle best-of-N, with a column for each
measured recovery policy. Compressed conditions must share one attempt ceiling;
the matching full-cache control is shown at zero removal. Only measured points
are connected. Output extensions select PNG, SVG or PDF.
`comet plot-resources ANALYSIS --policy never --output COSTS.svg` supplies the
corresponding latency, attempts, memory, throughput, estimated FLOPs, compaction
and recovery panels. Repeat with `fixed` or `dynamic` for those measured policies.

Configurations are JSON. `extends` resolves relative to the child file; top-level
objects merge one level and lists replace in full. The run records the fully
resolved configuration and its SHA-256 digest, so later edits to a parent file
cannot change recorded results. `comet matrix CONFIG` prints all 29 conditions.

## Observables and decisions

Context length is the count of full raw token IDs already generated/prefilled
plus the next pending observation suffix. It is independent of physical KV
length. Counts accumulate from the beginning of the attempt, including diagnostic
prefixes. A tool call is one Python execution submitted to AppWorld; a code block
may invoke several app APIs. Invalid action formatting does not increment it.

The runner checks recovery immediately before each model generation. `fixed`
uses `tool_calls >= fixed_tool_calls`. `dynamic` combines the configured context
and tool thresholds with the explicit `and` or `or` rule. `never` disables
recovery. Every decision records its inputs and reason; admission failures retain
the original cache. One admitted rebuild is allowed per attempt. Recovery
re-prefills the full accumulated raw transcript including the pending tool
observation, then reapplies retention. The next token is sampled from the saved
prefill logits; the observation is not appended twice. No past tool action is
executed again. [engine.md](engine.md) defines KV rounding and memory
accounting.

The raw token stream is append-only across tool turns. Qwen chat role delimiters
and `<tool_response>` markers preserve phase information for AgentKV. We never
re-tokenize the entire conversation to silently reconstruct an evicted cache.
Reaching the configured full-transcript limit ends the attempt with
`context_limit`; there is no truncation or automatic recovery.

## Budget, isolation and interruption

A cell is one task, condition and replicate seed. All its attempts share one
monotonic wall-clock budget. The attempt seed is the first 32 bits of SHA-256 of
the JSON pair `[replicate_seed, attempt_index]`, paired across conditions. N is
an upper limit. Ordinary supervisor completion ends an attempt, but execution
continues with further attempts while budget and N permit, regardless of score.

AppWorld freezes Python clocks to simulate task time. COMET uses the operating
system's monotonic clock directly for real execution deadlines and timings.
Model operations check deadlines, and the main process also installs a wall timer
around bounded work. GPU kernels already in flight may finish after a deadline;
their elapsed time is recorded and the attempt is a failure. Outcome saving and
cleanup consume time. Artifact bookkeeping overhead is included in cell latency.

Each attempt starts a fresh AppWorld environment and clears the model session.
Run directories are locked against concurrent writers. Atomic manifests and
per-turn trajectories preserve completed work. Resume with the same command and
`--resume`; it rejects incompatible resolved settings or source changes and
skips completed cells. Installed package versions and stable native runtime/GPU
metadata must also match; each launch retains its own initialization record. If a
process died inside an attempt, its remaining cell
budget is conservatively consumed and the attempt becomes `interrupted`. This
avoids granting free compute when an operation has no reliable end timestamp.
Resume continues other unfinished cells; it does not replay completed attempts.
The interrupted failure is finalized in both the cell and attempt records;
`reserved_budget_seconds` distinguishes the unobserved reservation from measured
component timings. See [resume-validation.md](resume-validation.md) for the
opt-in real-process interruption check.

If every unfinished cell is already inflight, has exhausted its budget, or has
used its attempt limit, run `comet finalize RUN_DIRECTORY` in the original
checkout and managed environment. This uses the same source, configuration and
installed-package compatibility checks as resume, but never loads a GPU model or
initializes AppWorld. It validates every cell before changing any metadata and
refuses if any inference remains eligible. Completed artifacts are preserved;
interrupted cells consume their remaining reserved budget. Ordinary GPU resumes
still validate the original GPU/runtime identity. Finalization does not make
historical runs compatible with a changed checkout or environment.

## Checkpoint diagnostic

Use the diagnostic config with the same `run`, `evaluate`, and `analyze` commands.
The runner prepares one full-cache source checkpoint per task/seed, saving the
raw transcript, pending observation, engine KV/metadata/RNG and AppWorld state.
Each condition restores that same source, applies its own retention policy, and
continues independently. Prefix preparation time is charged identically to every
branch, as are its own reset and restore costs. Prefix inference and memory costs
are retained in each branch's metrics. Diagnostic cells contain one continuation.
The source must remain incomplete at the declared tool-count boundary. A source
that completes before or exactly at that boundary is ineligible: its trajectory
and preparation costs remain recorded, and every dependent branch is infeasible
without executing another action. The eligibility check consumes preparation
time. It uses the ordinary task-completion observation, not evaluator feedback.

AppWorld's database checkpoint alone is insufficient: Python variables and RNG
also matter. The adapter preserves supported data-valued execution namespaces and
rejects functions, generators, API handle aliases and other unsupported live
objects. Such a checkpoint is reported as infeasible, never silently replayed or
substituted. See [evaluation.md](evaluation.md). Failed source preparation remains
a failed condition in every comparison. Final evaluation always starts fresh.
Known preparation costs remain in branch metrics even when preparation or restore
fails. The attempt's `checkpoint_preparation` identifies the source and its tool
and rebuild counts separately; an unavailable source does not imply that a branch
executed those actions. Preparation time is charged once per branch.
This charge precedes branch reset, so a reset timeout retains the source costs
and an unavailable source does not incur a new reset or continuation.
Preparation cleanup includes synchronization, environment close, and the final
memory probe. Its time is charged; errors or a budget overrun invalidate an
otherwise completed source while preserving known costs and any primary failure.

## Baseline behavior diagnostic

Select the new model and validate its integration before declaring a full-cache
train/dev pilot. Inspect ordinary trajectories for API, authentication, task
coverage and premature-completion errors. Use a predeclared representative
sample for capability estimates; a targeted regression set is a separate test.
See the [current research direction](research-direction.md).

The optional [agent protocol](agent-protocol.md) changes feedback and action
validation. If enabled, evaluate it as an explicit paired intervention and freeze
the same setting across retention conditions. Historical prompt/guard pilots are
not pending work and must not restart automatically.

## Freeze and evaluate

Tune only on train/dev and record pilot measurements. Prepare a new JSON config
with `stage: "final"`, an explicit test split and task subset, and the agreed
sampling, seeds, budgets, thresholds, context length and N. Then:

```sh
comet freeze configs/final-candidate.json --output configs/final-v1.json \
  --pilot-run runs/measured-qualified-pilot
comet run configs/final-v1.json --output runs/final-v1 \
  --model-path "$COMET_MODEL_PATH" --appworld-root "$APPWORLD_ROOT"
```

Freeze requires completed, non-smoke train/dev pilot evidence on the selected device with matching
numerical settings and a completed attempt. It records the settings and evidence
digests. The command does not make scientific judgments about task sample size or
trigger quality: contributors must review those before the test run. Editing a
frozen setting invalidates its digest and requires a new experiment version.

## Artifact contract

`manifest.json` records the run, stage, source state, dependency pins, resolved
configuration and every expected cell. Each `cells/<id>/cell.json` records the
shared budget and ordered attempts. Attempt directories contain raw token IDs,
actions/observations, recovery decisions, timing/memory metrics and saved
evaluator-compatible environments. Diagnostic sources live under `checkpoints/`.
`scores.json` and `analysis.json` are separate post-hoc artifacts.

Scoring records its own source and installed-package provenance. Resuming scoring
requires that same implementation. Analysis refuses to pool different source,
runtime, hardware or scoring versions even when their experiment settings match.
Use the recorded checkout and environment when continuing an older run.

Keep complete run directories outside tracked source. Copy them intact when
moving between machines; AppWorld scoring also needs its pinned data root. Small
validation summaries in [records/](records/README.md) identify hardware, jobs,
and portable artifact filenames and hashes. Keep general documentation independent
of personal locations and run histories. Do not treat fixture tests or unqualified
integration results as research measurements.
