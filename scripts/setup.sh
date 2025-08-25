#!/usr/bin/env bash
set -euo pipefail

PY=${PY:-python3}
VENV=.venv

$PY -m venv $VENV
source $VENV/bin/activate
pip install --upgrade pip
# Install PyTorch CUDA wheels first
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 || true
# Remove possible conflicting package named 'cuda' that can shadow cuda-python
pip uninstall -y cuda || true
# Ensure cuda-python is present (provides cuda.cudart)
pip install -U cuda-python
pip install -r requirements.txt

echo "Venv ready. Activate with: source $VENV/bin/activate"

# Ensure ffmpeg is present on Ubuntu containers (for pydub/ffmpeg decoding)
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y || true
    apt-get install -y ffmpeg || true
  fi
fi

# Install CUDA runtime (libcudart) to remove cudart warning if on apt-based system
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  # Prefer CUDA 12 where available; fall back to generic libcudart
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
    # Last resort: CUDA meta-runtime if available
    apt-get install -y nvidia-cuda-runtime || true
  fi
fi
