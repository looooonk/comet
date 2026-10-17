#!/usr/bin/env bash
set -euo pipefail

runtime_env=${1:?Usage: download_assets.sh environment-path appworld-root [--model|--model-14b]}
appworld_root=${2:?AppWorld data directory required}
if [[ -d "$appworld_root/data" ]]; then
    [[ "$(cat "$appworld_root/data/version.txt")" == 0.2.0 ]] || {
        printf 'Existing AppWorld data has a different version; choose a new root.\n' >&2
        exit 1
    }
else
    "$runtime_env/bin/appworld" download data --version 0.2.0 --root "$appworld_root"
    [[ "$(cat "$appworld_root/data/version.txt")" == 0.2.0 ]]
fi
if [[ "${3:-}" == --model ]]; then
    "$runtime_env/bin/hf" download Qwen/Qwen3-8B \
        --revision b968826d9c46dd6066d109eabc6255188de91218
elif [[ "${3:-}" == --model-14b ]]; then
    "$runtime_env/bin/hf" download Qwen/Qwen3-14B \
        --revision 40c069824f4251a91eefaf281ebe4c544efd3e18
elif [[ -n "${3:-}" ]]; then
    printf 'Unknown asset option: %s\n' "$3" >&2
    exit 1
fi
