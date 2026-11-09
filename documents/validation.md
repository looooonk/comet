# Validation guide

Validation has three layers: CPU checks, live integration checks, and recorded
task execution with separate scoring and analysis. Passing one layer does not
establish the others. Use the pinned environments in [setup.md](setup.md).

## CPU checks

After creating the managed CPU environment in [setup.md](setup.md):

```sh
export COMET_CHECK_OUTPUT="$COMET_REPO/artifacts/checks/cpu-unique-id"
bash scripts/run_checks.sh cpu
```

These check configuration, retention accounting, policies, budgets, state
isolation, scoring gates, and aggregation. Report skips explicitly; mocks and
accounting tests do not validate the installed CUDA or AppWorld integrations.

For repeatable allocated checks, use `infra/slurm/setup.sh` followed by
`infra/slurm/check.sh` as described in [setup.md](setup.md). The underlying
`scripts/run_checks.sh cpu|appworld|gpu` also runs directly inside an allocation.
It requires `COMET_REPO`, the matching managed `COMET_ENV`, and a new absolute
`COMET_CHECK_OUTPUT` directory. CPU checks run lint, shell syntax, and unit tests;
AppWorld checks require installed data; GPU checks run the entire suite with the
pinned model. Missing required inputs fail before testing. Existing evidence
directories are never overwritten.

Each check saves the source revision/diff and hashes (including scripts and tests),
runtime lock identity, package list, Slurm allocation when present, pytest XML, and exit status. GPU checks also save
the device report and engine evidence. Skips remain explicit: a minimal CPU
runtime cannot run numerical engine checks, and process-interruption testing
requires the separate configuration below. Set `COMET_TEST_CAPACITY=1` to include
the optional near-limit context check. Always inspect skips as well as exit codes.

An already managed GPU runtime can run its native CPU selector tests inside a
CPU allocation without a model or GPU:

```sh
bash "$COMET_REPO/scripts/run_checks.sh" gpu --cpu-only
```

This keeps GPU-profile ownership verification and the installed pinned engine,
masks CUDA devices, and selects tests marked neither `gpu` nor `appworld`.
`mode.txt` records the selection. Shell syntax checks still run; lint runs only
when `ruff` is installed, with its absence recorded in `lint-status.txt`. No
packages are synchronized. The Slurm check wrapper forwards the same option.
Native CPU checks validate selector outputs and accounting, not persistent GPU
KV, checkpoint/recovery execution, or inference at the newly checked settings.

## Live integration checks

Inside an allocated GPU node, select the managed GPU environment and run:

```sh
export COMET_MODEL_PATH=/path/to/pinned/model/snapshot
export COMET_APPWORLD_ROOT=/path/to/appworld
export COMET_CHECK_OUTPUT="$COMET_STORAGE/validation/gpu-unique-id"
export COMET_TEST_CAPACITY=1
bash "$COMET_REPO/scripts/run_checks.sh" gpu
```

The runner preserves `sampling.json`, `gpu.json`, `memory.json`, and, when requested,
`capacity.json` alongside pytest results. For a focused debugging command, first
source `scripts/activate_runtime.sh gpu`; use the runtime's Python directly.
Do not run `uv run` inside it, since automatic project synchronization can remove
its CUDA/AppWorld dependencies.

`COMET_GPU_CAP_BYTES` sets an explicit persistence/capacity-check memory cap,
defaulting to 40 GiB. `COMET_REFERENCE_CAP_BYTES` separately sets the numerical
reference-check cap. These overrides are recorded in the check settings and
still require actual CUDA allocations to fit; they do not change the calculated
tight cap used by the dedicated admission-refusal check.

The AppWorld fixtures check execution, fresh resets, checkpoint restore, offline
evaluation, explicit authentication, parsed response types, and pagination. The
authentication and pagination probes use isolated dev environments, perform only
read operations, and never consult evaluator feedback. The GPU checks cover
seeded sampling and RNG advancement/replay across all four sampler paths, greedy
RNG preservation, persistent compressed KV, checkpoint replay, recovery, and live cap refusal. [engine.md](engine.md) defines their
accounting and evidence scope. [checkpoint-validation.md](checkpoint-validation.md)
describes the opt-in combined Runner/AppWorld/GPU branching fixture. Follow
[resume-validation.md](resume-validation.md) for clean segmentation followed by
process interruption; it needs a dedicated configuration and artifact directory.

Then run small train/dev tasks through the execution, scoring, and analysis
commands in [experiments.md](experiments.md). Distinguish an agent reaching
completion from passing the AppWorld evaluator. Retain failed attempts and their
budget charges. Unqualified hardware checks must use integration mode and cannot qualify final
evaluation. The [hardware decision](experimental-hardware.md) permits other
adequately sized GPUs; explicitly pin `engine.device_name`, validate the intended
range, and keep comparisons on the same GPU model.

## Recording evidence

Keep personal execution notes and dated validation reports in
[records/](records/README.md). Record source and dependency revisions, resolved
configuration, hardware, checks performed, failures, and limitations. Include
artifact filenames and hashes; link only storage accessible to collaborators.
Omit account-specific access details and private storage locations. Large logs,
trajectories, weights, and checkpoints belong in external storage or ignored run
directories, with small summaries committed here.

Consult the applicable record before claiming a path has been validated. Results
apply to its recorded configuration, source, hardware, and test scope; they do not
automatically validate later changes or a different deployment.
