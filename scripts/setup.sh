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

if [[ -n "${PARAKEET_MODEL_DIR:-}" && "${AUTO_FETCH_FP32:-0}" == "1" ]]; then
  echo "Model dir set. Attempting to fetch FP32 artifacts..."
  bash scripts/fetch_fp32.sh || echo "WARN: fetch_fp32.sh failed; continuing without FP32"
fi

if [[ "${INSTALL_TRT:-0}" == "1" ]]; then
  echo "INSTALL_TRT=1 set. Attempting to install TensorRT runtime via apt..."
  bash scripts/install_trt.sh || echo "WARN: install_trt.sh failed; TRT EP may be unavailable"
fi

echo "Venv ready. Activate with: source $VENV/bin/activate"
