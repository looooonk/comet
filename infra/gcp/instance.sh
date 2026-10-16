#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT:?Set the GCP project ID}"
: "${GCP_ZONE:?Select a zone with A2 Ultra quota and capacity}"
: "${GCP_VM:?Choose a unique VM name}"
: "${GCP_IMAGE:?Set an exact image resource, not an image family}"
: "${GCP_MAX_DURATION:?Set a maximum VM lifetime, for example 4h}"
: "${GCP_DISK_GB:?Set persistent boot disk capacity for assets and results}"

command=(gcloud compute instances create "$GCP_VM"
    --project="$GCP_PROJECT" --zone="$GCP_ZONE"
    --machine-type=a2-ultragpu-1g --image="$GCP_IMAGE"
    --boot-disk-size="${GCP_DISK_GB}GB" --boot-disk-type=pd-balanced
    --maintenance-policy=TERMINATE --no-restart-on-failure
    --max-run-duration="$GCP_MAX_DURATION" --instance-termination-action=STOP
    --no-service-account --no-scopes --labels=project=comet)
printf '%q ' "${command[@]}"
printf '\n'
if [[ "${1:-}" == --apply ]]; then
    "${command[@]}"
elif [[ "${1:-}" != '' ]]; then
    printf 'Usage: instance.sh [--apply]\n' >&2
    exit 2
fi
