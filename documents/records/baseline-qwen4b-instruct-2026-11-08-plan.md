# Broader nonthinking 4B dev baseline

The three targeted regression tasks cannot establish representative model
capability. This plan declares broader coverage before any 4B task outcomes:
all 19 families in AppWorld data 0.2.0 dev, taking variant `_1` and sorting by
identifier, with replicate seeds 17 and 18. The complete selection is copied
from the [earlier identifier-only plan](baseline-qwen8b-2026-11-07-plan.md).
That historical run had a defective sampler and predates the scoring repair;
its scores are not evidence about the corrected baseline.

The explicit configuration is
`configs/pilot-baseline-broad-qwen4b-instruct-v1.json`. It uses the model, native
nonthinking template, candidate prompt, sampling, budget and memory settings
from the [targeted 4B plan](execution-qwen4b-instruct-2026-11-08-plan.md), without
the old six-file inheritance chain. These are 38 independent N=1 cells, each
with a 600-second budget, not shared-budget best-of-2. All families remain
included regardless of difficulty or previous scores.

Qualify the new model before execution. A failed targeted pilot can motivate
diagnosis, but its zero success alone does not establish failure on the other
families. Unresolved inference or environment defects stop progression; fix
those before interpreting broader outcomes. Keep this run separate from the
targeted six cells and do not splice their results into this configuration.

The declared cell budgets total at most 6 hours 20 minutes, excluding model
loading and post-hoc scoring. Earlier corrected 8B and 14B targeted means imply
roughly 2.6-2.8 hours for 38 cells, but that extrapolation is neither measured
4B cost nor representative broad-task timing. Determine allocation segments
from measured 4B costs, keeping the exact configuration and shared budget
accounting. Cell-boundary stopping must preserve completed work and give no
extra attempts or time. Score only after the complete run has finished.

Report per-family outcomes, status and resource coverage, all failures, and
task-level uncertainty. Identify the historical prompt-development tasks
`3ab5b8b_1`, `23cf851_1`, `fac291d_1` and the recent regression tasks
`0d8a4ee_1`, `3ab5b8b_1`, `57c3486_1`. These previously exposed dev variants
are not held-out accuracy, a random sample of all 57 dev variants, or final
evaluation. Do not select a favorable subset for later reported comparisons.

## Bounded execution review after the targeted pilot

The [targeted result](execution-qwen4b-instruct-2026-11-08-results.md) is 0/6
with six normal completions. Its complete transcript and relevant API listings
do not show transport or observation truncation. This does not establish
capability across the other 16 predeclared families. The
[explicit scope extension](qwen4b-broad-pilot-qualification-2026-11-08.json)
applies the existing model-specific A6000 numerical evidence to these 38 new
exploratory cells. It preserves both failed original BF16 reference screens,
the independent FP32 comparison, and unchanged thresholds. It does not grant
final-study qualification or establish universal numerical equivalence.

The preferred allocation is one A6000, six host CPUs and 32 GiB host memory for
at most seven hours. Execution is bounded to 23,400 seconds: the 22,800-second
ceiling of all cell budgets plus 600 seconds for model loading and shared
startup. Preflight, offline scoring and analysis have separate 300-, 600- and
120-second operational bounds. These ceilings are not runtime estimates.
Matched scheduler probes showed no placement advantage for shorter allocations;
one allocation avoids repeated model loading. It runs the exact committed
configuration on the unchanged qualified runtime, verifies fresh CUDA capacity
and runtime identities, and confirms all 38 cells are terminal before scoring.

The shared runner's [live resume check](resume-validation-2026-11-08.md) now
passes. If scheduling requires clean segmentation, the reviewed alternative is
six cells per 90-minute allocation and a final two-cell segment, all within one
run identity. It would preserve completed artifacts, prohibit overlapping jobs
and defer scoring until all cells finish. That fallback is unsubmitted; a
changed operational launch plan must be recorded before use.
