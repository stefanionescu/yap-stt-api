#!/usr/bin/env bash
set -euo pipefail

export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8000}
export PARAKEET_NUM_LANES=${PARAKEET_NUM_LANES:-2}

mkdir -p logs logs/metrics

if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
fi

if command -v uvicorn >/dev/null 2>&1; then
  exec uvicorn src.server:app --host "$HOST" --port "$PORT" --loop uvloop --http httptools
else
  exec python -m uvicorn src.server:app --host "$HOST" --port "$PORT" --loop uvloop --http httptools
fi
