#!/usr/bin/env bash
set -euo pipefail
: "${COMET_REPO:?}"
: "${OUTPUT_DIR:?}"
stage=${COMET_CLOUD_STAGE:-/mnt/disks/stage}
queue="$stage/queue"
reports="$stage/reports"
mkdir -p "$queue" "$reports"
started=$SECONDS
printf 'worker_ready\n'
while (( SECONDS - started < 24300 )); do
    [[ ! -f "$queue/STOP" ]] || break
    found=0
    for ready in "$queue"/*/READY; do
        [[ -f "$ready" ]] || continue
        plan=$(basename "$(dirname "$ready")")
        [[ "$plan" =~ ^[0-9][0-9]-[a-z0-9-]+$ ]] || continue
        [[ ! -d "$OUTPUT_DIR/$plan" ]] || continue
        found=1
        export COMET_RESULTS_DIR="$OUTPUT_DIR/$plan"
        export COMET_PLAN_DIR="$COMET_RESULTS_DIR/plan"
        mkdir -p "$COMET_PLAN_DIR" "$reports/$plan"
        cp -R "$queue/$plan/." "$COMET_PLAN_DIR/"
        printf 'plan_started %s\n' "$plan"
        status=0
        bash "$COMET_PLAN_DIR/run.sh" > "$COMET_RESULTS_DIR/worker.log" 2>&1 || status=$?
        printf '%s\n' "$status" > "$COMET_RESULTS_DIR/exit-status.txt"
        tar -C "$OUTPUT_DIR" -cf "$OUTPUT_DIR/.plan-output.tar" "$plan"
        cp "$OUTPUT_DIR/.plan-output.tar" "$reports/$plan/artifacts.tar"
        rm "$OUTPUT_DIR/.plan-output.tar"
        cp "$COMET_RESULTS_DIR/exit-status.txt" "$reports/$plan/exit-status.txt"
        printf 'plan_finished %s exit=%s\n' "$plan" "$status"
    done
    (( found )) || sleep 10
done
printf 'worker_finished\n'
