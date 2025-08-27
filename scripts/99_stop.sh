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
echo
echo "[99] === DISK USAGE BEFORE CLEANUP ==="
df -h | head -2
echo
echo "[99] === LARGEST DIRECTORIES (before cleanup) ==="
du -sh /workspace/* /root/.* /tmp/* /var/cache/* 2>/dev/null | sort -hr | head -10 || true
echo

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
echo "[99] ✓ Cleaned up temporary build directories"

# 5e. Remove any downloaded model files that might be cached elsewhere
find /workspace -name "*.bin" -o -name "*.safetensors" -o -name "*.onnx" | while read -r model_file; do
  # Only remove large model files (>10MB) to avoid deleting random binaries
  if [ -f "$model_file" ] && [ "$(stat -f%z "$model_file" 2>/dev/null || stat -c%s "$model_file" 2>/dev/null)" -gt 10485760 ]; then
    rm -f "$model_file"
    echo "[99] ✓ Removed model file: $model_file"
  fi
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

# 5j. NUCLEAR OPTION: Remove even the system packages we installed
echo
if [[ "${1:-}" == "--nuclear" ]]; then
  REPLY="y"
  echo "[99] --nuclear flag detected, removing system packages..."
else
  read -p "[99] Also remove system packages installed by scripts (cmake, libopus-dev, etc.)? [y/N]: " -n 1 -r
  echo
fi
if [[ $REPLY =~ ^[Yy]$ ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    # Remove packages installed by 00_prereqs.sh
    apt-get remove --purge -y cmake libopus-dev build-essential pkg-config libssl-dev ffmpeg tmux jq python3-pip gnupg 2>/dev/null || true
    # Only remove CUDA if WE installed it (check for our apt source file)
    if [ -f "/etc/apt/sources.list.d/cuda.list" ]; then
      echo "[99] Removing CUDA toolkit that WE installed (not RunPod's built-in CUDA)..."
      apt-get remove --purge -y 'cuda-toolkit-12-8' 'cuda-toolkit-12-4' 2>/dev/null || true
      # Remove CUDA apt source that WE added
      rm -f /etc/apt/sources.list.d/cuda.list
      rm -f /usr/share/keyrings/cuda-archive-keyring.gpg
    else
      echo "[99] Keeping RunPod's built-in CUDA toolkit (not installed by us)"
    fi
    apt-get autoremove --purge -y 2>/dev/null || true
    echo "[99] ✓ Removed system packages installed by scripts"
  fi
else
  echo "[99] ✓ Keeping system packages (cmake, libopus-dev, etc.)"
fi

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
  # Remove CUDA environment variables (handle both versioned and unversioned paths)
  sed -i '/export PATH=.*cuda.*bin.*\$PATH/d' ~/.bashrc
  sed -i '/export CUDA_HOME=/d' ~/.bashrc
  sed -i '/export CUDA_PATH=/d' ~/.bashrc
  sed -i '/export CUDA_ROOT=/d' ~/.bashrc
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
echo "[99]   • RunPod's built-in CUDA toolkit (if not installed by scripts)"
echo "[99]   • System packages that came with RunPod image"
echo
echo "[99] Removed:"
echo "[99]   • moshi-server binary"
echo "[99]   • Rust toolchain (~/.rustup and ~/.cargo)"
echo "[99]   • uv tool and ~/.local directory"
echo "[99]   • All downloaded models and HF cache"
echo "[99]   • All log files and tmux sessions"
echo "[99]   • Configuration files and cloned repos"
echo "[99]   • Python pip cache (~/.cache/pip)"
echo "[99]   • System package caches (apt, debconf, fontconfig)"
echo "[99]   • All common cache directories"
echo "[99]   • Large files >50MB (outside git repo)"
echo "[99]   • Environment variables (Rust, CUDA, HF, uv) from ~/.bashrc"
echo
echo "[99] === DISK USAGE AFTER CLEANUP ==="
df -h | head -2
echo
echo "[99] === LARGEST REMAINING DIRECTORIES ==="
du -sh /workspace/* /root/.* /tmp/* /var/cache/* 2>/dev/null | sort -hr | head -10 || true
echo
echo "[99] To reinstall: run 'bash scripts/main.sh' again"
echo "[99] For maximum cleanup: run 'bash scripts/99_stop.sh --nuclear'"
