#!/usr/bin/env bash
set -euo pipefail
export COMET_REPO=${COMET_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}
exec bash "$COMET_REPO/scripts/run_experiment.sh"
