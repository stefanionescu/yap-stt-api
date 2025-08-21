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

# Wire the TensorRT and cuDNN wheel lib dirs at runtime so ORT TRT-EP can load
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

# Preflight: ensure local model dir (if set) has required artifacts before starting
if [[ -n "${PARAKEET_MODEL_DIR:-}" ]]; then
  if [[ ! -d "${PARAKEET_MODEL_DIR}" ]]; then
    echo "Model dir missing: ${PARAKEET_MODEL_DIR}" >&2
    exit 1
  fi
  for f in encoder-model.onnx decoder_joint-model.onnx vocab.txt config.json; do
    if [[ ! -f "${PARAKEET_MODEL_DIR}/${f}" ]]; then
      echo "Missing ${f} in ${PARAKEET_MODEL_DIR}" >&2
      exit 1
    fi
  done
  ls -lh "${PARAKEET_MODEL_DIR}"/encoder-model.onnx* "${PARAKEET_MODEL_DIR}"/decoder_joint-model.onnx "${PARAKEET_MODEL_DIR}"/vocab.txt "${PARAKEET_MODEL_DIR}"/config.json || true
fi

exec python -m uvicorn src.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --loop uvloop --http httptools
