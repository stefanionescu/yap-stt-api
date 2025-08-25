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
  # Install torch/torchaudio before NeMo to ensure correct CUDA wheels
  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 || true
  # Remove conflicting 'cuda' package and ensure cuda-python present
  pip uninstall -y cuda || true
  pip install -U cuda-python
  pip install -r requirements.txt
  # Ensure ffmpeg is present on Ubuntu containers (for pydub/ffmpeg decoding)
  if ! command -v ffmpeg >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -y || true
      apt-get install -y ffmpeg || true
    fi
  fi
  # Install libcudart to enable CUDA runtime APIs when available
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y || true
    if apt-cache show libcudart12 >/dev/null 2>&1; then
      apt-get install -y libcudart12 || true
    elif apt-cache show nvidia-cuda-runtime-cu12 >/dev/null 2>&1; then
      apt-get install -y nvidia-cuda-runtime-cu12 || true
    elif apt-cache show libcudart11.0 >/dev/null 2>&1; then
      apt-get install -y libcudart11.0 || true
    elif apt-cache show libcudart11.5 >/dev/null 2>&1; then
      apt-get install -y libcudart11.5 || true
    else
      apt-get install -y nvidia-cuda-runtime || true
    fi
  fi
else
  source .venv/bin/activate
  # Keep cuda-python present and avoid conflicting 'cuda' package
  pip uninstall -y cuda || true
  pip install -U cuda-python
  pip install -r requirements.txt
  # Best-effort ensure libcudart
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y || true
    if apt-cache show libcudart12 >/dev/null 2>&1; then
      apt-get install -y libcudart12 || true
    elif apt-cache show nvidia-cuda-runtime-cu12 >/dev/null 2>&1; then
      apt-get install -y nvidia-cuda-runtime-cu12 || true
    elif apt-cache show libcudart11.0 >/dev/null 2>&1; then
      apt-get install -y libcudart11.0 || true
    elif apt-cache show libcudart11.5 >/dev/null 2>&1; then
      apt-get install -y libcudart11.5 || true
    else
      apt-get install -y nvidia-cuda-runtime || true
    fi
  fi
fi

exec python -m src.server
