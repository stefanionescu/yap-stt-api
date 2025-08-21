#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs logs/metrics
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Installing..." | tee logs/server.log
  bash scripts/install_docker.sh | tee -a logs/server.log
fi
# Ensure daemon running
if ! docker info >/dev/null 2>&1; then
  echo "Starting Docker daemon (dockerd)..." | tee -a logs/server.log
  nohup dockerd --host=unix:///var/run/docker.sock --storage-driver=overlay2 \
    >> logs/server.log 2>&1 & echo $! > logs/dockerd.pid
  for i in {1..20}; do
    if docker info >/dev/null 2>&1; then echo "Daemon ready" | tee -a logs/server.log; break; fi
    sleep 1
  done
fi
nohup docker compose up --build > logs/server.log 2>&1 & echo $! > logs/server.pid
echo "Started with PID $(cat logs/server.pid). Logs: logs/server.log"
