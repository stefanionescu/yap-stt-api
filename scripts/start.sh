#!/usr/bin/env bash
set -euo pipefail

source scripts/env.sh || true

mkdir -p logs logs/metrics

use_docker=${USE_DOCKER:-1}
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Installing..."
  bash scripts/install_docker.sh
fi
docker compose up --build
