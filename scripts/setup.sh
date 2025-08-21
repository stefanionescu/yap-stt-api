#!/usr/bin/env bash
set -euo pipefail

PY=${PY:-python3}
VENV=.venv

$PY -m venv $VENV
source $VENV/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Load default environment
source scripts/env.sh

if [[ "${PARAKEET_USE_DIRECT_ONNX:-0}" == "1" && -n "${PARAKEET_MODEL_DIR:-}" && "${AUTO_FETCH_INT8:-1}" == "1" ]]; then
  echo "Direct ONNX enabled and model dir set. Attempting to fetch INT8 artifacts..."
  bash scripts/fetch_int8.sh || echo "WARN: fetch_int8.sh failed; continuing without INT8"
fi

echo "Venv ready. Activate with: source $VENV/bin/activate"
