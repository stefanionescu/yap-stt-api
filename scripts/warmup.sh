#!/usr/bin/env bash
set -euo pipefail

FILE=${1:-}
if [[ -z "$FILE" ]]; then
  echo "Usage: $0 /path/to/audio.wav"
  exit 1
fi

python3 test/warmup.py --file "$FILE" --url "${URL:-http://127.0.0.1:8000}"
