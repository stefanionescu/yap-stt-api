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

NVRTC_PATH=$(ldconfig -p | awk '/libnvrtc\\.so/{print $NF; exit}')
CUDA_SYMLINK_TARGET=$(readlink -f /usr/local/cuda 2>/dev/null || true)
echo "  NVRTC chosen: ${NVRTC_PATH:-<not found in ldconfig cache>}"

# Accept either the explicit versioned prefix, or the /usr/local/cuda symlink if it points to our prefix
if [[ -n "${NVRTC_PATH}" ]]; then
  if [[ "${NVRTC_PATH}" == "${CUDA_PREFIX}"* ]] || { [[ "${NVRTC_PATH}" == "/usr/local/cuda"* ]] && [[ "${CUDA_SYMLINK_TARGET}" == "${CUDA_PREFIX}" ]]; }; then
    echo "  ✓ NVRTC resolves to CUDA ${CUDA_MM}"
  else
    echo "  ⚠️  NVRTC path does not match ${CUDA_PREFIX}. Attempting to refresh ldconfig..."
    echo "${CUDA_PREFIX}/lib64" > /etc/ld.so.conf.d/cuda-our-version.conf
    echo "${CUDA_PREFIX}/targets/x86_64-linux/lib" >> /etc/ld.so.conf.d/cuda-our-version.conf
    ldconfig
    NVRTC_PATH=$(ldconfig -p | awk '/libnvrtc\\.so/{print $NF; exit}')
    echo "  NVRTC after refresh: ${NVRTC_PATH:-<not found>}"
    if [[ "${NVRTC_PATH}" == "${CUDA_PREFIX}"* ]] || { [[ "${NVRTC_PATH}" == "/usr/local/cuda"* ]] && [[ "${CUDA_SYMLINK_TARGET}" == "${CUDA_PREFIX}" ]]; }; then
      echo "  ✓ NVRTC now resolves to CUDA ${CUDA_MM}"
    else
      echo "  ✗ ERROR: NVRTC from different CUDA version after refresh."
      exit 2
    fi
  fi
else
  echo "  ⚠️  NVRTC not present in ldconfig cache; proceeding with LD_LIBRARY_PATH overrides"
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

if ! command -v yap-server >/dev/null 2>&1 && ! command -v moshi-server >/dev/null 2>&1; then
  echo "[01] Building yap-server (moshi-server) from local workspace with CUDA ${CUDA_MM}, compute cap ${CUDA_COMPUTE_CAP}..."
  
  # Set cudarc NVRTC path to ensure it uses the correct CUDA version
  export CUDARC_NVRTC_PATH="${CUDA_PREFIX}/lib64/libnvrtc.so"
  
  pushd "${ROOT_DIR}/../server"
  cargo build --release --features cuda -p moshi-server
  install -m 0755 target/release/yap-server /usr/local/bin/yap-server
  ln -sf /usr/local/bin/yap-server /usr/local/bin/moshi-server
  popd
else
  echo "[01] Server binary already installed. Ensuring yap-server symlink..."
  if command -v yap-server >/dev/null 2>&1; then
    ln -sf "$(command -v yap-server)" /usr/local/bin/moshi-server || true
  fi
fi

echo "[01] yap-server:    $(command -v yap-server || echo <not found>)"
echo "[01] moshi-server: $(command -v moshi-server || echo <not found>)"