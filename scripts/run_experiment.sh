#!/usr/bin/env bash
set -euo pipefail
: "${COMET_REPO:?Set COMET_REPO to the checkout directory}"
: "${COMET_ENV:?Set COMET_ENV to the GPU virtual environment}"
: "${COMET_STORAGE:?Set COMET_STORAGE to persistent project storage}"
: "${COMET_CONFIG:?Set COMET_CONFIG to a versioned configuration file}"
: "${COMET_RUN:?Set COMET_RUN to a unique output directory}"
: "${COMET_MODEL:?Set COMET_MODEL to the pinned local model snapshot}"

export PATH="$COMET_ENV/bin:/usr/local/cuda/bin:$PATH"
export CUDA_HOME=${CUDA_HOME:-/usr/local/cuda}
export HF_HOME="$COMET_STORAGE/cache/huggingface"
export UV_CACHE_DIR="$COMET_STORAGE/cache/uv"
export FLASHINFER_WORKSPACE_BASE="$COMET_STORAGE/cache/flashinfer"
export TVM_FFI_CACHE_DIR="$COMET_STORAGE/cache/tvm-ffi"
export APPWORLD_ROOT="$COMET_STORAGE/appworld"
export PYTHONUNBUFFERED=1
cd "$COMET_REPO"
launch_dir="$COMET_RUN/launch/$(date -u +%Y%m%dT%H%M%SZ)-${SLURM_JOB_ID:-$$}"
mkdir -p "$launch_dir"
cp "$COMET_CONFIG" "$launch_dir/submitted-config.json"
git rev-parse HEAD > "$launch_dir/commit.txt"
git diff --binary HEAD > "$launch_dir/changes.patch"
git ls-files --others --exclude-standard > "$launch_dir/untracked-files.txt"
nvidia-smi -q > "$launch_dir/gpu.txt"
python -m pip freeze > "$launch_dir/packages.txt" 2>/dev/null || \
    uv pip freeze --python "$COMET_ENV/bin/python" > "$launch_dir/packages.txt"
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    scontrol show job "$SLURM_JOB_ID" > "$launch_dir/slurm.txt"
fi
args=(run "$COMET_CONFIG" --output "$COMET_RUN" --model-path "$COMET_MODEL"
    --appworld-root "$APPWORLD_ROOT")
if [[ "${COMET_RESUME:-0}" == 1 ]]; then args+=(--resume); fi
if [[ "${COMET_INTEGRATION_SMOKE:-0}" == 1 ]]; then args+=(--integration-smoke); fi
exec comet "${args[@]}"
