#!/usr/bin/env bash
#SBATCH --job-name=comet-partition
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --no-requeue
#SBATCH --open-mode=append
#SBATCH --signal=B:TERM@60

set -euo pipefail
: "${COMET_REPO:?Set COMET_REPO}"
: "${COMET_PARTITIONS:?Set COMET_PARTITIONS to the generated partition directory}"
: "${COMET_STUDY_RUN:?Set COMET_STUDY_RUN to a new study output directory}"
: "${COMET_EXPECTED_COMMIT:?Pin the submitted source commit}"
: "${SLURM_ARRAY_TASK_ID:?Submit this wrapper as a job array}"
[[ "$(git -C "$COMET_REPO" rev-parse HEAD)" == "$COMET_EXPECTED_COMMIT" ]]
git -C "$COMET_REPO" diff --quiet HEAD
printf -v partition_name 'part-%02d' "$SLURM_ARRAY_TASK_ID"
export COMET_CONFIG="$COMET_PARTITIONS/$partition_name.json"
export COMET_RUN="$COMET_STUDY_RUN/$partition_name"
exec srun --cpus-per-task="${SLURM_CPUS_PER_TASK:-1}" --kill-on-bad-exit=1 \
    bash "$COMET_REPO/scripts/run_experiment.sh"
