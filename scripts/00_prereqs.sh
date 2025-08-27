#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"
echo "[00] Installing prerequisites… (driver supports CUDA ${CUDA_MM})"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  build-essential git curl pkg-config libssl-dev ca-certificates \
  python3 python3-venv python3-pip ffmpeg tmux jq gnupg \
  cmake libopus-dev

# Add NVIDIA CUDA repo (Ubuntu 22.04)
if [ ! -f /usr/share/keyrings/cuda-archive-keyring.gpg ]; then
  curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/3bf863cc.pub \
    | gpg --dearmor -o /usr/share/keyrings/cuda-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/ /" \
    > /etc/apt/sources.list.d/cuda.list
  apt-get update -y
fi

# Install toolkit that matches the driver (e.g., cuda-toolkit-12-2)
if ! dpkg -s "cuda-toolkit-${CUDA_MM_PKG}" >/dev/null 2>&1; then
  echo "[00] Installing cuda-toolkit-${CUDA_MM_PKG} to match driver…"
  apt-get install -y --no-install-recommends "cuda-toolkit-${CUDA_MM_PKG}"
else
  echo "[00] cuda-toolkit-${CUDA_MM_PKG} already installed."
fi

# Prefer versioned CUDA path (avoid /usr/local/cuda symlink pointing to a newer toolkit)
if [ -d "${CUDA_PREFIX}/bin" ]; then
  export PATH="${CUDA_PREFIX}/bin:$PATH"
  export CUDA_HOME="${CUDA_PREFIX}"
  export CUDA_PATH="${CUDA_PREFIX}"
  export CUDA_ROOT="${CUDA_PREFIX}"
  grep -q "${CUDA_PREFIX}/bin" ~/.bashrc || echo "export PATH=\"${CUDA_PREFIX}/bin:\$PATH\"" >> ~/.bashrc
  grep -q "CUDA_HOME=" ~/.bashrc || echo "export CUDA_HOME=${CUDA_PREFIX}" >> ~/.bashrc
  grep -q "CUDA_PATH=" ~/.bashrc || echo "export CUDA_PATH=${CUDA_PREFIX}" >> ~/.bashrc
  grep -q "CUDA_ROOT=" ~/.bashrc || echo "export CUDA_ROOT=${CUDA_PREFIX}" >> ~/.bashrc
fi

# Rust & uv
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

# FD limits
bash -c 'cat >/etc/security/limits.d/moshi-nofile.conf <<EOF
* soft nofile 1048576
* hard nofile 1048576
EOF'
ulimit -n 1048576 || true

echo "[00] cmake: $(cmake --version | head -n1 || echo N/A)"
echo "[00] nvcc:  $(nvcc --version | head -n1 || echo N/A)"
echo "[00] CUDA:  ${CUDA_PREFIX}"
echo "[00] opus:  $(pkg-config --modversion opus || echo N/A)"
echo "[00] Done."