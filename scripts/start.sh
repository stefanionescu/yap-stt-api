#!/usr/bin/env bash
set -euo pipefail

source scripts/env.sh || true

mkdir -p logs logs/metrics

# Wire the TensorRT and cuDNN wheel lib dirs at runtime so ORT TRT-EP can load
TRT_LIB_DIR=$(python3 - <<'PY'
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

CUDNN_LIB_DIR=$(python3 - <<'PY'
import os, sysconfig
site = sysconfig.get_paths().get('purelib') or ''
p = os.path.join(site, 'nvidia', 'cudnn', 'lib')
print(p if os.path.isdir(p) else '')
PY
)
if [[ -n "${CUDNN_LIB_DIR}" ]]; then export LD_LIBRARY_PATH="${CUDNN_LIB_DIR}:${LD_LIBRARY_PATH}"; fi

if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
fi

if command -v uvicorn >/dev/null 2>&1; then
  exec uvicorn src.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --loop uvloop --http httptools
else
  exec python3 -m uvicorn src.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --loop uvloop --http httptools
fi
