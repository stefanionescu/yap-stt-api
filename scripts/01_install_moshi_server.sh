#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"
echo "[01] Installing moshi-server (CUDA ${CUDA_MM})…"

# Ensure versioned CUDA is first
export PATH="${CUDA_PREFIX}/bin:$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
export CUDA_HOME="${CUDA_PREFIX}"; export CUDA_PATH="${CUDA_PREFIX}"; export CUDA_ROOT="${CUDA_PREFIX}"

if ! command -v nvcc >/dev/null 2>&1; then
  echo "[01] ERROR: nvcc not found in ${CUDA_PREFIX}/bin — check 00_prereqs.sh output." >&2
  exit 1
fi

if ! command -v moshi-server >/dev/null 2>&1; then
  cargo install --features cuda moshi-server
else
  echo "[01] moshi-server already installed."
fi

echo "[01] moshi-server: $(command -v moshi-server)"