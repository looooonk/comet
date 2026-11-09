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
