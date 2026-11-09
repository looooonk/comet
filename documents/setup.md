# Setup and execution

## New Qwen hybrid profile

For the current Qwen3.5-9B implementation, use profile `hybrid` with the same
managed setup, activation and check scripts. This pins Transformers 5.22.2 and
packages the existing AgentKV selectors without installing the legacy server.
The benchmark root can be reused. All loading, inference and GPU checks run
inside a suitable allocation.

```sh
bash scripts/setup_runtime.sh hybrid "$COMET_ENV"
bash scripts/download_assets.sh "$COMET_ENV" "$COMET_APPWORLD_ROOT" --model-9b-hybrid
source scripts/activate_runtime.sh hybrid
export COMET_MODEL_PATH="$HF_HOME/hub/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a"
export COMET_TEST_RETENTION_GRID=1
export COMET_LOCAL_MODEL=1
bash scripts/run_checks.sh hybrid
export COMET_RUNTIME_PROFILE=hybrid
export COMET_MODEL="$COMET_MODEL_PATH"
bash scripts/run_experiment.sh
```

As for other profiles, set `COMET_REPO`, `COMET_ENV`, `COMET_STORAGE`, a fresh
`COMET_CHECK_OUTPUT`, and explicit experiment `COMET_CONFIG`/`COMET_RUN` paths.
The hybrid backend must be selected in the configuration. Its [state contract](hybrid-backend.md)
and [current evidence](records/qwen9b-study-2026-11-09.md) distinguish implementation
from qualification. The remainder of this guide documents the legacy backend.

`COMET_LOCAL_MODEL=1` stages the pinned snapshot in `SLURM_TMPDIR` (or an explicit
job-local `TMPDIR`) before loading. It reuses a complete staged copy within the
same allocation, records bytes/time, and leaves the persistent snapshot intact.
Allocate at least 21 GB of scratch space for 9B. Staging is model initialization,
outside task timing; ordinary execution and rebuild allocations remain charged.

On slow shared storage, archive the ready managed runtime once inside a CPU
allocation: `python scripts/stage_runtime.py pack "$COMET_ENV" RUNTIME.tar`.
Set `COMET_RUNTIME_ARCHIVE` to that archive for subsequent jobs. Activation
unpacks the same environment into job-local scratch and checks its checkout,
profile and locks as usual; it does not resolve or install new packages.
Rebuild the archive after runtime changes. Allow another 8 GB of scratch for
the hybrid profile. Initialization logs record staging time. Persistent caches
and outputs remain in their configured locations.

The sections below describe the retained legacy implementation. Follow the
[current direction](research-direction.md) when selecting the active backend.

COMET has a small CPU environment for configuration, policies, accounting, analysis,
and unit tests. Model inference uses a separate Linux x86_64 Python 3.12 environment.
Every method uses the same pinned Mini-SGLang engine. Nothing in the CPU tests
establishes that the CUDA or AppWorld integration works.

