#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs logs/metrics

# Wire TRT libs (wheel) for background run
TRT_LIB_DIR=$(python3 - <<'PY'
import os, sysconfig
site = sysconfig.get_paths().get('purelib') or ''
p = os.path.join(site, 'tensorrt', 'lib')
print(p if os.path.isdir(p) else '')
PY
)
if [[ -n "${TRT_LIB_DIR}" ]]; then export LD_LIBRARY_PATH="${TRT_LIB_DIR}:${LD_LIBRARY_PATH:-}"; fi
CUDNN_LIB_DIR=$(python3 - <<'PY'
import os, sysconfig
site = sysconfig.get_paths().get('purelib') or ''
p = os.path.join(site, 'nvidia', 'cudnn', 'lib')
print(p if os.path.isdir(p) else '')
PY
)
if [[ -n "${CUDNN_LIB_DIR}" ]]; then export LD_LIBRARY_PATH="${CUDNN_LIB_DIR}:${LD_LIBRARY_PATH}"; fi

if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi

nohup python -m uvicorn src.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --loop uvloop --http httptools \
  > logs/server.log 2>&1 & echo $! > logs/server.pid
echo "Started with PID $(cat logs/server.pid). Logs: logs/server.log"
