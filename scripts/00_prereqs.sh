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

# CUDA toolkit (nvcc) for cudarc
if ! command -v nvcc >/dev/null 2>&1; then
  echo "[00] Installing CUDA toolkit 12.4…"
  curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/3bf863cc.pub \
    | gpg --dearmor -o /usr/share/keyrings/cuda-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/ /" \
    > /etc/apt/sources.list.d/cuda.list
  apt-get update -y
  apt-get install -y --no-install-recommends cuda-toolkit-12-4
fi
export PATH="/usr/local/cuda/bin:$PATH"
export CUDA_HOME="/usr/local/cuda"
export CUDA_PATH="/usr/local/cuda"
export CUDA_ROOT="/usr/local/cuda"
grep -q 'cuda/bin' ~/.bashrc || echo 'export PATH="/usr/local/cuda/bin:$PATH"' >> ~/.bashrc
grep -q 'CUDA_HOME=' ~/.bashrc || echo 'export CUDA_HOME=/usr/local/cuda' >> ~/.bashrc
grep -q 'CUDA_PATH=' ~/.bashrc || echo 'export CUDA_PATH=/usr/local/cuda' >> ~/.bashrc
grep -q 'CUDA_ROOT=' ~/.bashrc || echo 'export CUDA_ROOT=/usr/local/cuda' >> ~/.bashrc

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