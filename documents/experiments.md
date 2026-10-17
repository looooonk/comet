# Experiment workflow

COMET uses the same runner for full KV, StreamingLLM, R-KV and AgentKV. The
proposal remains the research contract. The sample configurations are explicitly
provisional train/dev settings; they are runnable examples, not measured or
frozen research choices.

## Start small

Follow [setup.md](setup.md) to install the pinned engine and AppWorld data, then:

```sh
uv run comet validate configs/pilot-smoke.json
comet run configs/pilot-smoke.json --output runs/pilot-smoke-001 \
  --model-path "$COMET_MODEL_PATH" --appworld-root "$APPWORLD_ROOT"
comet evaluate runs/pilot-smoke-001
comet analyze runs/pilot-smoke-001 --output runs/pilot-smoke-001/analysis.json
```

Run the last three commands from the GPU environment. On an alternative GPU,
add `--integration-smoke` to `run`; those results remain visibly separate and
cannot qualify a final experiment for freezing. Model loading is excluded from
the task budget. A deterministic synthetic warmup of all methods also runs as
model initialization, with its shapes and elapsed time recorded in the manifest;
later shape-dependent compilation remains charged. Attempts, resets, tools,
checkpoint work and recovery are charged.
Evaluation is a separate command and is never called by execution.

The included configurations are:

| Configuration | Purpose |
| --- | --- |
| `pilot-smoke.json` | One real dev task, one seed, full KV and all three methods at 50%; at most eight minutes of task budgets |
| `pilot-matrix.json` | Q1/Q2 matrix: two full controls plus 27 compressed conditions, two dev tasks and two seeds |
| `checkpoint-diagnostic.json` | One full control plus 27 compressed continuations from a common pre-compression checkpoint |

The full pilot matrix has 116 cells at a provisional ten-minute shared budget:
19.3 GPU-hours at the time limit, excluding model loading. Inspect smoke costs
before scheduling it. Nothing automatically launches this sweep. Task IDs are
verified against the requested AppWorld split before loading the model.

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

## Checkpoint diagnostic

Use the diagnostic config with the same `run`, `evaluate`, and `analyze` commands.
The runner prepares one full-cache source checkpoint per task/seed, saving the
raw transcript, pending observation, engine KV/metadata/RNG and AppWorld state.
Each condition restores that same source, applies its own retention policy, and
continues independently. Prefix preparation time is charged identically to every
branch, as are its own reset and restore costs. Prefix inference and memory costs
are retained in each branch's metrics. Diagnostic cells contain one continuation.

AppWorld's database checkpoint alone is insufficient: Python variables and RNG
also matter. The adapter preserves supported data-valued execution namespaces and
rejects functions, generators, API handle aliases and other unsupported live
objects. Such a checkpoint is reported as infeasible, never silently replayed or
substituted. See [evaluation.md](evaluation.md). Failed source preparation remains
a failed condition in every comparison. Final evaluation always starts fresh.

## Freeze and evaluate

Tune only on train/dev and record pilot measurements. Prepare a new JSON config
with `stage: "final"`, an explicit test split and task subset, and the agreed
sampling, seeds, budgets, thresholds, context length and N. Then:

```sh
comet freeze configs/final-candidate.json --output configs/final-v1.json \
  --pilot-run runs/measured-a100-pilot
comet run configs/final-v1.json --output runs/final-v1 \
  --model-path "$COMET_MODEL_PATH" --appworld-root "$APPWORLD_ROOT"
```

Freeze requires completed, non-smoke train/dev pilot evidence with matching
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
committed validation summaries identify the original host, jobs and artifact
paths. Do not treat fixture tests or non-A100 integration results as research
measurements.
