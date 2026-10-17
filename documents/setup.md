# Setup and execution

COMET has a small CPU environment for configuration, policies, accounting, analysis,
and unit tests. Model inference uses a separate Linux x86_64 Python 3.12 environment.
Every method uses the same pinned Mini-SGLang engine. Nothing in the CPU tests
establishes that the CUDA or AppWorld integration works.

## Local development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```sh
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen pytest -m 'not gpu and not appworld'
uv run --frozen comet --help
```

`uv.lock` fixes the CPU dependencies. CI uses Python 3.11 and uv 0.13.0;
`.python-version` selects Python 3.12 locally. Core COMET requires only the standard
library. CUDA kernels are deliberately absent from this environment.

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
bash scripts/setup_runtime.sh gpu "$COMET_STORAGE/venv"
bash scripts/download_assets.sh "$COMET_STORAGE/venv" "$COMET_STORAGE/appworld" --model
```

For AppWorld-only testing, use `appworld` instead of `gpu`, and omit `--model`.
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
Non-A100 validation requires integration mode and must not enter A100 research
comparisons. Keep dated hardware and validation observations in
[records/](records/README.md), omitting account-specific access details.

Store datasets, weights, environments, and runs in the account's project storage.
The [storage guide](https://columbiauniversity.atlassian.net/wiki/spaces/rcs/pages/62145132/Insomnia+-+Storage)
documents a 50GB home quota and no automatic backups. Keep source checkouts small,
and copy completed run records to durable storage.

The launcher sources `scripts/runtime_caches.sh` before importing GPU libraries.
It places Hugging Face, uv, Triton, PyTorch, CUDA, FlashInfer, and TVM-FFI caches
under `COMET_STORAGE/cache`. Source the same file before standalone GPU preflight
commands. Triton otherwise writes to its own home-directory cache even when the
model and FlashInfer caches are redirected. Check project-storage quota, free
blocks, and free inodes before long runs; filesystem-wide free space does not
establish that an account has quota. The launcher checks create/write/fsync/rename
in every cache directory before model loading; this catches current write
failures, not quota exhaustion later in a run. Existing caches are not removed
or migrated.

The launch script takes explicit settings, with no settled research budget hidden
in scheduler defaults:

```sh
export COMET_REPO="$HOME/comet"
export COMET_STORAGE=/path/to/project/storage/comet
export COMET_ENV="$COMET_STORAGE/venv"
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
smokes. Final evaluation must unset `COMET_INTEGRATION_SMOKE`, select and verify
the prescribed A100 80GB hardware.
The scheduler time limit is a job ceiling; the shared task budget is enforced by
COMET's configuration and runner. Set `COMET_RESUME=1` to request a compatible
resume into the same run directory. It must retain prior attempt and budget usage.
Slurm requeue or preemption must never start a fresh budget under the same run ID.

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
Run `comet doctor --gpu` before the pilot. The pilot must set measured budgets and
freeze settings before any test evaluation; the VM lifetime is not that budget.
