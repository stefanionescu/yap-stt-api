#!/usr/bin/env bash
set -euo pipefail

mkdir -p /models /models/trt_cache
bash scripts/fetch_int8_model.sh
exec uvicorn src.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --loop uvloop --http httptools
