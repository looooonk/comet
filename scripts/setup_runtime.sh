#!/usr/bin/env bash
set -euo pipefail

profile=${1:?Usage: setup_runtime.sh cpu|appworld|gpu [environment-path]}
case "$profile" in cpu|appworld|gpu) ;; *) exit 2 ;; esac
repo=$(cd "$(dirname "$0")/.." && pwd)
runtime_env=${2:-"$repo/.venv-$profile"}
cd "$repo"
unset PYTHONPATH
if [[ "$profile" != cpu ]]; then
    : "${COMET_STORAGE:?Set COMET_STORAGE to persistent project storage}"
fi
if [[ -n "${COMET_STORAGE:-}" ]]; then source scripts/runtime_caches.sh; fi
[[ "$(uv --version | cut -d ' ' -f 2)" == 0.13.0 ]] || { echo "Use uv 0.13.0" >&2; exit 2; }
python3 src/comet/runtime.py prepare "$repo" "$runtime_env" "$profile"
uv venv --allow-existing --python 3.12 "$runtime_env"
if [[ "$profile" == cpu ]]; then
    UV_PROJECT_ENVIRONMENT="$runtime_env" uv sync --frozen --python 3.12
else
    uv pip sync --python "$runtime_env/bin/python" "infra/requirements/$profile.lock"
    uv pip install --python "$runtime_env/bin/python" --no-deps -e .
fi

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
if [[ "$profile" != cpu ]]; then
    "$runtime_env/bin/python" scripts/fetch_appworld_bundles.py
    "$runtime_env/bin/appworld" install
fi
uv pip check --python "$runtime_env/bin/python"
"$runtime_env/bin/python" src/comet/runtime.py record "$repo" "$runtime_env" "$profile"
printf 'Environment ready: %s\n' "$runtime_env"