## Local development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```sh
export COMET_REPO="$PWD"
export COMET_ENV="$COMET_REPO/.venv-cpu"
bash scripts/setup_runtime.sh cpu "$COMET_ENV"
export COMET_CHECK_OUTPUT="$COMET_REPO/artifacts/checks/cpu-unique-id"
bash scripts/run_checks.sh cpu
source scripts/activate_runtime.sh cpu
comet --help
```

`uv.lock` fixes the CPU dependencies. The shared setup and managed CI job use
Python 3.12 and uv 0.13.0. A separate CI job checks the declared Python 3.11 minimum.
Core COMET requires only the standard library. CUDA kernels are deliberately
absent from this environment. The common activation helper verifies the selected
checkout and profile; use it before direct commands. Slurm checks, experiments,
asset downloads, and the GCP launcher use the same activation path.

## Runtime environment

Use a Linux x86_64 compute node with Python 3.12, Git, a compiler, and a CUDA toolkit.
The current runtime lock uses PyTorch 2.9.1 with CUDA 12.8 libraries. The native CUDA
toolkit must be on `PATH`, with `CUDA_HOME` set, for kernel compilation. Runtime
compatibility checks and model loading must happen inside a GPU allocation.

```sh
export COMET_STORAGE=/path/to/persistent/project/storage
source scripts/runtime_caches.sh
export CUDA_HOME=/usr/local/cuda
export PATH="$CUDA_HOME/bin:$PATH"
export COMET_REPO="$PWD"
export COMET_ENV="$COMET_STORAGE/environments/my-checkout-gpu"
bash scripts/setup_runtime.sh gpu "$COMET_ENV"
bash scripts/download_assets.sh "$COMET_ENV" "$COMET_STORAGE/appworld" --model
source scripts/activate_runtime.sh gpu
```

For AppWorld-only testing, use `appworld` instead of `gpu`, and omit `--model`.
For an isolated CPU environment, use `cpu`; it installs `uv.lock` without CUDA or
AppWorld. All three profiles require uv 0.13.0 and select Python 3.12. Use a
separate environment for each checkout and profile. Setup records its owner and
lock hashes in `.comet-runtime.json`, marks incomplete setup, and refuses to
modify an unmanaged environment or one owned by another checkout. Existing
legacy environments remain usable with their original source; choose a new path
for this workflow. Rerunning setup for the same owner/profile synchronizes its
locks and repairs an interrupted installation. Do not run setup while that
environment is executing a job. Changed locks require setup again.

For a repair test alongside an active job, use a new checkout and environment,
leaving the active source, runtime, outputs, and dependent jobs unchanged. Set
`UV_LINK_MODE=copy` before setup when package files must be independently writable;
verify that representative installed files have different inodes from the active
environment. Reuse model snapshots and caches, and audit the extra environment
against workspace storage before retaining it.

Check and experiment launchers verify this marker, the selected Python, and the
installed COMET source location before executing. They clear `PYTHONPATH` so a
stale override cannot select a different checkout. Source edits in the same
checkout remain editable and are captured in evidence; commit them before model
comparisons. These checks supplement the engine's pinned-source/patch validation.
The setup script retrieves AppWorld's Git LFS bundles at the pinned commit, checks
their SHA256 and size against the repository pointers, and installs the bundled
applications. Pydantic 2.12.5 is pinned because AppWorld's datetime schema patch is
incompatible with the newer `match_type` signature. Downloading the data is
a separate explicit step. `APPWORLD_ROOT` identifies this data directory at runtime.
Do not use `uv run` with its automatic project synchronization inside the GPU
environment: invoke that environment's `comet`, `python`, and `pytest` directly.

`dependencies.lock.json` records source, model, tokenizer, and benchmark data
versions. `infra/requirements/appworld.lock` and `gpu.lock` fix transitive runtime
versions for Linux x86_64/Python 3.12. The GPU setup applies
`patches/minisgl-comet.patch` to the pinned engine checkout in ignored `vendor/`.
It refuses a different revision or unrecognized existing edits. Preserve the patch,
resolved dependency list, and source revision with run artifacts.

The model path is the Hugging Face snapshot directory ending in
`b968826d9c46dd6066d109eabc6255188de91218`, not its parent model directory.
Both model and tokenizer use that revision. Model downloading and loading are
outside experimental budgets; environment resets and task execution are inside.

To intentionally regenerate runtime locks on Linux, use uv 0.13.0:

```sh
uv pip compile infra/requirements/appworld.in --python-version 3.12 \
  --python-platform x86_64-manylinux_2_28 -o infra/requirements/appworld.lock
uv pip compile infra/requirements/gpu.in --python-version 3.12 \
  --python-platform x86_64-manylinux_2_28 -o infra/requirements/gpu.lock
