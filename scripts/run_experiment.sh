#!/usr/bin/env bash
set -euo pipefail
: "${COMET_REPO:?Set COMET_REPO to the checkout directory}"
: "${COMET_ENV:?Set COMET_ENV to the GPU virtual environment}"
: "${COMET_STORAGE:?Set COMET_STORAGE to persistent project storage}"
: "${COMET_CONFIG:?Set COMET_CONFIG to a versioned configuration file}"
: "${COMET_RUN:?Set COMET_RUN to a unique output directory}"
: "${COMET_MODEL:?Set COMET_MODEL to the pinned local model snapshot}"

source "$COMET_REPO/scripts/activate_runtime.sh" "${COMET_RUNTIME_PROFILE:-gpu}"
cd "$COMET_REPO"
launch_dir="$COMET_RUN/launch/$(date -u +%Y%m%dT%H%M%SZ)-${SLURM_JOB_ID:-$$}"
mkdir -p "$launch_dir"
for cache_name in XDG_CACHE_HOME APPWORLD_CACHE HF_HOME UV_CACHE_DIR TRITON_CACHE_DIR TORCH_HOME \
    TORCHINDUCTOR_CACHE_DIR TORCH_EXTENSIONS_DIR PYTORCH_KERNEL_CACHE_PATH \
    CUDA_CACHE_PATH FLASHINFER_WORKSPACE_BASE TVM_FFI_CACHE_DIR; do
    printf '%s=%s\n' "$cache_name" "${!cache_name}"
done > "$launch_dir/cache-environment.txt"
python - "$launch_dir/cache-environment.txt" <<'PY'
import os
import sys
import tempfile
from pathlib import Path

for line in Path(sys.argv[1]).read_text().splitlines():
    name, directory = line.split("=", 1)
    with tempfile.TemporaryDirectory(prefix=".comet-probe-", dir=directory) as probe:
        path = Path(probe) / "write"
        with path.open("wb") as stream:
            stream.write(b"comet" * 1024)
            stream.flush()
            os.fsync(stream.fileno())
        path.rename(Path(probe) / "renamed")
    print(f"Cache write probe passed: {name}")
PY
df -Pk "$COMET_STORAGE" > "$launch_dir/storage-blocks.txt"
df -Pi "$COMET_STORAGE" > "$launch_dir/storage-inodes.txt"
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
if [[ -n "${COMET_MAX_CELLS:-}" ]]; then args+=(--max-cells "$COMET_MAX_CELLS"); fi
if [[ "${COMET_INTEGRATION_SMOKE:-0}" == 1 ]]; then args+=(--integration-smoke); fi
exec comet "${args[@]}"
