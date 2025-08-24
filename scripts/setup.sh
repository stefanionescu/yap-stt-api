#!/usr/bin/env bash
set -euo pipefail

PY=${PY:-python3}
VENV=.venv

$PY -m venv $VENV
source $VENV/bin/activate
pip install --upgrade pip
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 || true
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
