#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs logs/metrics
bash scripts/start.sh > logs/server.log 2>&1 & echo $! > logs/server.pid
echo "Started with PID $(cat logs/server.pid). Logs: logs/server.log"
