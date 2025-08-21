#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs logs/metrics
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Installing..." | tee logs/server.log
  bash scripts/install_docker.sh | tee -a logs/server.log
fi
nohup docker compose up --build > logs/server.log 2>&1 & echo $! > logs/server.pid
echo "Started with PID $(cat logs/server.pid). Logs: logs/server.log"
