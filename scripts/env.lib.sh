# shellcheck shell=bash
set -euo pipefail

# Resolve repo root (works whether script is in . or ./scripts)
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${THIS_DIR}"
[ -f "${ROOT_DIR}/.env" ] || { [ -f "${ROOT_DIR}/../.env" ] && ROOT_DIR="${THIS_DIR}/.."; }

# Load .env if present
if [ -f "${ROOT_DIR}/.env" ]; then
  set -a; source "${ROOT_DIR}/.env"; set +a
fi

# Safe defaults if .env missing or partial
export HF_HOME="${HF_HOME:-/workspace/hf_cache}"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"
export MOSHI_ADDR="${MOSHI_ADDR:-0.0.0.0}"           # bind address
export MOSHI_PORT="${MOSHI_PORT:-8000}"
export MOSHI_CLIENT_HOST="${MOSHI_CLIENT_HOST:-127.0.0.1}"  # where client connects
export MOSHI_PUBLIC_WS_URL="${MOSHI_PUBLIC_WS_URL:-}"       # optional full wss URL via Runpod proxy
export MOSHI_LOG_DIR="${MOSHI_LOG_DIR:-/workspace/logs}"
export DSM_REPO_DIR="${DSM_REPO_DIR:-/workspace/delayed-streams-modeling}"
export MOSHI_CONFIG="${MOSHI_CONFIG:-/workspace/moshi-stt.toml}"
export TMUX_SESSION="${TMUX_SESSION:-moshi-stt}"
export SMOKETEST_RTF="${SMOKETEST_RTF:-1000}"

# Ensure paths exist
mkdir -p "${HF_HOME}" "${MOSHI_LOG_DIR}"
