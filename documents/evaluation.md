# AppWorld execution, scoring, and analysis

COMET keeps execution, scoring, and analysis separately callable. The online adapter never calls the evaluator and loads each task with `load_ground_truth=False`. Completion means the agent called AppWorld's supervisor completion API; it does not imply task success. Scoring begins only after the execution manifest and every configured task/condition/replicate-seed cell are complete.

## Pinned environment

The adapter targets [AppWorld commit 42b5bcf](https://github.com/StonyBrookNLP/appworld/tree/42b5bcf3cd334fee33f0c37c02070a9f5807add5), package version `0.2.0.dev0`, and data version `0.2.0`. This is an implementation dependency choice, not a change to the benchmark. The installed distribution must record this exact Git revision in its direct installation metadata. See the shared setup instructions and dependency lock for the resolved transitive dependencies, LFS bundle hydration, and installed package constraints.

Verified upstream entry points at that revision are `AppWorld(..., load_ground_truth=False)`, `execute`, `task_completed`, `save`, `save_state(state_id=...)`, `load_state(state_id=...)`, `close`, and the separate `evaluate_task`. The adapter uses local execution with remote modes disabled. It leaves AppWorld's syntax and execution safety checks enabled. The shared runner enforces the wall-clock deadline; AppWorld's inner timeout is disabled so it cannot replace the runner's signal timer. Interaction and API-call ceilings are set to the platform integer maximum, leaving the configured context and shared wall-clock budget as the experiment limits.

AppWorld freezes the task's clock through Freezegun. COMET's elapsed-time measurements must use the real monotonic clock rather than task time. An outer deadline may be turned into an ordinary execution error by IPython; the runner also checks the budget on return and records the attempt as a timeout. The adapter restores AppWorld's process-wide execution patches even if execution raises.

The initial task context contains the instruction, public supervisor information, task date, app descriptions, and the `api_docs` and `supervisor` documentation. Other APIs are discoverable through the documented API interface. It contains no reference solution, required-action list, evaluator feedback, or private task data. The configurable system prompt is stored in the resolved run configuration. A model turn must contain exactly one nonempty fenced `python` or `py` block. One accepted block is one tool call, even when the block invokes several AppWorld APIs. Invalid formatting produces an observation without executing code.

## Attempt and checkpoint state

Every reset creates a new AppWorld instance and a unique output namespace. Final evaluation starts from the initial task state. An attempt's `environment/live.json` identifies AppWorld's automatically saved database and execution logs, including failed attempts that could not finish copying their outcome within the budget. Successfully saved outcomes include `environment/reference.json` and a copy of the AppWorld task output in `environment/task/`. This includes database changes relative to the benchmark base data and the code/data version markers required for offline evaluation.

Upstream `save_state` stores database state only. It does not save the interactive Python namespace, random state, counters, or logs. COMET checkpoints add these, then restore database state and execution values without re-executing historical tool actions. The checkpoint also preserves alias relationships between supported Python values, Python's global RNG, NumPy's global RNG when loaded, the environment interaction counters, and the request log and counter. The task clock is reinstated after upstream `load_state` clears it. The runner separately stores raw token IDs, KV state, sampling state, and recovery counters. Restoring the environment precedes restoring the engine RNG state.

Execution checkpoints currently support data-valued Python variables: builtin scalar/container values, common standard date/time and numeric values, regular expressions, and module aliases. User-defined functions and classes, generators, API-handle aliases, open resources, unusual container subclasses, and changed runtime bindings fail explicitly with `UnsupportedPath`. They are never silently dropped or reconstructed by replay. Such a diagnostic branch is reported as infeasible. This limitation does not prevent ordinary final-evaluation attempts from executing those constructs. Broader execution snapshots need a separate implementation and live validation before being claimed as supported.

Checkpoint execution files are trusted local pickle artifacts with identity and checksum checks. Do not load externally supplied checkpoints. A restore must match the task, seed, code revision, data version, and checkpoint schema. The parent checkpoint also validates engine and configuration compatibility.

## Offline evaluation

Run the shared CLI's `evaluate` command after execution. `evaluate_run` checks the manifest's exact Cartesian task/condition/seed set, every cell's identity and completion flag, ordered attempt indices, attempt limits, and terminal statuses before invoking any evaluator. It holds the run lock and writes `scores.json` separately from online artifacts. A scoring error raises instead of being silently converted into a failed benchmark task. Completed cell scores survive an interrupted scoring job; modified execution artifacts invalidate existing scores.

Only attempts with execution status `completed` are eligible for a successful AppWorld score. Timeouts, out-of-memory errors, context-limit terminations, interrupted attempts, infeasible attempts, and other execution errors remain failures. Zero-attempt cells remain in the denominator. Failure outcomes are not given free replacements. Each eligible saved outcome is copied into a separate scoring namespace, with AppWorld caches cleared before and after evaluation. The task score and report are saved without opening another online attempt. Merely calling `complete_task()` does not guarantee that the evaluator passes.

The evaluator runs after every attempt for the run has finished. It cannot guide actions, select recovery, rank attempts while executing, or stop the remaining attempt schedule. Oracle success is `any(success)` within a task/condition/replicate-seed cell. It is an upper bound assuming perfect outcome selection, not an implemented online selection policy. Single-attempt success uses attempt index zero, not the first successful or first feasible attempt.

## Analysis definitions

`analyze_runs` reads separately completed score files. It rejects mixed stages, incompatible configuration versions, duplicate cells, changed execution artifacts, or mismatched task/replicate-seed sets. Integration smoke results are flagged and cannot be pooled with research runs. Conditions must have the same paired tasks and replicate seeds. No task is silently discarded to manufacture a common subset.

For each condition, success is averaged over replicate seeds within each task and then over tasks. Replicate seeds are repeated budgeted experiments; analysis does not combine their attempts into a larger unbudgeted best-of-N. The 95% confidence intervals use percentile task bootstrap resampling, retaining every attempt, seed, and paired condition for each sampled task. Paired differences use the same task draws and are reported as the right-hand condition minus the left-hand condition. A single-task smoke interval is not evidence of generalization; the output reports the task count.

The analysis reports:

| Metric | Definition and unit |
| --- | --- |
| Oracle success | Fraction of tasks solved by any eligible attempt within each replicate's shared budget; replicate means are averaged by task |
| Single-attempt success | Fraction solved by attempt index zero, with failure and zero-attempt cells retained |
| Actual attempts | Mean number actually started per task/replicate cell, including failed attempts |
| End-to-end latency | Mean recorded cell elapsed seconds, including attempts, resets, tools, checkpoint costs, rebuilds, and outcome saving; excludes model loading and offline scoring |
| Decoding throughput | Sum of decode-produced tokens divided by summed decode seconds for attempts with both measurements; the first token produced by prefill is excluded |
| Peak KV memory | Maximum recorded live KV tensor bytes over attempts; distinct from allocated cache capacity and total VRAM |
| Peak total VRAM | Maximum recorded total VRAM bytes, including model/workspace/cache and rebuild transients |
| Estimated inference FLOPs | Sum of the engine's analytic forward-pass estimates, including rebuild prefill; an estimate, not a hardware-counter measurement |

Every resource aggregate reports the number of attempts with observations and the total number of attempts. Missing failure-path measurements are not silently replaced with zero. Throughput is unavailable when no positive decoding time was observed. Total estimated FLOPs and memory maxima describe the recorded observations; coverage makes partial instrumentation visible.

For a process interrupted inside an attempt, cell latency includes the remaining
budget consumed conservatively on resume. The attempt's `reserved_budget_seconds`
identifies this unobserved charge; it is not a measured execution duration. Do not
interpret interrupted-cell latency as a precise timing measurement.

The engine FLOPs estimate counts `2 * parameter_count * processed_tokens` plus attention work `4 * layers * query_heads * head_dimension * attended_query_key_pairs`. It uses physical retained cache length plus causal within-prefill pairs and includes every recorded prefill/decode/rebuild forward. This is an architecture-level arithmetic estimate, not elapsed compute, GPU utilization, or a precise kernel operation count. Non-matmul operations and eviction-selection work are excluded; the full parameter count makes the dense term approximate. The method identifier is preserved in recorded metrics.

## Validation

Focused tests cover fresh-state isolation, saved outcome isolation, checkpoint aliases and RNG, restoration without replay, unsupported state rejection, scoring gates and failure retention, task-level oracle accounting, exact seed pairing, and task-bootstrap uncertainty. The opt-in `tests/test_appworld_integration.py` uses `COMET_APPWORLD_ROOT` to check the pinned installed AppWorld package and a train task. It exercises task context, fresh reset, supervisor state changes, database and namespace restoration, ordinary continuation, independent offline scoring, and wall-budget interruption. Passing synthetic tests alone is not an AppWorld integration result. Live validation evidence and hardware-specific limitations are recorded in the shared validation document.
