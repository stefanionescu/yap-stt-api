#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"
echo "[01] Installing moshi-server (CUDA ${CUDA_MM})…"

# Ensure versioned CUDA is first
export PATH="${CUDA_PREFIX}/bin:$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

if ! command -v nvcc >/dev/null 2>&1; then
  echo "[01] ERROR: nvcc not found in ${CUDA_PREFIX}/bin — check 00_prereqs.sh output." >&2
  exit 1
fi

# CUDA sanity checks before build
echo "[01] CUDA sanity checks (targeting CUDA ${CUDA_MM}):"
echo "  Driver says CUDA: $(nvidia-smi | awk -F'CUDA Version: ' '/CUDA Version/ {print $2}' | awk '{print $1}' | head -n1)"
echo "  nvcc: $(nvcc --version | sed -n 's/^.*release //p' | head -n1)"
echo "  nvcc path: $(which nvcc)"
echo "  Using CUDA prefix: ${CUDA_PREFIX}"
echo "  LD_LIBRARY_PATH: ${LD_LIBRARY_PATH}"
echo "  CUDA_COMPUTE_CAP: ${CUDA_COMPUTE_CAP}"

# Check for conflicting CUDA installations
if [ -L "/usr/local/cuda" ]; then
  CUDA_SYMLINK_TARGET=$(readlink -f /usr/local/cuda)
  if [[ "${CUDA_SYMLINK_TARGET}" != "${CUDA_PREFIX}" ]]; then
    echo "  ⚠️  WARNING: /usr/local/cuda -> ${CUDA_SYMLINK_TARGET} (not our ${CUDA_PREFIX})"
  else
    echo "  ✓ /usr/local/cuda -> ${CUDA_SYMLINK_TARGET} (correct)"
  fi
fi

echo "  NVRTC chosen: $(ldconfig -p | awk '/libnvrtc\\.so/{print $NF; exit}')"
NVRTC_PATH=$(ldconfig -p | awk '/libnvrtc\\.so/{print $NF; exit}')
if [[ "${NVRTC_PATH}" == "${CUDA_PREFIX}"* ]]; then
  echo "  ✓ NVRTC from our CUDA version"
else
  echo "  ⚠️  WARNING: NVRTC from different CUDA version! Failing fast."
  exit 2
fi

# Optional: show all CUDA libs the loader will see first
echo "  CUDA libraries loader precedence:"
ldconfig -p | grep -E 'lib(cudart|nvrtc|cuda)\.so' | sort -u | sed 's/^/    /'

# Verify NVRTC can load (fail fast on driver/toolkit mismatch)
python3 - <<'PY'
import ctypes, sys, os
try:
    lib = ctypes.CDLL("libnvrtc.so")
    print("OK: libnvrtc loaded successfully")
except OSError as e:
    print("ERROR: could not load NVRTC:", e)
    sys.exit(3)
PY

if ! command -v moshi-server >/dev/null 2>&1; then
  echo "[01] Installing moshi-server with CUDA ${CUDA_MM}, compute cap ${CUDA_COMPUTE_CAP}..."
  cargo install --features cuda moshi-server
else
  echo "[01] moshi-server already installed."
fi

echo "[01] moshi-server: $(command -v moshi-server)"