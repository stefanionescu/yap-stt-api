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
  if command -v rootlesskit >/dev/null 2>&1 && command -v dockerd-rootless-setuptool.sh >/dev/null 2>&1; then
    echo "Starting rootless Docker..." | tee -a logs/server.log
    export XDG_RUNTIME_DIR=/run/user/$(id -u)
    mkdir -p "$XDG_RUNTIME_DIR"
    dockerd-rootless-setuptool.sh install || true
    nohup dockerd-rootless.sh >> logs/server.log 2>&1 & echo $! > logs/dockerd.pid
  else
    nohup dockerd --host=unix:///var/run/docker.sock --storage-driver=overlay2 \
      >> logs/server.log 2>&1 & echo $! > logs/dockerd.pid
  fi
  for i in {1..20}; do
    if docker info >/dev/null 2>&1; then echo "Daemon ready" | tee -a logs/server.log; break; fi
    sleep 1
  done
fi
nohup docker compose up --build > logs/server.log 2>&1 & echo $! > logs/server.pid
echo "Started with PID $(cat logs/server.pid). Logs: logs/server.log"
