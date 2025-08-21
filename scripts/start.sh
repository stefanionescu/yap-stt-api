#!/usr/bin/env bash
set -euo pipefail

source scripts/env.sh || true

mkdir -p logs logs/metrics

# Wire the tensorrt wheel's lib dir at runtime so ORT TRT-EP can load
TRT_LIB_DIR=$(python3 - <<'PY'
import os, sysconfig
site = sysconfig.get_paths().get('purelib') or ''
p = os.path.join(site, 'tensorrt', 'lib')
print(p if os.path.isdir(p) else '')
PY
)
if [[ -n "${TRT_LIB_DIR}" ]]; then
  export LD_LIBRARY_PATH="${TRT_LIB_DIR}:${LD_LIBRARY_PATH:-}"
fi

CUDNN_LIB_DIR=$(python3 - <<'PY'
import os, sysconfig
site = sysconfig.get_paths().get('purelib') or ''
p = os.path.join(site, 'nvidia', 'cudnn', 'lib')
print(p if os.path.isdir(p) else '')
PY
)
if [[ -n "${CUDNN_LIB_DIR}" ]]; then
  export LD_LIBRARY_PATH="${CUDNN_LIB_DIR}:${LD_LIBRARY_PATH}"
fi

if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
fi

exec uvicorn src.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --loop uvloop --http httptools
