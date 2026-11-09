#!/usr/bin/env bash
set -euo pipefail
: "${COMET_REPO:?Set COMET_REPO}"
: "${COMET_CHECK_OUTPUT:?Set COMET_CHECK_OUTPUT to a new qualification directory}"
: "${COMET_RESUME_CONFIG:?Set COMET_RESUME_CONFIG to a train/dev resume fixture}"
qualification_root=$COMET_CHECK_OUTPUT
mkdir -p "$(dirname "$qualification_root")"
mkdir "$qualification_root"
trap 'status=$?; printf "%s\n" "$status" > "$qualification_root/exit-status.txt"' EXIT
export COMET_CHECK_OUTPUT="$qualification_root/inprocess"
export PYTEST_ADDOPTS='tests/test_hybrid.py tests/test_hybrid_appworld.py tests/test_rkv_memory.py tests/test_appworld_integration.py tests/test_environment_warmup.py'
bash "$COMET_REPO/scripts/run_checks.sh" hybrid
# CLI children need the full cap; the earlier CUDA-owning pytest process must exit first.
export COMET_CHECK_OUTPUT="$qualification_root/process-resume"
export COMET_RESUME_ARTIFACT_DIR="$qualification_root/resume"
export PYTEST_ADDOPTS='tests/test_resume_integration.py'
bash "$COMET_REPO/scripts/run_checks.sh" hybrid
