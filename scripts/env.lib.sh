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

# Auto-select toolkit version to match driver
export CUDA_MM="${CUDA_MM:-$(detect_cuda_mm)}"      # e.g., "12.2"
export CUDA_MM_PKG="${CUDA_MM_PKG:-${CUDA_MM//./-}}" # e.g., "12-2"
export CUDA_PREFIX="/usr/local/cuda-${CUDA_MM}"

mkdir -p "${HF_HOME}" "${MOSHI_LOG_DIR}"