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
else
  source .venv/bin/activate
  python -c "import uvicorn" 2>/dev/null || pip install -r requirements.txt
fi

exec python -m uvicorn src.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --loop uvloop --http httptools
