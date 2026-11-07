# Full-cache baseline diagnostic

Use the full-cache control to establish usable agent behavior before interpreting
retention or recovery results. Execution completion alone is not task success.
The paired `pilot-baseline-control.json` and `pilot-baseline-repair.json` configs
retain the same engine, numerical settings, task subset, seed, and single-attempt
budget. The control preserves the completion-v4 prompt. The candidate adds generic
instructions for explicit authentication tokens, complete task coverage and
pagination, and inspecting response types after errors. These are ordinary agent
actions charged to the existing budget; no API injection or online scoring is
introduced.

The diagnostic uses three dev tasks selected from observed failure mechanisms:
`3ab5b8b_1` for authentication, `23cf851_1` for pagination, and `fac291d_1` for
response-shape errors. This is a targeted regression set, not a representative
success estimate. The bundled intervention tests whether the combined guidance
helps; it cannot attribute changes to individual instructions. It contains no
reference solutions, expected answers, evaluator results, or task-specific API
recipes. Preserve all attempts, including timeouts and failed candidates.

Both configs use Qwen3-8B. Their explicit `-qwen14b` variants implement the already
authorized [exploratory model policy](experimental-models.md) and must stay
separate from the main Qwen3-8B/A100 research comparison. Each three-task run has
at most 30 minutes of task budgets plus initialization. Run both variants on the
same device type with the paired seed before post-hoc evaluation. No experiment
settings in these files are frozen for final evaluation.

Inside a suitable allocation with the managed GPU environment, use the shared
launcher twice, choosing fresh output directories:

```sh
export COMET_CONFIG="$COMET_REPO/configs/pilot-baseline-control.json"
export COMET_RUN="$COMET_STORAGE/runs/baseline-control-unique-id"
bash "$COMET_REPO/scripts/run_experiment.sh"
export COMET_CONFIG="$COMET_REPO/configs/pilot-baseline-repair.json"
export COMET_RUN="$COMET_STORAGE/runs/baseline-repair-unique-id"
bash "$COMET_REPO/scripts/run_experiment.sh"
```

Set `COMET_MODEL` to the matching pinned snapshot and use
`COMET_INTEGRATION_SMOKE=1` only for alternative-hardware validation. Once both
runs finish, evaluate each separately with `comet evaluate`, audit each saved run
with schema 2, and inspect task-level outcomes and error streaks. Analyze each
experiment separately: the shared analysis deliberately refuses to pool different
experiment configurations. A descriptive paired task table can compare the two
configurations while retaining their identities. Do not turn these three tasks
into an accuracy claim or choose a favorable subset afterward.

If the guidance is ineffective, retain that evidence and investigate prompt
adherence or another concrete failure mechanism before expanding the matrix.
A versioned candidate is not a validated replacement until saved trajectories and
separate scoring support it. The main A100 pilot, settings freeze, recovery, and
budget-matched best-of-N comparisons remain required.
