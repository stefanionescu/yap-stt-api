# shellcheck shell=bash
set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${THIS_DIR}"
[ -f "${ROOT_DIR}/.env" ] || { [ -f "${ROOT_DIR}/../.env" ] && ROOT_DIR="${THIS_DIR}/.."; }

# Load .env if present
if [ -f "${ROOT_DIR}/.env" ]; then
  set -a; source "${ROOT_DIR}/.env"; set +a
fi

# Parse CUDA "max supported" from driver (e.g., 12.2)
detect_cuda_mm() {
  local mm
  mm="$(nvidia-smi 2>/dev/null | awk -F'CUDA Version: ' '/CUDA Version/ {print $2}' | awk '{print $1}' | head -n1)"
  # Fallback
  echo "${mm:-12.2}"
}

export HF_HOME="${HF_HOME:-/workspace/hf_cache}"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"
export YAP_ADDR="${YAP_ADDR:-0.0.0.0}"
export YAP_PORT="${YAP_PORT:-8000}"
export YAP_CLIENT_HOST="${YAP_CLIENT_HOST:-127.0.0.1}"
export YAP_PUBLIC_WS_URL="${YAP_PUBLIC_WS_URL:-}"
export YAP_LOG_DIR="${YAP_LOG_DIR:-/workspace/logs}"
export DSM_REPO_DIR="${DSM_REPO_DIR:-/workspace/delayed-streams-modeling}"
export YAP_CONFIG="${YAP_CONFIG:-${ROOT_DIR}/../server/config-stt-en_fr-hf.toml}"
export TMUX_SESSION="${TMUX_SESSION:-yap-stt}"
export SMOKETEST_RTF="${SMOKETEST_RTF:-1}"

# Always target CUDA 12.4 unless explicitly overridden
# If a newer CUDA is present on the image, 00_prereqs.sh will purge it and install 12.4
export CUDA_MM="${CUDA_MM:-12.4}"
export CUDA_MM_PKG="${CUDA_MM_PKG:-${CUDA_MM//./-}}" # e.g., "12-4"
export CUDA_PREFIX="/usr/local/cuda-${CUDA_MM}"

# Force loader to use versioned CUDA libs and set L40S compute capability
# This approach handles pre-existing CUDA by:
# 1. Prioritizing our versioned libs via LD_LIBRARY_PATH (runtime override)
# 2. Using ldconfig to set system-wide library precedence (in 00_prereqs.sh)
# 3. Setting all CUDA_* env vars to point to our version
# 4. Using explicit versioned path /usr/local/cuda-X.Y (avoids symlink conflicts)
export LD_LIBRARY_PATH="${CUDA_PREFIX}/lib64:${CUDA_PREFIX}/targets/x86_64-linux/lib:${LD_LIBRARY_PATH:-}"
export CUDA_HOME="${CUDA_PREFIX}"
export CUDA_PATH="${CUDA_PREFIX}"
export CUDA_ROOT="${CUDA_PREFIX}"
export CUDA_COMPUTE_CAP="${CUDA_COMPUTE_CAP:-89}"  # L40S = sm_89

mkdir -p "${HF_HOME}" "${YAP_LOG_DIR}"