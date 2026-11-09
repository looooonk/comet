#!/usr/bin/env bash
set -euo pipefail
profile=${1:?Usage: run_checks.sh cpu|appworld|gpu [--cpu-only]}
case "$profile" in cpu|appworld|gpu) ;; *) exit 2 ;; esac
cpu_only=false
if [[ $# -gt 1 ]]; then
    if [[ $# != 2 || "$profile" != gpu || "$2" != --cpu-only ]]; then
        echo '--cpu-only is supported only with the gpu runtime profile' >&2
        exit 2
    fi
    cpu_only=true
fi
: "${COMET_REPO:?Set COMET_REPO to the checkout directory}"
: "${COMET_ENV:?Set COMET_ENV to the matching managed environment}"
: "${COMET_CHECK_OUTPUT:?Set COMET_CHECK_OUTPUT to a new evidence directory}"
source "$COMET_REPO/scripts/activate_runtime.sh" "$profile"
cd "$COMET_REPO"
if [[ "$cpu_only" == true ]]; then
    export CUDA_VISIBLE_DEVICES=''
    unset COMET_RUN_GPU_TESTS COMET_GPU_EVIDENCE COMET_GPU_MEMORY_EVIDENCE
    unset COMET_GPU_CAPACITY_EVIDENCE COMET_GPU_SAMPLING_EVIDENCE
elif [[ "$profile" == gpu ]]; then
    : "${COMET_MODEL_PATH:?Set COMET_MODEL_PATH to the pinned model snapshot}"
    export COMET_RUN_GPU_TESTS=1
    export COMET_GPU_EVIDENCE="$COMET_CHECK_OUTPUT/gpu.json"
    export COMET_GPU_MEMORY_EVIDENCE="$COMET_CHECK_OUTPUT/memory.json"
    export COMET_GPU_CAPACITY_EVIDENCE="$COMET_CHECK_OUTPUT/capacity.json"
    export COMET_GPU_SAMPLING_EVIDENCE="$COMET_CHECK_OUTPUT/sampling.json"
fi
mkdir -p "$(dirname "$COMET_CHECK_OUTPUT")"
mkdir "$COMET_CHECK_OUTPUT"
trap 'status=$?; printf "%s\n" "$status" > "$COMET_CHECK_OUTPUT/exit-status.txt"' EXIT
printf 'profile=%s\ncpu_only=%s\n' "$profile" "$cpu_only" > "$COMET_CHECK_OUTPUT/mode.txt"
git rev-parse HEAD > "$COMET_CHECK_OUTPUT/commit.txt"
git diff --binary HEAD > "$COMET_CHECK_OUTPUT/changes.patch"
git ls-files --others --exclude-standard > "$COMET_CHECK_OUTPUT/untracked-files.txt"
cp "$COMET_ENV/.comet-runtime.json" "$COMET_CHECK_OUTPUT/runtime.json"
python - <<'PYTHON' > "$COMET_CHECK_OUTPUT/packages.txt"
import hashlib
import os
from pathlib import Path

from comet.artifacts import provenance, write_json

root = Path(os.environ["COMET_REPO"])
record = provenance()
for pattern in ("scripts/*.sh", "tests/*.py", "infra/slurm/*.sh", "pyproject.toml", "uv.lock"):
    record["source_hashes"].update({
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.glob(pattern)
    })
write_json(Path(os.environ["COMET_CHECK_OUTPUT"]) / "source.json", record)
for name, version in sorted(record["installed_packages"].items()):
    print(f"{name}=={version}")
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
        if [[ "$cpu_only" == true ]]; then
            if command -v ruff >/dev/null 2>&1; then
                ruff check .
                printf 'passed\n' > "$COMET_CHECK_OUTPUT/lint-status.txt"
            else
                printf 'skipped: ruff is unavailable in the GPU runtime\n' > "$COMET_CHECK_OUTPUT/lint-status.txt"
            fi
            for script in scripts/*.sh infra/slurm/*.sh infra/gcp/*.sh; do bash -n "$script"; done
            selection='not gpu and not appworld'
        else
            nvidia-smi -q > "$COMET_CHECK_OUTPUT/gpu-device.txt"
            selection=''
        fi
        ;;
esac
printf 'selection=%s\n' "$selection" >> "$COMET_CHECK_OUTPUT/mode.txt"
python -m pytest -m "$selection" --junitxml="$COMET_CHECK_OUTPUT/pytest.xml" -ra
