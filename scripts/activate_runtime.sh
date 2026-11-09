#!/usr/bin/env bash
# Source this file before direct runtime commands; launchers use it automatically.
comet_runtime_profile=${1:?Usage: source scripts/activate_runtime.sh cpu|appworld|gpu|hybrid}
case "$comet_runtime_profile" in cpu|appworld|gpu|hybrid) ;; *) return 2 ;; esac
: "${COMET_REPO:?Set COMET_REPO to the checkout directory}"
: "${COMET_ENV:?Set COMET_ENV to the matching managed environment}"
export PATH="$COMET_ENV/bin:$PATH"
export PYTHONUNBUFFERED=1
unset PYTHONPATH
"$COMET_ENV/bin/python" "$COMET_REPO/src/comet/runtime.py" verify \
    "$COMET_REPO" "$COMET_ENV" "$comet_runtime_profile" || return $?
if [[ "$comet_runtime_profile" != cpu ]]; then
    : "${COMET_STORAGE:?Set COMET_STORAGE to persistent project storage}"
fi
if [[ -n "${COMET_STORAGE:-}" ]]; then
    source "$COMET_REPO/scripts/runtime_caches.sh" || return $?
fi
if [[ "$comet_runtime_profile" != cpu ]]; then
    export COMET_APPWORLD_ROOT=${COMET_APPWORLD_ROOT:-"$COMET_STORAGE/appworld"}
    export APPWORLD_ROOT="$COMET_APPWORLD_ROOT"
fi
if [[ "$comet_runtime_profile" == gpu ]]; then
    export CUDA_HOME=${CUDA_HOME:-/usr/local/cuda}
    export PATH="$CUDA_HOME/bin:$PATH"
fi
unset comet_runtime_profile
