#!/usr/bin/env bash
set -euo pipefail

# Configure TRT wheel lib dir into LD_LIBRARY_PATH if present
TRT_LIB_DIR=$(python3 - <<'PY'
import os, sysconfig
site = sysconfig.get_paths().get('purelib') or ''
p = os.path.join(site, 'tensorrt', 'lib')
print(p if os.path.isdir(p) else '')
PY
)
if [[ -n "$TRT_LIB_DIR" ]]; then
  export LD_LIBRARY_PATH="$TRT_LIB_DIR:${LD_LIBRARY_PATH:-}"
fi

# Ensure model dir exists
mkdir -p "$PARAKEET_MODEL_DIR" "$TRT_ENGINE_CACHE"

# Optionally fetch INT8 artifacts on first run
if [[ "${AUTO_FETCH_INT8:-1}" == "1" ]]; then
  bash scripts/fetch_int8.sh || echo "WARN: fetch_int8 failed; continuing"
fi

exec uvicorn src.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --loop uvloop --http httptools

