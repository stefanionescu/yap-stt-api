#!/usr/bin/env bash
set -euo pipefail

source scripts/env.sh || true

mkdir -p logs logs/metrics

use_docker=${USE_DOCKER:-1}
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Installing..."
  bash scripts/install_docker.sh
fi

# Ensure Docker daemon is running (non-systemd environments)
if ! docker info >/dev/null 2>&1; then
  echo "Starting Docker daemon (dockerd) in background..."
  mkdir -p logs
  nohup dockerd --host=unix:///var/run/docker.sock --storage-driver=overlay2 \
    > logs/dockerd.log 2>&1 & echo $! > logs/dockerd.pid
  # Wait for daemon to be ready
  for i in {1..20}; do
    if docker info >/dev/null 2>&1; then
      echo "Docker daemon is ready."
      break
    fi
    sleep 1
  done
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon failed to start. Check logs/dockerd.log" >&2
    exit 1
  fi
fi

docker compose up --build
