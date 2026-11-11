#!/usr/bin/env bash
#SBATCH --job-name=comet-score
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --no-requeue
#SBATCH --open-mode=append

set -euo pipefail
: "${COMET_REPO:?Set COMET_REPO}"
: "${COMET_EXPECTED_COMMIT:?Pin the submitted source commit}"
: "${COMET_PARTITIONS:?Set COMET_PARTITIONS}"
: "${COMET_STUDY_RUN:?Set COMET_STUDY_RUN}"
: "${COMET_PLOT_ENV:?Set COMET_PLOT_ENV to a managed CPU runtime with plotting support}"
[[ "$(git -C "$COMET_REPO" rev-parse HEAD)" == "$COMET_EXPECTED_COMMIT" ]]
git -C "$COMET_REPO" diff --quiet HEAD
source "$COMET_REPO/scripts/activate_runtime.sh" "${COMET_RUNTIME_PROFILE:-hybrid}"
srun --cpus-per-task="${SLURM_CPUS_PER_TASK:-1}" --kill-on-bad-exit=1 \
    python "$COMET_REPO/scripts/score_study.py" "$COMET_PARTITIONS" "$COMET_STUDY_RUN"
unset COMET_RUNTIME_ARCHIVE
export COMET_ENV="$COMET_PLOT_ENV"
source "$COMET_REPO/scripts/activate_runtime.sh" cpu
for extension in png pdf; do
    comet plot-aggressivity "$COMET_STUDY_RUN/analysis.json" \
        --output "$COMET_STUDY_RUN/aggressivity.$extension"
    comet plot-resources "$COMET_STUDY_RUN/analysis.json" --policy never \
        --output "$COMET_STUDY_RUN/resources.$extension"
done
