# Process interruption validation

`tests/test_resume_integration.py` runs the actual model/AppWorld CLI twice inside
one existing GPU allocation. It kills only its child process group; it does not
submit or cancel scheduler jobs. The test needs a fresh artifact directory outside
tracked source, the installed pinned runtime, model weights, and AppWorld data.
It always uses `--integration-smoke` and cannot freeze experiment settings.

Prepare a provisional pilot configuration with one train/dev task and one seed,
three full-cache conditions in order, and the ordinary agent prompt. Give the
first and third conditions `max_attempts: 1`, and the middle condition the shared
`max_attempts` of at least 2. Distinct condition IDs identify preservation,
interruption, and fresh continuation; they are validation repetitions, not an
additional research comparison. Keep context, sampling, budget, and cap identical
across the three conditions. A completed first cell may contain an execution
failure; this test does not require or claim task success.

From the runtime environment inside the allocation:

```sh
source "$COMET_REPO/scripts/activate_runtime.sh" gpu
COMET_RESUME_CONFIG=/path/to/resume-config.json \
COMET_RESUME_ARTIFACT_DIR=/path/to/new/resume-evidence \
COMET_MODEL_PATH=/path/to/pinned/Qwen3-8B \
COMET_APPWORLD_ROOT=/path/to/appworld \
python -m pytest -q tests/test_resume_integration.py
```

The overall timeout defaults to twice the configured cell budget plus 600 seconds
for initialization and interruption. Override `COMET_RESUME_TIMEOUT_SECONDS` when
needed, up to one hour. This harness deadline never increases the runner's cell
budgets. Keep source, installed packages, hardware, and the original resolved
configuration unchanged for the entire test.

The harness waits for the first cell to finish and a real model-generated action
and observation to be saved in the second cell. It pauses and kills that CLI
process group, checks that a changed-budget resume is rejected without modifying
run artifacts, and resumes the original configuration. It verifies:

- Every file in the completed cell retains its hash and modification time.
- The interrupted trajectory is unchanged, the attempt remains a failure in both
  `cell.json` and `attempt.json`, and the cell consumes its whole budget without
  starting a replacement attempt.
- The remaining cell starts at attempt zero with the paired seed, its own
  AppWorld experiment/output directory, and the same initial generated turn and
  raw-token prefix as the original fresh attempt.
- Both successful launches are recorded, and execution never creates scores.

`report.json`, the resolved and intentionally incompatible configurations, CLI
logs, and all run artifacts remain in the requested directory, including on test
failure. Run offline evaluation and analysis separately after a passing resume
check. Report GPU model and source revision with the result; CPU regression tests
alone do not validate this process-kill path.

On resume, `reserved_budget_seconds` records the unobserved remainder consumed
conservatively after interruption; it is not a measured component duration.
`budget_elapsed_seconds` records the exhausted cell budget. Saved trajectory
content is retained, and unavailable per-attempt timing/metric values are not
reconstructed from that reservation.
