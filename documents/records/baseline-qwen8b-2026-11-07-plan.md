# Broader Qwen3-8B baseline pilot

Declared before execution on November 7, 2026. The user requested a few dozen
more extensive rollouts of the main 8B model after the managed runtime validation.

## Scope and selection

Use [pilot-baseline-broad-qwen8b.json](../../configs/pilot-baseline-broad-qwen8b.json):
all 19 families in AppWorld data 0.2.0 `dev.txt`, choosing each family's `_1`
variant by identifier and sorting lexicographically. Run replicate seeds 17 and
18 for 38 fresh attempts. No task is selected or removed based on a new outcome.
The three earlier prompt-development tasks (`3ab5b8b_1`, `23cf851_1`, and
`fac291d_1`) remain included and must be identified in the report. This is broader
dev coverage, not held-out accuracy or a randomized sample of all 57 variants.

Use the existing candidate prompt unchanged, pinned Qwen3-8B in BF16, and pinned
AgentKV Mini-SGLang. Each task/seed cell has one attempt, a shared 600-second
budget, a 40 GiB total VRAM cap, 32768 context tokens, and at most 4096 newly
generated tokens per turn. Temperature 0.6, top-p 0.95, and reasoning enabled are
unchanged. Full cache disables eviction; no recovery or diagnostic branch
checkpoints are enabled. The two seeds are independent N=1 replicates, not
best-of-2 under a shared task budget.

Run sequentially on one RTX A6000 through Slurm and the managed GPU profile.
This alternative-hardware development pilot does not qualify the main A100
experiment. Maximum task budgets total 22800 seconds (6 hours 20 minutes), plus
model initialization and offline evaluation. Reuse the existing model snapshot,
environment, and persistent caches; retain outputs in a fresh run directory.

## Execution and reporting

Validate the resolved configuration and its task membership before launch.
Commit the configuration and this plan first; record the clean source revision,
resolved configuration digest, dependency/model pins, GPU identity, run ID, and
Slurm job. Use the common `scripts/run_experiment.sh` launcher through
`infra/slurm/run.sh`. A compatible resume must preserve accumulated budgets and
completed cells; an interruption does not authorize free replacement attempts.

After all 38 cells are terminal, run `comet evaluate`, `comet analyze`, and
schema-2 trajectory auditing. Preserve execution failures, timeouts, and OOMs in
the denominator. Report:

- Task success for each seed and averaged over seeds, with a task-bootstrap
  interval retaining both replicates together.
- Per-task and per-attempt outcomes, status counts, elapsed time, throughput,
  estimated FLOPs, and peak total and KV memory where recorded.
- Error categories, repeated actions, error streaks, and representative ordinary
  observations supporting the next agent-behavior fixes.
- Full-cache invariants, artifact hashes, and storage growth.

Do not pool results with the 14B pilot, infer prompt improvement without a matched
8B control, or select a favorable task subset afterward. Scoring remains offline
and cannot change actions, stop attempts early, or alter this run's settings.
The retention/recovery matrix and budget-matched best-of-N remain separate work.
