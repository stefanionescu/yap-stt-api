#!/usr/bin/env bash
set -euo pipefail

if [[ -f logs/server.pid ]]; then
  PID=$(cat logs/server.pid)
  kill "$PID" || true
  rm -f logs/server.pid
  echo "Stopped PID $PID"
else
  echo "No PID file found"
fi
