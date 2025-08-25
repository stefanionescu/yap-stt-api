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
  pip install -r requirements.txt
fi

# Launch using venv python to ensure correct interpreter
nohup python -m src.server > logs/server.log 2>&1 & echo $! > logs/server.pid
echo "Started with PID $(cat logs/server.pid). Logs: logs/server.log"
