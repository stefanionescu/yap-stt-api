#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"

# Set default values for variables that might not be defined
TMUX_SESSION="${TMUX_SESSION:-yap-stt}"
YAP_LOG_DIR="${YAP_LOG_DIR:-/workspace/logs}"
HF_HOME="${HF_HOME:-/workspace/hf_cache}"
CUDA_MM_PKG="${CUDA_MM_PKG:-12-4}"
DSM_REPO_DIR="${DSM_REPO_DIR:-}"

echo "[99] Stopping and cleaning up yap-server installation..."
echo
echo "[99] === DISK USAGE BEFORE CLEANUP ==="
df -h | head -2
echo
echo "[99] === LARGEST DIRECTORIES (before cleanup) ==="
du -sh /workspace/* /root/.* /tmp/* /var/cache/* 2>/dev/null | sort -hr | head -10 || true
echo

# 1. Stop tmux session
if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
  tmux kill-session -t "${TMUX_SESSION}"
  echo "[99] ✓ Stopped tmux session '${TMUX_SESSION}'"
else
  echo "[99] ✓ Session '${TMUX_SESSION}' was not running"
fi

# 1b. Kill any stray yap-server processes not in tmux
if pgrep -f "(^|/| )yap-server( |$)" >/dev/null 2>&1; then
  pkill -9 -f "(^|/| )yap-server( |$)" || true
  echo "[99] ✓ Killed stray yap-server processes"
fi

# 1c. Kill any other moshi-related processes
if pgrep -f "moshi" >/dev/null 2>&1; then
  pkill -9 -f "moshi" || true
  echo "[99] ✓ Killed stray moshi processes"
fi

# 2. Uninstall yap-server binary
if command -v yap-server >/dev/null 2>&1; then
  BIN_PATH="$(command -v yap-server)"
  rm -f "$BIN_PATH"
  echo "[99] ✓ Removed yap-server binary at $BIN_PATH"
else
  echo "[99] ✓ yap-server was not installed"
fi

# 3. Remove cloned repositories and config files
if [ -n "${DSM_REPO_DIR}" ] && [ -d "${DSM_REPO_DIR}" ]; then
  rm -rf "${DSM_REPO_DIR}" && echo "[99] ✓ Removed ${DSM_REPO_DIR}"
fi

# Preserve repo-tracked config files; only remove external config paths
REPO_ROOT="$(cd "${ROOT_DIR}/.." && pwd)"

# Always delete generated runtime configs (*.runtime) even if they live inside the repo tree
if [ -n "${YAP_CONFIG:-}" ] && [[ "${YAP_CONFIG}" == *.runtime ]] && [ -f "${YAP_CONFIG}" ]; then
  rm -f "${YAP_CONFIG}"
  echo "[99] ✓ Removed generated runtime config ${YAP_CONFIG}"
fi
if [ -f "${REPO_ROOT}/server/config-stt-en_fr-hf.toml.runtime" ]; then
  rm -f "${REPO_ROOT}/server/config-stt-en_fr-hf.toml.runtime"
  echo "[99] ✓ Removed server/config-stt-en_fr-hf.toml.runtime"
fi

if [ -n "${YAP_CONFIG:-}" ] && [ -f "${YAP_CONFIG}" ]; then
  case "${YAP_CONFIG}" in
    ${REPO_ROOT}/*)
      echo "[99] ✓ Preserving repo config ${YAP_CONFIG}"
      ;;
    *)
      rm -f "${YAP_CONFIG}" && echo "[99] ✓ Removed ${YAP_CONFIG}"
      ;;
  esac
fi

# 4. Remove log directory
[ -d "${YAP_LOG_DIR}" ] && rm -rf "${YAP_LOG_DIR}" && echo "[99] ✓ Removed ${YAP_LOG_DIR}"

# 5. Remove HuggingFace cache
[ -d "${HF_HOME}" ] && rm -rf "${HF_HOME}" && echo "[99] ✓ Removed HF cache ${HF_HOME}"

# 5b. Remove Rust toolchain and cargo cache (installed by 00_prereqs.sh)
if [ -d "$HOME/.cargo" ]; then
  rm -rf "$HOME/.cargo"
  echo "[99] ✓ Removed Rust cargo cache (~/.cargo)"
fi

# 5b2. Remove rustup installation directory
if [ -d "$HOME/.rustup" ]; then
  rm -rf "$HOME/.rustup"
  echo "[99] ✓ Removed Rust toolchain (~/.rustup)"
fi

# 5c. Remove uv installation (installed by 00_prereqs.sh)
if [ -d "$HOME/.local/bin" ] && [ -f "$HOME/.local/bin/uv" ]; then
  rm -rf "$HOME/.local"
  echo "[99] ✓ Removed uv and ~/.local directory"
fi

# 5d. Remove any temporary cargo build directories
find /tmp -name "cargo-install*" -type d -exec rm -rf {} + 2>/dev/null || true
find /tmp -name "rustc-*" -type d -exec rm -rf {} + 2>/dev/null || true
find /tmp -name "*.deb" -delete 2>/dev/null || true
find /tmp -name "libtinfo5*" -delete 2>/dev/null || true
echo "[99] ✓ Cleaned up temporary build directories and packages"

# 5e. Remove any downloaded model files that might be cached elsewhere
find /workspace -type f \( -name "*.bin" -o -name "*.safetensors" -o -name "*.onnx" \) 2>/dev/null | while read -r model_file; do
  case "$model_file" in
    ${REPO_ROOT}/*)
      # keep files inside the git repo
      ;;
    *)
      # Only remove large model files (>10MB) to avoid deleting random binaries
      if [ -f "$model_file" ] && [ "$(stat -f%z "$model_file" 2>/dev/null || stat -c%s "$model_file" 2>/dev/null)" -gt 10485760 ]; then
        rm -f "$model_file"
        echo "[99] ✓ Removed model file: $model_file"
      fi
      ;;
  esac
done 2>/dev/null || true

# 5f. Clean Python pip cache (can be huge)
if [ -d "$HOME/.cache/pip" ]; then
  rm -rf "$HOME/.cache/pip"
  echo "[99] ✓ Removed pip cache (~/.cache/pip)"
fi

# 5g. Clean apt package cache
if command -v apt-get >/dev/null 2>&1; then
  apt-get clean
  apt-get autoclean
  echo "[99] ✓ Cleaned apt package cache"
fi

# 5h. Remove common cache directories
for cache_dir in "$HOME/.cache" "/root/.cache" "/var/cache" "/tmp/pip*" "/tmp/tmp*"; do
  if [ -d "$cache_dir" ] && [ "$cache_dir" != "/var/cache" ]; then # Keep /var/cache but clean its contents
    rm -rf "$cache_dir"
    echo "[99] ✓ Removed cache directory: $cache_dir"
  fi
done

# Clean specific /var/cache subdirs that are safe to remove
for var_cache in "/var/cache/apt" "/var/cache/debconf" "/var/cache/fontconfig"; do
  if [ -d "$var_cache" ]; then
    rm -rf "$var_cache"/*
    echo "[99] ✓ Cleaned $var_cache"
  fi
done

# 5i. Find and remove any remaining large files (>50MB) in /workspace, /tmp, /root
echo "[99] Scanning for large files (>50MB)..."
find /workspace /tmp /root -type f -size +50M 2>/dev/null | while read -r large_file; do
  # Skip files in our git repo
  if [[ "$large_file" != *"/yap-stt-api/"* ]] || [[ "$large_file" == *".git/"* ]]; then
    rm -f "$large_file"
    echo "[99] ✓ Removed large file: $large_file"
  fi
done

# 5k. Remove repo-local build artifacts and virtual environments
echo "[99] Removing repo virtualenvs, Rust targets, and __pycache__ directories..."
REPO_ARTIFACT_DIRS=(
  "${REPO_ROOT}/.venv"
  "${REPO_ROOT}/venv"
  "${REPO_ROOT}/server/.venv"
  "${REPO_ROOT}/server/venv"
  "${REPO_ROOT}/server/moshi-server/.venv"
  "${REPO_ROOT}/server/target"
  "${REPO_ROOT}/target"
  "${REPO_ROOT}/test/results"
)
for artifact in "${REPO_ARTIFACT_DIRS[@]}"; do
  if [ -e "$artifact" ]; then
    rm -rf "$artifact"
    echo "[99] ✓ Removed repo artifact: $artifact"
  fi
done
find "${REPO_ROOT}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null && \
  echo "[99] ✓ Purged Python __pycache__ directories"
find "${REPO_ROOT}" -name "*.pyc" -delete 2>/dev/null && \
  echo "[99] ✓ Purged Python bytecode files"

# 5j. Remove system packages we installed (unless --keep-packages flag is used)
echo
if [[ "${1:-}" == "--keep-packages" ]]; then
  echo "[99] --keep-packages flag detected, keeping system packages..."
else
  echo "[99] Removing system packages installed by scripts (cmake, libopus-dev, etc.)..."
  if command -v apt-get >/dev/null 2>&1; then
    # Remove packages installed by 00_prereqs.sh
    apt-get remove --purge -y cmake libopus-dev build-essential pkg-config libssl-dev ffmpeg tmux jq python3-pip gnupg 2>/dev/null || true
    # Only remove CUDA if WE installed it (check for our apt source file)
    if [ -f "/etc/apt/sources.list.d/cuda.list" ]; then
      echo "[99] Removing CUDA toolkit-${CUDA_MM_PKG} that WE installed..."
      apt-get remove --purge -y "cuda-toolkit-${CUDA_MM_PKG}" 2>/dev/null || true
      # Remove CUDA apt source that WE added
      rm -f /etc/apt/sources.list.d/cuda.list
      rm -f /usr/share/keyrings/cuda-archive-keyring.gpg
      # Remove our ldconfig configuration
      rm -f /etc/ld.so.conf.d/cuda-our-version.conf
      ldconfig
      echo "[99] ✓ Cleaned up CUDA ldconfig configuration"
    else
      echo "[99] Keeping RunPod's built-in CUDA toolkit (not installed by us)"
      # Still clean up our ldconfig config if it exists
      if [ -f "/etc/ld.so.conf.d/cuda-our-version.conf" ]; then
        rm -f /etc/ld.so.conf.d/cuda-our-version.conf
        ldconfig
        echo "[99] ✓ Cleaned up our CUDA ldconfig configuration"
      fi
    fi
    apt-get autoremove --purge -y 2>/dev/null || true
    # Always nuke CUDA packages and symlinks to avoid conflicts on next run
    echo "[99] Purging all CUDA packages and paths (default behavior)"
    apt-get remove --purge -y 'cuda-*' nvidia-cuda-toolkit 2>/dev/null || true
    rm -f /usr/local/cuda || true
    rm -rf /usr/local/cuda-* || true
    rm -f /etc/ld.so.conf.d/cuda-our-version.conf || true
    ldconfig || true
    echo "[99] ✓ Removed system packages installed by scripts"
  fi
fi

# 6. Remove file descriptor limits config
if [ -f "/etc/security/limits.d/moshi-nofile.conf" ]; then
  rm -f "/etc/security/limits.d/moshi-nofile.conf"
  echo "[99] ✓ Removed file descriptor limits config"
fi
# 6b. Remove network tuning configuration
if [ -f "/etc/sysctl.d/99-moshi-net.conf" ]; then
  rm -f "/etc/sysctl.d/99-moshi-net.conf"
  echo "[99] ✓ Removed network tuning config"
fi

# 6c. Remove CUDA installation sentinel files
if [ -d "/var/lib/yap" ]; then
  rm -rf "/var/lib/yap"
  echo "[99] ✓ Removed CUDA installation markers (/var/lib/yap)"
fi

# 7. Clean up environment variables from ~/.bashrc
if [ -f ~/.bashrc ]; then
  # Remove HF_HOME and HF_HUB_ENABLE_HF_TRANSFER exports
  sed -i '/export HF_HOME=/d' ~/.bashrc
  sed -i '/export HF_HUB_ENABLE_HF_TRANSFER=/d' ~/.bashrc
  # Remove PATH additions for cargo and uv
  sed -i '/export PATH="$HOME\/.cargo\/bin:$PATH"/d' ~/.bashrc
  sed -i '/export PATH="$HOME\/.local\/bin:$PATH"/d' ~/.bashrc
  # Remove CUDA environment variables (handle versioned paths like /usr/local/cuda-12.2)
  sed -i '/export PATH=.*\/usr\/local\/cuda.*bin.*\$PATH/d' ~/.bashrc
  sed -i '/export CUDA_HOME=.*\/usr\/local\/cuda/d' ~/.bashrc
  sed -i '/export CUDA_PATH=.*\/usr\/local\/cuda/d' ~/.bashrc
  sed -i '/export CUDA_ROOT=.*\/usr\/local\/cuda/d' ~/.bashrc
  # Remove CUDA_COMPUTE_CAP export
  sed -i '/export CUDA_COMPUTE_CAP=/d' ~/.bashrc
  # Remove LD_LIBRARY_PATH exports (all variations)
  sed -i '/export LD_LIBRARY_PATH=.*cuda.*lib/d' ~/.bashrc
  echo "[99] ✓ Cleaned up environment variables from ~/.bashrc"
fi

# 8. Remove the .env file created by main.sh
ENV_FILE="${ROOT_DIR}/.env"
if [ -f "${ENV_FILE}" ]; then
  rm -f "${ENV_FILE}"
  echo "[99] ✓ Removed ${ENV_FILE}"
fi

echo
echo "[99] ===== CLEANUP COMPLETE ====="
echo "[99] Preserved:"
echo "[99]   • Git repository and your code"
if [[ "${1:-}" == "--keep-packages" ]]; then
  echo "[99]   • System packages (--keep-packages flag used)"
fi
echo
echo "[99] Removed:"
echo "[99]   • yap-server binary and moshi processes"
echo "[99]   • Rust toolchain (~/.rustup and ~/.cargo)"
echo "[99]   • uv tool and ~/.local directory"
echo "[99]   • All downloaded models and HF cache"
echo "[99]   • All log files and tmux sessions"
echo "[99]   • Configuration files (outside repo) and cloned repos"
echo "[99]   • Python pip cache (~/.cache/pip) and bytecode files"
echo "[99]   • Repo build artifacts (venv, target, __pycache__)"
if [[ "${1:-}" != "--keep-packages" ]]; then
  echo "[99]   • System packages (cmake, libopus-dev, CUDA toolkit, etc.)"
fi
echo "[99]   • System package caches (apt, debconf, fontconfig)"
echo "[99]   • All common cache directories"
echo "[99]   • Large files >50MB (outside git repo)"
echo "[99]   • Network tuning configuration (/etc/sysctl.d/99-moshi-net.conf)"
echo "[99]   • CUDA installation markers (/var/lib/yap/)"
echo "[99]   • File descriptor limits config"
echo "[99]   • Environment variables (Rust, CUDA, HF, uv, LD_LIBRARY_PATH) from ~/.bashrc"
echo "[99]   • CUDA ldconfig configurations"
echo "[99]   • Generated .env files and temporary packages"
echo
echo "[99] === DISK USAGE AFTER CLEANUP ==="
df -h | head -2
echo
echo "[99] === LARGEST REMAINING DIRECTORIES ==="
du -sh /workspace/* /root/.* /tmp/* /var/cache/* 2>/dev/null | sort -hr | head -10 || true
echo
echo "[99] To reinstall: run './main.sh' again"
echo "[99] To keep system packages: run 'bash scripts/stop.sh --keep-packages'"
