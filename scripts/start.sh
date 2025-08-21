#!/usr/bin/env bash
set -euo pipefail

source scripts/env.sh

mkdir -p logs logs/metrics

if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
fi

if command -v uvicorn >/dev/null 2>&1; then
  exec uvicorn src.server:app --host "$HOST" --port "$PORT" --loop uvloop --http httptools
else
  exec python -m uvicorn src.server:app --host "$HOST" --port "$PORT" --loop uvloop --http httptools
fi
