#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"
echo "[00] Installing prerequisites…"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  build-essential git curl pkg-config libssl-dev ca-certificates \
  python3 python3-venv python3-pip ffmpeg tmux jq gnupg \
  cmake libopus-dev

# Rust + uv
if ! command -v cargo >/dev/null 2>&1; then
  curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain stable
  echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
fi
export PATH="$HOME/.cargo/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi
export PATH="$HOME/.local/bin:$PATH"

# File descriptors
bash -c 'cat >/etc/security/limits.d/moshi-nofile.conf <<EOF
* soft nofile 1048576
* hard nofile 1048576
EOF'
ulimit -n 1048576 || true

echo "[00] cmake: $(cmake --version | head -n1 || echo N/A)"
echo "[00] nvcc:  $(nvcc --version | head -n1 || echo N/A)"
echo "[00] opus:  $(pkg-config --modversion opus || echo N/A)"
echo "[00] Done."