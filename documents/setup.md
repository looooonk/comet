# Setup

Use Python 3.12 and uv 0.13.0. COMET has a small CPU environment for development
and analysis, and a Linux CUDA environment for Qwen3.5-9B and AppWorld.
[Dependency pins](../dependencies.lock.json), `uv.lock` and
`infra/requirements/*.lock` define the reproducible environments.

## Local development

From the checkout root:

```sh
export COMET_REPO="$PWD"
export COMET_ENV="$COMET_REPO/.venv-cpu"
bash scripts/setup_runtime.sh cpu "$COMET_ENV"
export COMET_CHECK_OUTPUT="$COMET_REPO/artifacts/checks/cpu-unique-id"
bash scripts/run_checks.sh cpu
source scripts/activate_runtime.sh cpu
comet --help
```

Use a new `COMET_CHECK_OUTPUT` for each check. The CPU suite covers configuration,
accounting, policies, scoring and analysis; it does not establish live GPU or
AppWorld correctness. For figures, install the pinned plotting extra in this CPU
profile with `uv pip install --python "$COMET_ENV/bin/python" -e '.[plots]'`.

## Qwen3.5-9B and AppWorld

Use a Linux x86_64 compute node with a CUDA toolkit, C/C++ compiler and matching
Python development headers. The hybrid profile pins Transformers 5.22.2,
PyTorch 2.9.1 and the AgentKV selectors. Setup retrieves and verifies AppWorld's
pinned application bundles; the asset command downloads its data and model.

```sh
export COMET_REPO="$PWD"
export COMET_STORAGE=/path/to/persistent/project/storage
export COMET_ENV="$COMET_STORAGE/environments/my-checkout-hybrid"
export COMET_APPWORLD_ROOT="$COMET_STORAGE/appworld"
source scripts/runtime_caches.sh
bash scripts/setup_runtime.sh hybrid "$COMET_ENV"
bash scripts/download_assets.sh "$COMET_ENV" "$COMET_APPWORLD_ROOT" --model-9b-hybrid
source scripts/activate_runtime.sh hybrid
export COMET_MODEL_PATH="$HF_HOME/hub/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a"
```

Runtime probes, model loading and GPU checks belong inside a GPU allocation.
Verify Triton's driver before expensive checks:

```sh
python -c 'from triton.runtime import driver; print(driver.active.get_current_target())'
comet doctor --gpu
```

The target must be CUDA; FLA can otherwise cache an unusable CPU fallback.
See the [backend contract](hybrid-backend.md) and
[validation guide](validation/README.md) for the live checks and explicit caps.
Use `appworld` for AppWorld-only checks. The retained `gpu` profile serves the
legacy Mini-SGLang backend and requires its matching model; it is not the 9B
runtime. The [engine reference](reference/engine.md) describes that path.

## Runtime ownership and storage

Keep one owned environment per checkout/profile. Setup records its owner and
lock hashes in `.comet-runtime.json` and refuses unmanaged or differently owned
environments. Rerun setup after lock changes or interrupted installation, only
when no job uses that environment. Launchers verify the profile, locks and installed
source. Source the activation script before direct commands; do not use `uv run`
to synchronize a GPU environment.

Reuse persistent caches under `COMET_STORAGE/cache`. The launchers set these
before GPU imports and probe cache writes before loading. Audit both storage
bytes and inode quotas; filesystem free space alone does not establish account
quota. Keep datasets, weights, complete runs and environments outside the source
tree. Remove superseded copies after jobs end, preserving unique results and
other contributors' files.

On slow shared storage, set `COMET_LOCAL_MODEL=1` to stage the pinned snapshot in
`SLURM_TMPDIR`, or an explicit job-local `TMPDIR`. Allow at least 21 GB of scratch
for 9B. Staging is recorded as model initialization, outside task timing.

A ready runtime can also be packed once in a CPU allocation:

```sh
python scripts/stage_runtime.py pack "$COMET_ENV" "$COMET_STORAGE/cache/hybrid-runtime.tar"
export COMET_RUNTIME_ARCHIVE="$COMET_STORAGE/cache/hybrid-runtime.tar"
```

Activation unpacks it to job-local scratch, preserving ownership and lock checks.
Allow about 8 GB more scratch; rebuild the archive after runtime changes. This
reuses installed packages without resolving a new environment.

## Insomnia

Run computation on allocated nodes. Set the scheduler configuration when a
noninteractive session does not inherit it:

```sh
export SLURM_CONF=/etc/slurm/slurm.conf
sacctmgr -nP show assoc user="$USER" format=Account,Partition,QOS
sinfo -o '%P %a %l %G %D'
```

Choose an authorized account, partition and GPU from the current inventory.
For a short focused check, after setting the runtime variables above:

```sh
export COMET_CHECK_OUTPUT="$COMET_STORAGE/validation/hybrid-unique-id"
export PYTEST_ADDOPTS='tests/test_hybrid.py tests/test_rkv_memory.py'
mkdir -p "$COMET_STORAGE/logs"
sbatch --account="$COMET_SLURM_ACCOUNT" --partition="$COMET_GPU_PARTITION" \
  --gres=gpu:1 --cpus-per-task=2 --mem=12G --time=00:10:00 \
  --output="$COMET_STORAGE/logs/%x-%j.log" infra/slurm/check.sh hybrid
```

This generic GPU request is an integration check. Research runs must request and
verify the exact qualified device in their configuration. Use `infra/slurm/setup.sh`
for setup on a CPU allocation and `infra/slurm/run.sh` for experiments with the
variables in the [workflow](experiments.md). The wrappers honor allocated CPU
counts, disable automatic requeue and preserve logs. Check `sacct` for the actual
exit status; cancel pending dependents after failed prerequisites.

The scheduler's time limit bounds the job, not individual task budgets. Resume
requires the original source, runtime, device, configuration and output directory;
set `COMET_RESUME=1`. Completed cells stay complete and interrupted attempts retain
their budget charges. Keep each check's evidence directory distinct.

## Google Cloud

`infra/gcp/run.sh` uses the same experiment launcher and runtime variables as
Slurm. Qualify the selected device and preserve comparison caps and budgets.
Confirm current quota, cost and the [remaining project allowance](records/qwen9b/cloud-ledger.json)
before provisioning.

`infra/gcp/instance.sh` is the retained A100 80GB provisioning helper: it prints
a command by default and creates a VM only with `--apply`. It requires explicit
project, zone, immutable image, VM name, disk size and maximum lifetime. Its
termination action stops the VM; disks remain until explicitly removed. Other
qualified hardware uses its corresponding provisioning route.

For bounded queued studies, see [cloud sessions](reference/cloud-sessions.md).
Both routes use the same runner, scorer and analysis; neither grants extra
experimental time or retries.