```

Commit and revalidate changed locks before running a new experiment version.

## Insomnia

The [cluster guide](https://columbiauniversity.atlassian.net/wiki/spaces/rcs/pages/62145124/Insomnia+HPC+Cluster+User+Documentation)
requires computational work on allocated compute nodes. Noninteractive SSH sessions
may omit the scheduler configuration exported by a login shell:

```sh
ssh insomnia
export SLURM_CONF=/etc/slurm/slurm.conf
sacctmgr -nP show assoc user="$USER" format=Account,Partition,QOS
sinfo -o '%P %a %l %G %D'
```

Choose an account and partition from the associations and current scheduler
inventory available to you. Verify the allocated GPU before running a job.
For a selected research device, set `engine.device_name` to its exact reported
name and qualify it using [hardware qualification](experimental-hardware.md).
Unqualified checks use integration mode and remain outside final comparisons. Keep dated hardware and validation observations in
[records/](records/README.md), omitting account-specific access details.

Store datasets, weights, environments, and runs in the account's project storage.
The [storage guide](https://columbiauniversity.atlassian.net/wiki/spaces/rcs/pages/62145132/Insomnia+-+Storage)
documents a 50GB home quota and no automatic backups. Keep source checkouts small,
and copy completed run records to durable storage.

The launcher sources `scripts/runtime_caches.sh` before importing GPU libraries.
It places AppWorld, Hugging Face, uv, Triton, PyTorch, CUDA, FlashInfer, and TVM-FFI caches
under `COMET_STORAGE/cache`. Source the same file before standalone GPU preflight
commands. Triton otherwise writes to its own home-directory cache even when the
model and FlashInfer caches are redirected. Check project-storage quotas for both
bytes and file count, plus free blocks and inodes, before long runs. Many small
compiler files can exhaust a file quota while byte capacity remains available.
Filesystem-wide free space does not establish that an account has quota.
Shared teaching storage also needs to remain small enough for other class users,
even when the filesystem has capacity. Keep one pinned copy of each needed model,
reuse the same uv cache across managed profiles, and measure the workspace as a
whole with `du -xch --max-depth=1 /path/to/workspace`. Linux uv environments
normally hard-link cached packages; summing separate per-directory `du` invocations
can count the same blocks repeatedly. Check inode usage as well as bytes. Audit
large directory trees in a CPU allocation. Remove only identified rebuildable
caches or superseded environments after jobs finish; preserve source, locks,
model revisions, and unique run/checkpoint evidence. Never prune an active runtime
or another contributor's files.
The launcher checks create/write/fsync/rename in every cache directory before
model loading; this catches current write failures, not quota exhaustion later
in a run. Existing caches are not removed or migrated.

Setup and checks also have Slurm entry points. Submit setup on an allocated CPU
node; request a GPU only for GPU checks. Choose the scheduler account, partitions,
and time limits explicitly. Use absolute paths, and ensure `uv` is on the
submitted `PATH`. For example, after exporting `COMET_REPO`, `COMET_STORAGE`,
and the scheduler variables below:

```sh
export COMET_ENV="$COMET_STORAGE/environments/my-checkout-cpu"
export COMET_CHECK_OUTPUT="$COMET_STORAGE/validation/my-unique-cpu-check"
mkdir -p "$COMET_STORAGE/logs"
setup_job=$(sbatch --parsable --account="$COMET_SLURM_ACCOUNT" \
  --partition="$COMET_CPU_PARTITION" --time=00:15:00 \
  --output="$COMET_STORAGE/logs/%x-%j.log" infra/slurm/setup.sh cpu)
sbatch --dependency="afterok:$setup_job" --account="$COMET_SLURM_ACCOUNT" \
  --partition="$COMET_CPU_PARTITION" --time=00:10:00 \
  --output="$COMET_STORAGE/logs/%x-%j.log" infra/slurm/check.sh cpu
```

Repeat with a new environment and `appworld` profile for live CPU API checks;
set `COMET_APPWORLD_ROOT` to the installed data. For `gpu`, set that root and
`COMET_MODEL_PATH` to the pinned Qwen3-8B snapshot, then request `--gres=gpu:1`
from a suitable GPU partition for `check.sh gpu`. Setup itself needs no GPU.
Use the same profile for setup and checks; GPU checks include the CPU, numerical,
and AppWorld suites. See [validation.md](validation.md) for optional capacity and
process-interruption checks. Model trials use `COMET_MODEL` instead of
`COMET_MODEL_PATH`; both must point to the matching pinned snapshot.

The wrappers pass Slurm's allocated CPU count to each job step. This accommodates
sites that increase CPUs to satisfy memory-per-CPU limits. Check `sacct` for job
exit codes and keep failed logs. A dependency that failed never validates the
next job; cancel its pending dependents and submit a new check output directory
when retrying. Single-GPU engine instances use separate file rendezvous stores,
so independent jobs do not compete for a fixed distributed port.

The launch script takes explicit settings, with no settled research budget hidden
in scheduler defaults:

```sh
export COMET_REPO=/path/to/your/checkout
export COMET_STORAGE=/path/to/project/storage/comet
export COMET_ENV="$COMET_STORAGE/environments/my-checkout-gpu"
export COMET_CONFIG="$COMET_REPO/configs/your-version.json"
export COMET_RUN="$COMET_STORAGE/runs/your-unique-run-id"
export COMET_MODEL="$COMET_STORAGE/cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218"
export COMET_INTEGRATION_SMOKE=1
export COMET_SLURM_ACCOUNT=your-slurm-account
export COMET_SLURM_PARTITION=your-gpu-partition
mkdir -p "$COMET_STORAGE/logs"
sbatch --account="$COMET_SLURM_ACCOUNT" --partition="$COMET_SLURM_PARTITION" \
  --gres=gpu:1 --time=00:30:00 \
  --output="$COMET_STORAGE/logs/%x-%j.log" infra/slurm/run.sh
