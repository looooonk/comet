#!/usr/bin/env bash
#SBATCH --job-name=comet
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --signal=B:TERM@60

set -euo pipefail
: "${COMET_REPO:?Set COMET_REPO to the checkout directory}"
exec srun --cpus-per-task="${SLURM_CPUS_PER_TASK:-1}" --kill-on-bad-exit=1 bash "$COMET_REPO/scripts/run_experiment.sh"
