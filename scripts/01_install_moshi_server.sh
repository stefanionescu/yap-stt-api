#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"
echo "[01] Installing moshi-server (CUDA)…"

export PATH="/usr/local/cuda/bin:$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
export CUDA_HOME CUDA_PATH CUDA_ROOT

if ! command -v nvcc >/dev/null 2>&1; then
  echo "[01] ERROR: nvcc missing"; exit 1
fi

if ! command -v moshi-server >/dev/null 2>&1; then
  cargo install --features cuda moshi-server
else
  echo "[01] moshi-server already installed."
fi

echo "[01] moshi-server: $(command -v moshi-server)"