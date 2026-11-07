#!/usr/bin/env bash
#SBATCH --job-name=comet-setup
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
set -euo pipefail
: "${COMET_REPO:?Set COMET_REPO to the checkout directory}"
: "${COMET_ENV:?Set COMET_ENV to a new or matching managed environment}"
exec srun --cpus-per-task="${SLURM_CPUS_PER_TASK:-1}" --kill-on-bad-exit=1 bash "$COMET_REPO/scripts/setup_runtime.sh" "${1:?Pass cpu, appworld, or gpu}" "$COMET_ENV"
