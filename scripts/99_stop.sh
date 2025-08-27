#!/usr/bin/env bash
set -euo pipefail

# Load env vars if available
if [ -f "$(dirname "${BASH_SOURCE[0]}")/.env" ]; then
  set -a; source "$(dirname "${BASH_SOURCE[0]}")/.env"; set +a
fi

# Set defaults if not loaded from .env
SESSION="${TMUX_SESSION:-moshi-stt}"
HF_HOME="${HF_HOME:-/workspace/hf_cache}"
MOSHI_LOG_DIR="${MOSHI_LOG_DIR:-/workspace/logs}"
DSM_REPO_DIR="${DSM_REPO_DIR:-/workspace/delayed-streams-modeling}"
MOSHI_CONFIG="${MOSHI_CONFIG:-/workspace/moshi-stt.toml}"

echo "[99] Stopping and cleaning up moshi-server installation..."

# 1. Stop tmux session
if tmux has-session -t "${SESSION}" 2>/dev/null; then
  tmux kill-session -t "${SESSION}"
  echo "[99] ✓ Stopped tmux session '${SESSION}'"
else
  echo "[99] ✓ Session '${SESSION}' was not running"
fi

# 2. Uninstall moshi-server binary
if command -v moshi-server >/dev/null 2>&1; then
  if command -v cargo >/dev/null 2>&1; then
    cargo uninstall moshi-server
    echo "[99] ✓ Uninstalled moshi-server binary"
  else
    echo "[99] ✗ cargo not found, cannot uninstall moshi-server"
  fi
else
  echo "[99] ✓ moshi-server was not installed"
fi

# 3. Remove cloned repositories and config files
[ -d "${DSM_REPO_DIR}" ] && rm -rf "${DSM_REPO_DIR}" && echo "[99] ✓ Removed ${DSM_REPO_DIR}"
[ -f "${MOSHI_CONFIG}" ] && rm -f "${MOSHI_CONFIG}" && echo "[99] ✓ Removed ${MOSHI_CONFIG}"

# 4. Remove log directory
[ -d "${MOSHI_LOG_DIR}" ] && rm -rf "${MOSHI_LOG_DIR}" && echo "[99] ✓ Removed ${MOSHI_LOG_DIR}"

# 5. Remove HuggingFace cache
[ -d "${HF_HOME}" ] && rm -rf "${HF_HOME}" && echo "[99] ✓ Removed HF cache ${HF_HOME}"

# 5b. Remove Rust toolchain and cargo cache (installed by 00_prereqs.sh)
if [ -d "$HOME/.cargo" ]; then
  rm -rf "$HOME/.cargo"
  echo "[99] ✓ Removed Rust toolchain and cargo cache (~/.cargo)"
fi

# 5c. Remove uv installation (installed by 00_prereqs.sh)
if [ -d "$HOME/.local/bin" ] && [ -f "$HOME/.local/bin/uv" ]; then
  rm -rf "$HOME/.local"
  echo "[99] ✓ Removed uv and ~/.local directory"
fi

# 5d. Remove any temporary cargo build directories
find /tmp -name "cargo-install*" -type d -exec rm -rf {} + 2>/dev/null || true
find /tmp -name "rustc-*" -type d -exec rm -rf {} + 2>/dev/null || true
echo "[99] ✓ Cleaned up temporary build directories"

# 5e. Remove any downloaded model files that might be cached elsewhere
find /workspace -name "*.bin" -o -name "*.safetensors" -o -name "*.onnx" | while read -r model_file; do
  # Only remove large model files (>10MB) to avoid deleting random binaries
  if [ -f "$model_file" ] && [ "$(stat -f%z "$model_file" 2>/dev/null || stat -c%s "$model_file" 2>/dev/null)" -gt 10485760 ]; then
    rm -f "$model_file"
    echo "[99] ✓ Removed model file: $model_file"
  fi
done 2>/dev/null || true

# 6. Remove file descriptor limits config
if [ -f "/etc/security/limits.d/moshi-nofile.conf" ]; then
  rm -f "/etc/security/limits.d/moshi-nofile.conf"
  echo "[99] ✓ Removed file descriptor limits config"
fi

# 7. Clean up environment variables from ~/.bashrc
if [ -f ~/.bashrc ]; then
  # Remove HF_HOME and HF_HUB_ENABLE_HF_TRANSFER exports
  sed -i '/export HF_HOME=/d' ~/.bashrc
  sed -i '/export HF_HUB_ENABLE_HF_TRANSFER=/d' ~/.bashrc
  # Remove PATH additions for cargo and uv
  sed -i '/export PATH="$HOME\/.cargo\/bin:$PATH"/d' ~/.bashrc
  sed -i '/export PATH="$HOME\/.local\/bin:$PATH"/d' ~/.bashrc
  echo "[99] ✓ Cleaned up environment variables from ~/.bashrc"
fi

# 8. Remove the .env file created by main.sh
ENV_FILE="$(dirname "${BASH_SOURCE[0]}")/.env"
if [ -f "${ENV_FILE}" ]; then
  rm -f "${ENV_FILE}"
  echo "[99] ✓ Removed ${ENV_FILE}"
fi

echo
echo "[99] ===== CLEANUP COMPLETE ====="
echo "[99] Preserved:"
echo "[99]   • Git repository and your code"
echo "[99]   • System packages (build-essential, cmake, libopus-dev, etc.)"
echo
echo "[99] Removed:"
echo "[99]   • moshi-server binary"
echo "[99]   • Rust toolchain and cargo cache (~/.cargo)"
echo "[99]   • uv tool and ~/.local directory"
echo "[99]   • All downloaded models and HF cache"
echo "[99]   • All log files and tmux sessions"
echo "[99]   • Configuration files and cloned repos"
echo "[99]   • Environment variable exports from ~/.bashrc"
echo
echo "[99] To reinstall: run 'bash scripts/main.sh' again"
