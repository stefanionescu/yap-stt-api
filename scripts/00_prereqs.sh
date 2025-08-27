#!/usr/bin/env bash
set -euo pipefail
echo "[00] Installing prerequisites…"

export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y --no-install-recommends \
  build-essential git curl pkg-config libssl-dev ca-certificates \
  python3 python3-venv python3-pip ffmpeg tmux jq \
  cmake libopus-dev gnupg

# ---------------- CUDA TOOLKIT (for nvcc) ----------------
# Check if CUDA is already available (RunPod devel images often have it)
if command -v nvcc >/dev/null 2>&1; then
  echo "[00] CUDA toolkit already present: $(nvcc --version | head -n1)"
  # Just ensure environment variables are set
  if [ -d /usr/local/cuda/bin ]; then
    export PATH="/usr/local/cuda/bin:${PATH}"
    export CUDA_HOME="/usr/local/cuda"
    export CUDA_PATH="/usr/local/cuda" 
    export CUDA_ROOT="/usr/local/cuda"
  elif [ -d /usr/local/cuda-12/bin ]; then
    # Some RunPod images use versioned CUDA paths
    export PATH="/usr/local/cuda-12/bin:${PATH}"
    export CUDA_HOME="/usr/local/cuda-12"
    export CUDA_PATH="/usr/local/cuda-12"
    export CUDA_ROOT="/usr/local/cuda-12"
  fi
else
  echo "[00] CUDA toolkit not found; installing 12.8.1 (matching RunPod image)…"
  curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/3bf863cc.pub \
    | gpg --dearmor -o /usr/share/keyrings/cuda-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/ /" \
    > /etc/apt/sources.list.d/cuda.list
  apt-get update -y
  # Install CUDA 12.8.1 to match RunPod image version
  apt-get install -y --no-install-recommends cuda-toolkit-12-8
  export PATH="/usr/local/cuda/bin:${PATH}"
  export CUDA_HOME="/usr/local/cuda"
  export CUDA_PATH="/usr/local/cuda"
  export CUDA_ROOT="/usr/local/cuda"
fi

# Ensure CUDA environment persists in ~/.bashrc
if [ -n "${CUDA_HOME:-}" ]; then
  grep -q 'export PATH=.*cuda.*bin' ~/.bashrc || echo "export PATH=\"${CUDA_HOME}/bin:\$PATH\"" >> ~/.bashrc
  grep -q 'export CUDA_HOME=' ~/.bashrc || echo "export CUDA_HOME=${CUDA_HOME}" >> ~/.bashrc
  grep -q 'export CUDA_PATH=' ~/.bashrc || echo "export CUDA_PATH=${CUDA_HOME}" >> ~/.bashrc
  grep -q 'export CUDA_ROOT=' ~/.bashrc || echo "export CUDA_ROOT=${CUDA_HOME}" >> ~/.bashrc
fi

# ---------------- Rust toolchain ----------------
if ! command -v cargo >/dev/null 2>&1; then
  curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain stable
  echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
  export PATH="$HOME/.cargo/bin:$PATH"
fi

# ---------------- uv (Kyutai client scripts) ----------------
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  export PATH="$HOME/.local/bin:$PATH"
fi

# ---------------- HF cache + file limits ----------------
mkdir -p "${HF_HOME}"
grep -q 'HF_HOME' ~/.bashrc || echo 'export HF_HOME=/workspace/hf_cache' >> ~/.bashrc
grep -q 'HF_HUB_ENABLE_HF_TRANSFER' ~/.bashrc || echo 'export HF_HUB_ENABLE_HF_TRANSFER=1' >> ~/.bashrc

bash -c 'cat >/etc/security/limits.d/moshi-nofile.conf <<EOF
* soft nofile 1048576
* hard nofile 1048576
EOF'
ulimit -n 1048576 || true
mkdir -p "${MOSHI_LOG_DIR}"

# ---------------- Sanity printouts ----------------
echo "[00] cmake:      $(cmake --version | head -n1 || echo 'missing')"
echo "[00] pkg-config: $(pkg-config --version || echo 'missing')"
echo "[00] opus:       $(pkg-config --modversion opus || echo 'not found (unexpected)')"
echo "[00] nvcc:       $(nvcc --version | head -n1 || echo 'missing (unexpected)')"
echo "[00] CUDA_HOME:  ${CUDA_HOME:-unset}"
echo "[00] Prereqs installed (CUDA 12.8.1 compatible)."