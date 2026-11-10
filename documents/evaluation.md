# AppWorld execution, scoring, and analysis

COMET keeps execution, scoring, and analysis separately callable. The online adapter never calls the evaluator and loads each task with `load_ground_truth=False`. Completion means the agent called AppWorld's supervisor completion API; it does not imply task success. Scoring begins only after the execution manifest and every configured task/condition/replicate-seed cell are complete.

## Provisional reports during execution

An explicitly requested partial report can score an isolated snapshot while the
remaining study runs. Use a fresh output directory outside the live run:

```sh
python -m comet.partial snapshot PARTITIONS LIVE_STUDY PARTIAL_REPORT
python -m comet.partial score PARTIAL_REPORT --workers 4
```

The snapshot includes only conditions that have finished the entire frozen
task/seed set. It retains every failure, lists coverage for all declared conditions,
and copies saved environments before scoring. It does not acquire the live run
lock, modify execution artifacts, or feed evaluator results to the agent. The
shared AppWorld scorer and paired-task analysis compute the results. Missing
conditions are unmeasured, not zero; every plotted point has the same paired tasks.

Scoring workers use separate processes because AppWorld owns process-global
database state. Use at most the allocated CPU count and one numerical-library
thread per worker. Cached outcomes support resuming the same snapshot with the
same evaluator and runtime.

When live workers contend for shared database files, prepare job-local scoring
assets with `scripts/stage_partial_assets.py prepare PARTIAL_REPORT --source
APPWORLD_ROOT --destination JOB_LOCAL_ROOT`. This copies the base databases,
shares immutable task assets, and redirects only the copied snapshot references.
Run `scripts/stage_partial_assets.py restore PARTIAL_REPORT` on exit to restore
those references. Original execution artifacts remain untouched.
If reads of the shared databases themselves stall, `--base-databases` may point
to an independent copy from the same pinned AppWorld data release. The helper
checks the database filenames and sizes against the installed layout and records
the copied files' hashes. This is an offline asset relocation, not a benchmark
version change.

With the managed CPU plotting runtime, render the provisional graph with:

```sh
python -m comet.partial_plot PARTIAL_REPORT PARTIAL_REPORT/aggressivity.png
```

The graph leaves gaps at missing retention points. If the full-cache best-of-two
control is pending, it is omitted from the oracle panel; the single-attempt
control can still appear in the first-attempt panel. These reports are labeled
provisional and cannot pass the normal complete-study scoring/analysis gates.
Create a new snapshot to refresh coverage. Pass `--reuse-report PREVIOUS_REPORT`
to reuse completed scores from the same frozen study. Previously scored terminal
cell hashes must still match, and scoring requires the same evaluator source and
runtime. Only newly covered conditions need fresh environment copies and scoring.
The new snapshot records its parent snapshot and score hashes; retain that prior
report and its saved environments as part of the evidence. Keep the study frozen
regardless of the provisional results.

## Pinned environment

