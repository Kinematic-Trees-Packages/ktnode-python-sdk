#!/usr/bin/env bash
set -euo pipefail

split_paths() {
  local value=${1:-}
  IFS=':' read -r -a __paths <<<"$value"
  for p in "${__paths[@]}"; do
    [[ -n "$p" ]] && printf '%s\n' "$p"
  done
}

find_in_path_list() {
  local env_name=$1
  local rel=$2
  local value=${!env_name:-}
  while IFS= read -r root; do
    [[ -e "$root/$rel" ]] && return 0
  done < <(split_paths "$value")
  return 1
}

require_kt_node_build_env() {
  local missing=0
  if ! find_in_path_list CPATH kt_robotics.h; then
    echo "kt-node header kt_robotics.h not found in CPATH; run through KTM so kt-node includePaths are composed" >&2
    missing=1
  fi
  if ! find_in_path_list LIBRARY_PATH libkt_node.so && ! find_in_path_list LIBRARY_PATH libkt_node.a && ! find_in_path_list LD_LIBRARY_PATH libkt_node.so; then
    echo "kt-node library not found in LIBRARY_PATH/LD_LIBRARY_PATH; run through KTM so kt-node libraryPaths are composed" >&2
    missing=1
  fi
  if [[ $missing -ne 0 ]]; then
    exit 2
  fi
}

cflags_from_cpath() {
  while IFS= read -r root; do printf ' -I%s' "$root"; done < <(split_paths "${CPATH:-}")
}

ldflags_from_library_path() {
  while IFS= read -r root; do printf ' -L%s' "$root"; done < <(split_paths "${LIBRARY_PATH:-}")
}

require_kt_node_build_env
python3 -m py_compile src/{{KTM_CREATE_MODULE_NAME}}/*.py examples/basic.py tests/test_smoke.py
PYTHONPATH=src python3 examples/basic.py
PYTHONPATH=src python3 -m pytest -q tests || PYTHONPATH=src python3 - <<'PY'
from {{KTM_CREATE_MODULE_NAME}} import Robot
print(Robot(native_required=True).status())
PY
echo "Python kt-node smoke passed"
