#!/usr/bin/env bash
set -euo pipefail
echo "[01] Installing moshi-server (CUDA)…"

# Make sure CUDA & Rust are on PATH for this shell
# Auto-detect CUDA path (RunPod images may use versioned paths)
if [ -d "/usr/local/cuda/bin" ]; then
  export PATH="/usr/local/cuda/bin:$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
  export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
  export CUDA_PATH="${CUDA_PATH:-/usr/local/cuda}"
  export CUDA_ROOT="${CUDA_ROOT:-/usr/local/cuda}"
elif [ -d "/usr/local/cuda-12/bin" ]; then
  export PATH="/usr/local/cuda-12/bin:$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
  export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-12}"
  export CUDA_PATH="${CUDA_PATH:-/usr/local/cuda-12}"
  export CUDA_ROOT="${CUDA_ROOT:-/usr/local/cuda-12}"
else
  export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
fi

# If you ever need to pin a CUDA major for cudarc, uncomment:
# export CUDARC_CUDA_VERSION=12

if ! command -v nvcc >/dev/null 2>&1; then
  echo "[01] ERROR: nvcc still not found; check 00_prereqs.sh output." >&2
  exit 1
fi

if ! command -v moshi-server >/dev/null 2>&1; then
  # --features cuda triggers cudarc; now that nvcc exists, this will compile.
  cargo install --features cuda moshi-server
else
  echo "[01] moshi-server already installed, skipping."
fi

echo "[01] moshi-server location: $(command -v moshi-server)"