The adapter targets [AppWorld commit 42b5bcf](https://github.com/StonyBrookNLP/appworld/tree/42b5bcf3cd334fee33f0c37c02070a9f5807add5), package version `0.2.0.dev0`, and data version `0.2.0`. This is an implementation dependency choice, not a change to the benchmark. The installed distribution must record this exact Git revision in its direct installation metadata. See the shared setup instructions and dependency lock for the resolved transitive dependencies, LFS bundle hydration, and installed package constraints.

Verified upstream entry points at that revision are `AppWorld(..., load_ground_truth=False)`, `execute`, `task_completed`, `save`, `save_state(state_id=...)`, `load_state(state_id=...)`, `close`, and the separate `evaluate_task`. The adapter uses local execution with remote modes disabled. It leaves AppWorld's syntax and execution safety checks enabled. The shared runner enforces the wall-clock deadline; AppWorld's inner timeout is disabled so it cannot replace the runner's signal timer. Interaction and API-call ceilings are set to the platform integer maximum, leaving the configured context and shared wall-clock budget as the experiment limits.

AppWorld freezes the task's clock through Freezegun. COMET's elapsed-time measurements must use the real monotonic clock rather than task time. An outer deadline may be turned into an ordinary execution error by IPython; the runner also checks the budget on return and records the attempt as a timeout. The adapter restores AppWorld's process-wide execution patches even if execution raises.

COMET normalizes named in-memory database identities from SQLAlchemy's structured
URL. The pinned AppWorld parser uses a rendered URL; percent-encoding of `file:`
can otherwise separate live mutation counters from the counters saved or loaded
for evaluation. This compatibility patch changes the database identity used for
bookkeeping, not the database connection or task actions. Saved outcomes and new
checkpoints record `database_path_version: "structured-memory-v1"`. Checkpoint
restore rejects older metadata, whose historical counters may be missing.

The initial task context contains the instruction, public supervisor information, task date, app descriptions, and the `api_docs` and `supervisor` documentation. Other APIs are discoverable through the documented API interface. It contains no reference solution, required-action list, evaluator feedback, or private task data. The configurable system prompt is stored in the resolved run configuration. A model turn must contain exactly one nonempty fenced `python` or `py` block. One accepted block is one tool call, even when the block invokes several AppWorld APIs. Invalid formatting produces an observation without executing code.

## Attempt and checkpoint state

Every reset creates a new AppWorld instance and a unique output namespace. Final evaluation starts from the initial task state. An attempt's `environment/live.json` identifies AppWorld's automatically saved database and execution logs, including failed attempts that could not finish copying their outcome within the budget. Successfully saved outcomes include `environment/reference.json` and a copy of the AppWorld task output in `environment/task/`. This includes database changes relative to the benchmark base data and the code/data version markers required for offline evaluation.

Upstream `save_state` stores database state only. It does not save the interactive Python namespace, random state, counters, or logs. COMET checkpoints add these, then restore database state and execution values without re-executing historical tool actions. The checkpoint also preserves alias relationships between supported Python values, Python's global RNG, NumPy's global RNG when loaded, the environment interaction counters, and the request log and counter. The task clock is reinstated after upstream `load_state` clears it. The runner separately stores raw token IDs, KV state, sampling state, and recovery counters. Restoring the environment precedes restoring the engine RNG state.

Execution checkpoints currently support data-valued Python variables: builtin scalar/container values, common standard date/time and numeric values, regular expressions, and module aliases. User-defined functions and classes, generators, API-handle aliases, open resources, unusual container subclasses, and changed runtime bindings fail explicitly with `UnsupportedPath`. They are never silently dropped or reconstructed by replay. Such a diagnostic branch is reported as infeasible. This limitation does not prevent ordinary final-evaluation attempts from executing those constructs. Broader execution snapshots need a separate implementation and live validation before being claimed as supported.

Checkpoint execution files are trusted local pickle artifacts with identity and checksum checks. Do not load externally supplied checkpoints. A restore must match the task, seed, code revision, data version, and checkpoint schema. The parent checkpoint also validates engine and configuration compatibility.

## Offline evaluation

Run the shared CLI's `evaluate` command after execution. `evaluate_run` checks the manifest's exact Cartesian task/condition/seed set, every cell's identity and completion flag, ordered attempt indices, attempt limits, and terminal statuses before invoking any evaluator. It holds the run lock and writes `scores.json` separately from online artifacts. A scoring error raises instead of being silently converted into a failed benchmark task. Completed cell scores survive an interrupted scoring job; modified execution artifacts invalidate existing scores.

Only attempts with execution status `completed` are eligible for a successful AppWorld score. Timeouts, out-of-memory errors, context-limit terminations, interrupted attempts, infeasible attempts, and other execution errors remain failures. Zero-attempt cells remain in the denominator. Failure outcomes are not given free replacements. Each eligible saved outcome is copied into a separate scoring namespace, with AppWorld caches cleared before and after evaluation. The task score and report are saved without opening another online attempt. Merely calling `complete_task()` does not guarantee that the evaluator passes.

Scoring verifies actual saved state for every model. In the temporary scoring
copy only, each model's change counter is set to its initial counter plus one.
This disables the pinned evaluator's counter-equality shortcut: its unchanged
row-count and record-hash comparisons determine whether a model changed. It does
not declare every model changed, alter a row, replay an API action, or change a
task requirement. The initial counters are loaded without ground truth, and
`evaluation/state-comparison.json` records the original counter-file hash and
comparison metadata. Global counter caches are cleared before and after scoring.
This also permits truthful evaluation of intact historical SQL snapshots whose
exported counters were lost.

Use an explicit scoring revision to preserve existing outputs:

```sh
comet rescore "$ORIGINAL_RUN" --output "$NEW_SCORING_RUN"
comet analyze "$NEW_SCORING_RUN" --output "$NEW_SCORING_RUN/analysis.json"
```

The new directory contains byte-identical execution metadata, cells and available
checkpoints, with the same execution digest. It archives prior scores/analysis
under `rescoring/` and records their hashes and the new scorer provenance.
Original reports remain untouched. A preparation marker prevents an interrupted copy from being scored; create a
new revision if preparation failed. Once preparation completes, interrupted
scoring resumes with `comet evaluate "$NEW_SCORING_RUN"`; it still requires the same evaluator and
execution digests. Revisions are alternative scores of the same execution, not
additional independent runs, and must not be pooled together.

The evaluator runs after every attempt for the run has finished. It cannot guide actions, select recovery, rank attempts while executing, or stop the remaining attempt schedule. Oracle success is `any(success)` within a task/condition/replicate-seed cell. It is an upper bound assuming perfect outcome selection, not an implemented online selection policy. Single-attempt success uses attempt index zero, not the first successful or first feasible attempt.

## Analysis definitions

`analyze_runs` reads separately completed score files. It rejects mixed stages, incompatible configuration versions, duplicate cells, changed execution artifacts, or mismatched task/replicate-seed sets. Integration smoke results are flagged and cannot be pooled with research runs. Conditions must have the same paired tasks and replicate seeds. No task is silently discarded to manufacture a common subset.

For each condition, success is averaged over replicate seeds within each task and then over tasks. Replicate seeds are repeated budgeted experiments; analysis does not combine their attempts into a larger unbudgeted best-of-N. The 95% confidence intervals use percentile task bootstrap resampling, retaining every attempt, seed, and paired condition for each sampled task. Paired differences use the same task draws and are reported as the right-hand condition minus the left-hand condition. A single-task smoke interval is not evidence of generalization; the output reports the task count.

Every mean estimate also reports `standard_error`, the sample standard deviation
of the task means divided by the square root of the number of observed tasks.
It is `null` with fewer than two tasks. Paired differences use the standard
deviation of within-task differences, not independent condition errors. Repeat
seeds do not multiply the independent task count. A constant sample can produce
zero estimated SE and a collapsed bootstrap interval; `bootstrap_degenerate` and
`uncertainty_notes` explicitly flag that this does not establish zero population
uncertainty.

Success estimates additionally report `bounded_mean_ci95`: a conservative,
distribution-free Hoeffding interval for independent task means in `[0, 1]`,
clipped to that range. Its radius is `sqrt(log(40) / (2*T))` for `T` tasks. Paired
success differences lie in `[-1, 1]` and use twice that radius. This remains
applicable when seeds are averaged within tasks, including all-failure samples;
it is not a binomial interval treating repeated attempts as independent tasks.
All intervals are pointwise 95%, not simultaneous guarantees across the plotted
conditions or metrics. They assume independent sampled tasks. Correlated
variants of one task family, hand-picked subsets, or a small development pilot
do not establish precision for the full benchmark or a frozen test population.

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
| Mean peak KV / total VRAM | Maximum within each cell's attempts, averaged over seeds within each task, then over tasks; bytes with task SE and bootstrap CI |
| Estimated inference FLOPs | Sum of the engine's analytic forward-pass estimates, including rebuild prefill; an estimate, not a hardware-counter measurement |

Every resource aggregate reports the number of attempts with observations and the total number of attempts. Missing failure-path measurements are not silently replaced with zero. Throughput is unavailable when no positive decoding time was observed. Total estimated FLOPs and memory maxima describe the recorded observations; coverage makes partial instrumentation visible.

Numeric metric summaries also retain the attempt-level coverage labels. A
`lower_bound` token or FLOPs count includes completed forwards before a failure;
it is not the full operation cost. A `partial` time records observed elapsed work,
without claiming that an interrupted GPU operation finished. Older values without
coverage metadata are `unspecified`, not retrospectively certified complete.
Decode throughput retains its ratio of observed counts and times and reports
whether those contributing attempts contain partial measurements. Do not compare
that observed ratio as complete throughput when coverage differs across methods.

Each condition includes a `recovery` summary of recorded policy decisions,
requests, admissions, completed/denied/failed/pending results, consumed allowances,
refusal reasons, and failure reasons. Admission rate divides admitted requests by
requests with a known admission outcome; its coverage also gives the total request
count. Unknown or pending outcomes are not refusals. Recorded recovery time includes
admission checks and observed failed rebuild time. The mean cell budget fraction
sums those recorded costs within a cell and divides by its configured shared budget;
it includes zero recovery cost only when the decision log is available and no
request occurred. Interrupted cells or cells missing any requested duration are
excluded from this cost fraction with explicit coverage. Decision counts are
observed counts, not proof that an interrupted attempt had no later decisions.

`mean_peak_kv_bytes` and `mean_peak_total_vram_bytes` retain a cell only when every
started attempt has its measurement; a zero-attempt cell has no observed peak.
A task mean requires complete cells for every configured seed. The output lists
observed attempts and complete cell/task counts, while preserving all failures
in success and latency summaries. Paired memory differences use only the shared
complete tasks and report their IDs. Missing resource measurements can bias these
observed-subset estimates; they are not grounds to drop failures from accuracy.
Global maxima remain in `metrics` as separate worst-observed summaries.

The engine's occupied KV peak includes transient page ownership during compaction
and full-history rebuild, and may exceed the post-compaction retained size.
The common `reserved_kv_pool_bytes` capacity is not resized with retention and
must not be substituted for occupied KV. Plot measured means at the actual
retention levels with their bounds; connect points only as a visual guide, without
smoothing or enforcing monotonicity. Independently evolving task trajectories can
have different lengths, and more aggressive retention need not reduce latency,
peak occupancy, or accuracy monotonically.

For a process interrupted inside an attempt, cell latency includes the remaining
budget consumed conservatively on resume. The attempt's `reserved_budget_seconds`
identifies this unobserved charge; it is not a measured execution duration. Do not
interpret interrupted-cell latency as a precise timing measurement. An initial
attempt `elapsed_seconds=0.0` may survive interruption as a journal placeholder;
without final timing evidence, report measured duration as unavailable and retain
the raw field separately.

If a terminal attempt journal was saved before the cell journal was interrupted,
the attempt's measured duration and outcome survive. In that case the unobserved
tail is stored in the cell's `reserved_budget_seconds` instead. Analysis reports
mean reserved budget separately and accounts for either journal location; the
ordinary cell latency still includes that reservation. A terminal attempt status
alone therefore does not establish that all of its cell time was measured.

The engine FLOPs estimate counts `2 * parameter_count * processed_tokens` plus attention work `4 * layers * query_heads * head_dimension * attended_query_key_pairs`. It uses physical retained cache length plus causal within-prefill pairs and includes every recorded prefill/decode/rebuild forward. This is an architecture-level arithmetic estimate, not elapsed compute, GPU utilization, or a precise kernel operation count. Non-matmul operations and eviction-selection work are excluded; the full parameter count makes the dense term approximate. The method identifier is preserved in recorded metrics.

## Paired protocol diagnostics

`comet.comparison.compare_protocol_runs` compares exactly two completed, separately
scored train/dev pilot runs. Declare the intended differences with
`protocol_fields=["prompt"]`, `["agent"]`, or both. The function permits those
fields plus experiment identifiers and notes to differ; every other configuration
field, task, seed, condition, dependency, model, hardware identity, execution
source/runtime, and evaluator source/runtime must match. It verifies scored cells
against the saved terminal execution records. This explicit comparison does not
relax `analyze_runs` or ordinary resume compatibility.

Save the comparison to a new output outside both original run directories. It
retains run IDs and configuration/execution digests, the declared intervention,
paired candidate-minus-control success and cost estimates, and per-condition
behavior summaries. Its success intervals use the same task-level bootstrap and
nondegenerate bounded-mean intervals as ordinary analysis.

Behavior summaries read each declared attempt's saved `trajectory.json` and record
its hash. The normalized error rate is error turns divided by saved turns within
each cell, averaged across replicate seeds within each task and then across tasks.
This prevents a long failing loop from dominating every shorter trajectory.
Missing trajectories are unavailable, not zero-error traces. Interrupted prefixes
remain visible in the error-rate summary and its coverage; they do not describe a
completed trajectory. A task-level behavior estimate requires observations for
every paired seed. Measured duration excludes interrupted-attempt journal
placeholders and reports its own complete-task coverage; reserved budget is
reported separately.

`comet.plotting.plot_baseline` renders a validated comparison's single full-cache
N=1 condition: task success, execution statuses (including cells with no attempt),
normalized errors, and measured attempt duration. Its caption distinguishes
interrupted prefixes and budget reservations. Normal completion, fewer errors, or
earlier stopping do not establish improved task success. These targeted diagnostic
plots do not replace broader declared dev coverage or frozen final evaluation.

## Validation

Focused tests cover fresh-state isolation, saved outcome isolation, checkpoint aliases and RNG, restoration without replay, unsupported state rejection, scoring gates and failure retention, task-level oracle accounting, exact seed pairing, and task-bootstrap uncertainty. The opt-in `tests/test_appworld_integration.py` uses `COMET_APPWORLD_ROOT` to check the pinned installed AppWorld package and a train task. It exercises task context, fresh reset, supervisor state changes, database and namespace restoration, ordinary continuation, independent offline scoring, and wall-budget interruption. Passing synthetic tests alone is not an AppWorld integration result. See the [validation guide](validation/README.md) for reusable checks and [records/](records/README.md) for dated evidence and hardware-specific limitations.

## Retention matrix figures

`comet plot-retention-matrix ANALYSIS --output FIGURE` plots all recorded methods,
recovery policies and attempt ceilings from one compatible shared analysis. Each
method/attempt-ceiling pair has its own row. Compressed conditions use policy
curves, and full-cache references with the same ceiling appear separately at
100% retention. No curve interpolates across different attempt limits or methods.
Missing full controls or duplicate compressed conditions are rejected.

The panels show oracle success, time, mean cell-peak occupied KV and mean cell-peak
total VRAM. Bounded task-mean intervals remain nondegenerate for all-zero success;
other intervals use the recorded task bootstrap. Missing resource points stay
missing and partial task coverage is annotated. Unobserved interruption
reservations trigger a budget-accounted time label. Slight horizontal policy
offsets improve visibility at identical retention settings and do not change the
underlying measured settings. The older `comet plot` command remains available
for the original one-method, one-ceiling, no-recovery figure.

## Recovery, trigger and attempt figures

The shared analysis retains paired task/seed identities, actual attempt counts,
cell outcomes, and recorded recovery decisions in each condition's `observations`.
These are offline reporting data, never inputs to the runner. Regenerate older
analysis files before using the following commands:

```sh
comet plot-recovery ANALYSIS --output recovery.svg
comet plot-triggers ANALYSIS --output triggers.svg
comet plot-attempts ANALYSIS --output attempts.svg
```

Recovery figures compare fixed and dynamic policies with a matched never-rebuild
condition at the same method, retention and attempt ceiling. They show paired
oracle-success differences, recorded time per observed request, mean cell budget
share, admission coverage, and refusal reasons. Thin intervals are task-bootstrap
95% intervals; pale wide intervals are conservative bounded task-mean intervals,
so all-zero samples do not imply population certainty. Cost and admission bars
are descriptive; repeated requests are not independent samples. Unknown admission
and incomplete cost coverage remain explicit.

Trigger figures show every located decision, including checks after a rebuild,
with requests highlighted, alongside dynamic-minus-fixed paired success. These
are observations on independently evolving trajectories, not fitted decision
boundaries or causal estimates from individual points. Actual trigger rules and
thresholds remain in the resolved run configuration.

Attempt figures show first-attempt and oracle success, distributions of actual
attempt counts including zero, and oracle success versus total cell time. Each
seed is a separate budgeted cell. The cost panel describes executed schedules;
it does not estimate time to first success or counterfactual outcomes under
smaller budgets. Interruption reservations remain part of budget-accounted time
and are identified in the caption. Oracle success assumes perfect outcome
selection after execution; it is not an online selection policy.

## Attained success over time

`comet plot-success-time ANALYSIS --output success-time.svg` plots success
available by cumulative budget-accounted time along the schedules that actually
executed. Reanalyze older scored runs to add the required timing observations.
This is a descriptive oracle upper bound assuming perfect outcome selection,
not an online selector, a rerun under a smaller budget, or a counterfactual
budget-performance curve. A scored success becomes available at its recorded
attempt completion, including charged preparation, resets, tools and cleanup;
post-hoc scoring time remains excluded.

Each condition's `observations.attempts` retains paired task/seed identities,
execution status, separately scored success, the recorded
`budget_elapsed_seconds`, validated `completion_seconds`, and timing coverage.
Cell observations identify the first successful attempt and its timestamp.
Interrupted attempts and their reserved budget never supply measured completion
times. A later cell-level reservation does not invalidate an earlier measured
success. There is no fallback to summed attempt durations or total cell time.
Invalid, missing, or nonmonotone success timestamps remain unavailable.
Malformed reservation values invalidate their attempt and subsequent cumulative
timestamps; aggregation rejects these invalid totals explicitly.

The `observations.attained_oracle_curve` uses exact observed success times, zero,
and the declared budget endpoint. It averages seeds within each task and reuses
the analysis's paired task-bootstrap draws at every time and condition. Failed
and zero-attempt cells remain in the denominator. If any first-success time or
declared budget is unavailable, that condition has no estimated curve; its
coverage and affected identities remain explicit. It is neither dropped nor
treated as an all-failure condition. No-success cells need no completion timestamp
to contribute their known zero along the executed schedule.

Figures use right-continuous steps without smoothing, at most three columns,
separate attempt-ceiling panels, and up to three recovery policies plus the
matched full-cache control. Darker bands show pointwise task-bootstrap 95%
intervals; pale bounded task-mean intervals remain nondegenerate for all-zero or
all-one samples. These intervals are not simultaneous across time or conditions.
Legend counts report cells with complete curve information over all cells.
When several full-cache attempt limits are available, an additional panel compares
those controls directly; compressed panels retain only their matching control.

## Independently executed budget sweeps

Use a separate report for train/dev pilot runs that actually executed under
different declared wall-clock budgets:

```sh
comet analyze-budget-sweep "$SHORT_RUN" "$LONG_RUN" --output budget-sweep.json
comet plot-budget-sweep budget-sweep.json --output budget-sweep.svg
```

Only the budget, experiment identifier and notes may differ across budget points.
The prompt, sampling, model, hardware, execution/evaluator sources and packages,
dependencies, memory cap, context limit, thresholds, attempt ceilings, exact tasks
and paired seeds must match. Each budget must contain the same condition
definitions. Disjoint condition shards at one budget may be supplied separately,
but must share an experiment identifier; overlapping shards, missing conditions,
duplicate executions or scoring revisions, and incomplete execution/scoring are
rejected. This path does not enable diagnostic or frozen final-evaluation shards.
It verifies scored cells against saved terminal records and preserves source
config/execution digests and score-file hashes in a new external report.

Each point is oracle task success at the end of an independently executed budget,
with seeds averaged within task. One task-bootstrap draw table is reused across
every budget and condition; bounded task-mean intervals remain nondegenerate for
all-failure samples. All intervals are pointwise, not simultaneous. Failed and
zero-attempt cells remain in the denominator, with attempt statuses, coverage and
unobserved budget reservations retained. `budget_accounted_seconds` reports mean
cell accounting, including these reservations; it is not measured latency.
`reserved_budget_seconds` separately identifies the unobserved charge.
The horizontal axis is the declared
budget: no success timestamp, inferred truncation or interruption reservation is
used to fabricate another budget point. These curves differ from attained-success
steps above, which describe one executed schedule. Connected endpoints only guide
the eye; neither monotonic improvement nor interpolation is imposed. The report
does not choose budgets or authorize new experiments.
