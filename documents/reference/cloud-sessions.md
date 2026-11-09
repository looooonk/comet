# Bounded cloud study sessions

For adaptive train/dev work, `infra/gcp/study_worker.sh` keeps one prepared GPU
allocation alive while accepting successive immutable launch plans. This is an
operational wrapper around the same experiment launcher, scorer and analysis;
it does not change task execution or budgets. Set up and activate the managed
hybrid runtime first, and export `COMET_REPO`, `COMET_ENV`, `COMET_STORAGE`,
`COMET_MODEL`, `COMET_RUNTIME_PROFILE` and `OUTPUT_DIR` as usual.

The cloud staging mount contains `queue/NN-name/run.sh` and that plan's resolved
configs. Upload all inputs before its final `READY` marker. Only trusted,
reviewed scripts for this study belong in the queue. The worker copies a ready
plan to its own output directory once, executes it with `COMET_PLAN_DIR` and
`COMET_RESULTS_DIR`, and publishes a closed archive and exit status under
`reports/NN-name/`. A nonzero exit remains visible and is not automatically
retried. Source `infra/gcp/study_segments.sh` before starting the worker when a
plan uses `run_segments config.json run-name cell-limit segment-limit`.

Clean cell segments use the existing `--max-cells` and `--resume` behavior;
completed segments are archived under `checkpoints/` before the next launch.
Scoring runs only after the complete experiment manifest is closed. Optional
`scripts/monitor_cells.py OUTPUT_DIR` prints execution statuses and timing,
never evaluator outcomes. Preserve the submitted plan with the results.

A `queue/STOP` marker ends the worker after its current plan. Its own queue
loop lasts at most 6 hours 45 minutes; the cloud task must also have an explicit
outer timeout, which bounds any active plan. Choose that timeout within the
current execution authorization and spending ceiling; the queue limit is not
permission for a longer paid allocation. `COMET_CLOUD_STAGE` can override the
mount root for a local transport check.

An interrupted active segment may have newer journals than its last closed
archive. Do not restart those cells with refunded budgets. Fetch current journals
when available; otherwise retain the missing active segment as interrupted and
account for its full reserved budgets. Do not present a closed backup as proof
that no later computation occurred. The existing runtime/source checks still
apply when resuming on another worker.
