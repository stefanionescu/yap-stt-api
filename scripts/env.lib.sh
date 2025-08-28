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
export MOSHI_ADDR="${MOSHI_ADDR:-0.0.0.0}"
export MOSHI_PORT="${MOSHI_PORT:-8000}"
export MOSHI_CLIENT_HOST="${MOSHI_CLIENT_HOST:-127.0.0.1}"
export MOSHI_PUBLIC_WS_URL="${MOSHI_PUBLIC_WS_URL:-}"
export MOSHI_LOG_DIR="${MOSHI_LOG_DIR:-/workspace/logs}"
export DSM_REPO_DIR="${DSM_REPO_DIR:-/workspace/delayed-streams-modeling}"
export MOSHI_CONFIG="${MOSHI_CONFIG:-/workspace/moshi-stt.toml}"
export TMUX_SESSION="${TMUX_SESSION:-moshi-stt}"
export SMOKETEST_RTF="${SMOKETEST_RTF:-1}"

# Detect existing CUDA installation (common in RunPod/Docker images)
detect_existing_cuda() {
  if [ -L "/usr/local/cuda" ]; then
    local existing_target=$(readlink -f /usr/local/cuda)
    if [[ "${existing_target}" =~ cuda-([0-9]+\.[0-9]+)$ ]]; then
      echo "${BASH_REMATCH[1]}"
      return 0
    fi
  fi
  return 1
}

# Auto-select toolkit version: prefer existing, fallback to driver-capped version
EXISTING_MM=$(detect_existing_cuda || echo "")
SUPPORT_MM="${CUDA_MM:-$(detect_cuda_mm)}"

if [ -n "${EXISTING_MM}" ] && [ -d "/usr/local/cuda-${EXISTING_MM}" ]; then
  # Use existing CUDA installation if it exists and is reasonable
  case "${EXISTING_MM}" in
    12.*|11.*) 
      TOOLKIT_MM="${EXISTING_MM}"
      echo "[env] Using existing CUDA ${EXISTING_MM} installation"
      ;;
    *) 
      # Fallback to driver version if existing is too old/new
      case "${SUPPORT_MM}" in
        12.6|12.5|12.4) TOOLKIT_MM=12.4 ;;
        *) TOOLKIT_MM="${SUPPORT_MM}" ;;
      esac
      echo "[env] Existing CUDA ${EXISTING_MM} not suitable, will install ${TOOLKIT_MM}"
      ;;
  esac
else
  # No existing CUDA, cap to 12.4 for stability
  case "${SUPPORT_MM}" in
    12.6|12.5|12.4) TOOLKIT_MM=12.4 ;;
    *) TOOLKIT_MM="${SUPPORT_MM}" ;;
  esac
  echo "[env] No existing CUDA found, will install ${TOOLKIT_MM}"
fi

export CUDA_MM="${TOOLKIT_MM}"
export CUDA_MM_PKG="${CUDA_MM_PKG:-${CUDA_MM//./-}}" # e.g., "12-4" or "12-8"
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

mkdir -p "${HF_HOME}" "${MOSHI_LOG_DIR}"