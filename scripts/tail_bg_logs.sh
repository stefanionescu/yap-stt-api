#!/usr/bin/env bash
set -euo pipefail

LOG_FILE=${LOG_FILE:-logs/server.log}

if [[ ! -f "$LOG_FILE" ]]; then
  echo "Log file not found: $LOG_FILE" >&2
  exit 1
fi

echo "Tailing $LOG_FILE (Ctrl-C to stop)"
tail -F "$LOG_FILE"
