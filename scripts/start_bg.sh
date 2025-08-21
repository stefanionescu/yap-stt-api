#!/usr/bin/env bash
set -euo pipefail
source scripts/env.sh || true
mkdir -p logs logs/metrics

# Ensure venv and deps
PY=${PY:-python3}
if [[ ! -f .venv/bin/activate ]]; then
  ${PY} -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
else
  source .venv/bin/activate
  python -c "import uvicorn" 2>/dev/null || pip install -r requirements.txt
fi

# Wire TRT libs (wheel) using the venv python
TRT_LIB_DIR=$(python - <<'PY'
import os, glob
try:
    import tensorrt
    base = os.path.dirname(tensorrt.__file__)
    for sub in ("lib", ".", ".."):
        cand = os.path.abspath(os.path.join(base, sub))
        matches = glob.glob(os.path.join(cand, "libnvinfer.so*"))
        if matches:
            print(os.path.dirname(matches[0])); raise SystemExit
    matches = glob.glob(os.path.join(base, "**", "libnvinfer.so*"), recursive=True)
    if matches:
        print(os.path.dirname(matches[0])); raise SystemExit
except Exception:
    pass
print("")
PY
)
if [[ -n "${TRT_LIB_DIR}" ]]; then export LD_LIBRARY_PATH="${TRT_LIB_DIR}:${LD_LIBRARY_PATH:-}"; fi
CUDNN_LIB_DIR=$(python - <<'PY'
import os, sysconfig
site = sysconfig.get_paths().get('purelib') or ''
p = os.path.join(site, 'nvidia', 'cudnn', 'lib')
print(p if os.path.isdir(p) else '')
PY
)
if [[ -n "${CUDNN_LIB_DIR}" ]]; then export LD_LIBRARY_PATH="${CUDNN_LIB_DIR}:${LD_LIBRARY_PATH}"; fi

# Launch using venv python to ensure correct interpreter
nohup python -m uvicorn src.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --loop uvloop --http httptools \
  > logs/server.log 2>&1 & echo $! > logs/server.pid
echo "Started with PID $(cat logs/server.pid). Logs: logs/server.log"
