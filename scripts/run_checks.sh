#!/usr/bin/env bash
set -euo pipefail
profile=${1:?Usage: run_checks.sh cpu|appworld|gpu}
case "$profile" in cpu|appworld|gpu) ;; *) exit 2 ;; esac
: "${COMET_REPO:?Set COMET_REPO to the checkout directory}"
: "${COMET_ENV:?Set COMET_ENV to the matching managed environment}"
: "${COMET_CHECK_OUTPUT:?Set COMET_CHECK_OUTPUT to a new evidence directory}"
export PATH="$COMET_ENV/bin:$PATH"
export PYTHONUNBUFFERED=1
unset PYTHONPATH
cd "$COMET_REPO"
python src/comet/runtime.py verify "$COMET_REPO" "$COMET_ENV" "$profile"
if [[ "$profile" != cpu ]]; then
    : "${COMET_STORAGE:?Set COMET_STORAGE to persistent project storage}"
    : "${COMET_APPWORLD_ROOT:?Set COMET_APPWORLD_ROOT to installed AppWorld data}"
    source scripts/runtime_caches.sh
fi
if [[ "$profile" == gpu ]]; then
    : "${COMET_MODEL_PATH:?Set COMET_MODEL_PATH to the pinned model snapshot}"
    export CUDA_HOME=${CUDA_HOME:-/usr/local/cuda}
    export PATH="$CUDA_HOME/bin:$PATH"
    export COMET_RUN_GPU_TESTS=1
    export COMET_GPU_EVIDENCE="$COMET_CHECK_OUTPUT/gpu.json"
    export COMET_GPU_MEMORY_EVIDENCE="$COMET_CHECK_OUTPUT/memory.json"
fi
mkdir -p "$(dirname "$COMET_CHECK_OUTPUT")"
mkdir "$COMET_CHECK_OUTPUT"
trap 'status=$?; printf "%s\n" "$status" > "$COMET_CHECK_OUTPUT/exit-status.txt"' EXIT
git rev-parse HEAD > "$COMET_CHECK_OUTPUT/commit.txt"
git diff --binary HEAD > "$COMET_CHECK_OUTPUT/changes.patch"
git ls-files --others --exclude-standard > "$COMET_CHECK_OUTPUT/untracked-files.txt"
cp "$COMET_ENV/.comet-runtime.json" "$COMET_CHECK_OUTPUT/runtime.json"
python - <<'PYTHON' > "$COMET_CHECK_OUTPUT/packages.txt"
import importlib.metadata
for package in sorted(importlib.metadata.distributions(), key=lambda p: p.metadata["Name"]):
    print(f"{package.metadata['Name']}=={package.version}")
PYTHON
if [[ -n "${SLURM_JOB_ID:-}" ]]; then scontrol show job "$SLURM_JOB_ID" > "$COMET_CHECK_OUTPUT/slurm.txt"; fi
case "$profile" in
    cpu)
        ruff check .
        for script in scripts/*.sh infra/slurm/*.sh infra/gcp/*.sh; do bash -n "$script"; done
        selection='not gpu and not appworld'
        ;;
    appworld) selection='appworld and not gpu' ;;
    gpu)
        nvidia-smi -q > "$COMET_CHECK_OUTPUT/gpu-device.txt"
        selection=''
        ;;
esac
python -m pytest -m "$selection" --junitxml="$COMET_CHECK_OUTPUT/pytest.xml" -ra
