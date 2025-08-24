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
  pip install -r requirements.txt
  # Ensure ffmpeg is present on Ubuntu containers (for pydub/ffmpeg decoding)
  if ! command -v ffmpeg >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -y || true
      apt-get install -y ffmpeg || true
    fi
  fi
else
  source .venv/bin/activate
  python -c "import uvicorn" 2>/dev/null || pip install -r requirements.txt
fi

exec python -m uvicorn src.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --loop uvloop --http httptools --timeout-keep-alive 120 --backlog 1024 \
  --ws-max-size "${WS_MAX_SIZE:-16777216}" --ws-ping-interval "${WS_PING_INTERVAL:-20}" --ws-ping-timeout "${WS_PING_TIMEOUT:-20}"
