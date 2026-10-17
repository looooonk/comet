#!/usr/bin/env bash
set -euo pipefail

profile=${1:?Usage: setup_runtime.sh appworld|gpu [environment-path]}
case "$profile" in appworld|gpu) ;; *) exit 2 ;; esac
repo=$(cd "$(dirname "$0")/.." && pwd)
runtime_env=${2:-"$repo/.venv-$profile"}
cd "$repo"
if [[ -n "${COMET_STORAGE:-}" ]]; then source scripts/runtime_caches.sh; fi
uv venv --allow-existing --python 3.12 "$runtime_env"
uv pip sync --python "$runtime_env/bin/python" "infra/requirements/$profile.lock"
uv pip install --python "$runtime_env/bin/python" --no-deps -e .

if [[ "$profile" == gpu ]]; then
    engine_revision=254c57bc84e4a7895159ba1062bd46c83626f511
    if [[ ! -d vendor/minisgl ]]; then
        mkdir -p vendor
        git clone https://github.com/LiuTaowen-Tony/kv-management-minisgl.git vendor/minisgl
        git -C vendor/minisgl checkout --detach "$engine_revision"
    fi
    [[ "$(git -C vendor/minisgl rev-parse HEAD)" == "$engine_revision" ]]
    patch_file="$repo/patches/minisgl-comet.patch"
    if git -C vendor/minisgl apply --reverse --check "$patch_file" 2>/dev/null; then
        :
    else
        [[ -z "$(git -C vendor/minisgl status --porcelain)" ]]
        git -C vendor/minisgl apply --check "$patch_file"
        git -C vendor/minisgl apply "$patch_file"
    fi
    uv pip install --python "$runtime_env/bin/python" --no-deps -e vendor/minisgl
fi
"$runtime_env/bin/python" scripts/fetch_appworld_bundles.py
"$runtime_env/bin/appworld" install
uv pip check --python "$runtime_env/bin/python"
printf 'Environment ready: %s\n' "$runtime_env"
