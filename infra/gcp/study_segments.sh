#!/usr/bin/env bash

run_segments() {
    export COMET_CONFIG="$COMET_PLAN_DIR/$1" COMET_RUN="$COMET_RESULTS_DIR/$2"
    export COMET_MAX_CELLS="$3"
    for ((segment=1; segment<=$4; segment++)); do
        if [[ -f "$COMET_RUN/manifest.json" ]]; then export COMET_RESUME=1; else unset COMET_RESUME; fi
        bash scripts/run_experiment.sh
        tar -C "$OUTPUT_DIR" -cf "$OUTPUT_DIR/.closed-segment.tar" "$(basename "$COMET_RESULTS_DIR")/$2"
        mkdir -p "${COMET_CLOUD_STAGE:-/mnt/disks/stage}/checkpoints"
        cp "$OUTPUT_DIR/.closed-segment.tar" "${COMET_CLOUD_STAGE:-/mnt/disks/stage}/checkpoints/$(basename "$COMET_RESULTS_DIR")-$2-segment-$segment.tar"
        rm "$OUTPUT_DIR/.closed-segment.tar"
        if python -c 'import json,os,sys; sys.exit(json.load(open(os.environ["COMET_RUN"]+"/manifest.json"))["status"] != "completed")'; then
            comet evaluate "$COMET_RUN"
            comet analyze "$COMET_RUN" --output "$COMET_RUN/analysis.json"
            break
        fi
    done
    unset COMET_MAX_CELLS COMET_RESUME
}
export -f run_segments
