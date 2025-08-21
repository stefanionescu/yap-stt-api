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

# Stop background dockerd if we started it
if [[ -f logs/dockerd.pid ]]; then
  DPID=$(cat logs/dockerd.pid)
  kill "$DPID" || true
  rm -f logs/dockerd.pid
fi
