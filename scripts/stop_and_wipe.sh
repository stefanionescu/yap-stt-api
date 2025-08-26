#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"

# Kill server if running
if [ -f "$ROOT/server.pid" ]; then
  PID=$(cat "$ROOT/server.pid" || true)
  if [ -n "${PID:-}" ] && ps -p "$PID" > /dev/null 2>&1; then
    echo "[stop] Killing PID $PID"
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$ROOT/server.pid"
fi

# Wipe everything created by bootstrap
echo "[wipe] Removing venv, repos, models, logs, TRT cache"
rm -rf "$ROOT/.venv" \
       "$ROOT/repos" \
       "$ROOT/models" \
       "$ROOT/logs" \
       "$ROOT/trt_cache"

echo "[wipe] Done. Re-run ./scripts/bootstrap.sh to rebuild."