```

This generic GPU request is suitable only for explicitly configured infrastructure
smokes. Final evaluation must unset `COMET_INTEGRATION_SMOKE` and select and verify
the exact qualified GPU model recorded in `engine.device_name`. Legacy configs
without that field retain their original A100 80GB requirement.
The scheduler time limit is a job ceiling; the shared task budget is enforced by
COMET's configuration and runner. Set `COMET_RESUME=1` to request a compatible
resume into the same run directory. It must retain prior attempt and budget usage.
Slurm requeue or preemption must never start a fresh budget under the same run ID.
The Slurm wrappers disable automatic requeue and append scheduler logs. This
prevents a reclaimed GPU allocation from silently rerunning a fresh launch or
truncating its failure log. For a deliberate resume, keep the original checkout,
environment, configuration and output directory, set `COMET_RESUME=1`, and request
the original GPU model explicitly. Installed runtime and GPU metadata must still
match. An interrupted attempt consumes its reserved cell budget and remains a
failure; completed cells are skipped. For multi-configuration jobs, resume each
existing run separately before starting an uncreated run, then score only after
every execution is terminal. Checks need a fresh evidence directory after failure.
The same requeue and log flags should be used by site-specific batch wrappers.

`COMET_APPWORLD_ROOT` can override the default `$COMET_STORAGE/appworld`.
`CUDA_HOME` defaults to `/usr/local/cuda`; an explicit value also controls the
toolkit added to `PATH`.

The shared `scripts/run_experiment.sh` launcher preserves the submitted config, Git revision/diff, dependency
list, GPU information, cache destinations, storage capacity/inodes, and scheduler allocation in a new directory under `launch/`
for every invocation. Commit source
changes before research runs; an untracked-file list is not a backup of those files.
The shared runner records the experiment manifest and trajectories separately.

## Google Cloud

`infra/gcp/instance.sh` prints a repeatable launch command by default and provisions
only with `--apply`. It requires explicit project, zone, immutable image resource,
disk capacity, VM name, and maximum runtime.

The [A2 Ultra specification](https://docs.cloud.google.com/compute/docs/gpus/)
identifies `a2-ultragpu-1g` as one A100 80GB GPU. Choose a driver/CUDA-ready Linux
image, pin its exact resource, and confirm quota and cost before applying the plan.
The script [limits VM runtime](https://docs.cloud.google.com/compute/docs/instances/limit-vm-runtime)
and requests automatic stopping. Persistent disks still incur storage charges
after a VM stops. Keep experiment records on persistent disks or object storage,
not local SSD, and remove resources when no longer needed.

```sh
export GCP_PROJECT=your-project GCP_ZONE=your-zone GCP_VM=comet-your-run
export GCP_IMAGE=projects/your-image-project/global/images/your-pinned-image
export GCP_MAX_DURATION=4h GCP_DISK_GB=200
bash infra/gcp/instance.sh
```

After provisioning an approved plan, copy or clone the exact COMET revision and use
the same runtime setup, asset download, and `COMET_*` variables as on Insomnia.
Run `bash infra/gcp/run.sh` to use the shared experiment launcher without Slurm.
Run `source scripts/activate_runtime.sh gpu` and `comet doctor --gpu` before the pilot. The pilot must set measured budgets and
freeze settings before any test evaluation; the VM lifetime is not that budget.
