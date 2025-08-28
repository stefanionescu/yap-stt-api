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

# Detect and handle pre-existing CUDA installations
echo "[00] Auditing existing CUDA installations..."
if [ -L "/usr/local/cuda" ]; then
  EXISTING_CUDA_TARGET=$(readlink -f /usr/local/cuda)
  echo "[00] Found existing /usr/local/cuda -> ${EXISTING_CUDA_TARGET}"
elif [ -d "/usr/local/cuda" ]; then
  echo "[00] Found existing /usr/local/cuda directory (not symlink)"
  EXISTING_CUDA_TARGET="/usr/local/cuda"
fi

# Show any system-wide CUDA libs that might conflict
echo "[00] System CUDA libraries found:"
find /usr/lib/x86_64-linux-gnu/ /lib/x86_64-linux-gnu/ /usr/local/ -name "*cuda*" -o -name "*nvrtc*" 2>/dev/null | head -10 | sed 's/^/  /'

# Install toolkit only if we don't have a suitable existing one
EXISTING_CUDA_OK=false
if [ -d "${CUDA_PREFIX}" ]; then
  echo "[00] Found existing CUDA installation at ${CUDA_PREFIX}"
  if [ -x "${CUDA_PREFIX}/bin/nvcc" ]; then
    EXISTING_CUDA_OK=true
    echo "[00] ✓ Existing CUDA ${CUDA_MM} is suitable, skipping installation"
  fi
fi

if [ "$EXISTING_CUDA_OK" = false ]; then
  if ! dpkg -s "cuda-toolkit-${CUDA_MM_PKG}" >/dev/null 2>&1; then
    echo "[00] Installing cuda-toolkit-${CUDA_MM_PKG} to match driver…"
    apt-get install -y --no-install-recommends "cuda-toolkit-${CUDA_MM_PKG}"
  else
    echo "[00] cuda-toolkit-${CUDA_MM_PKG} already installed."
  fi
fi

# Set up CUDA environment
if [ -d "${CUDA_PREFIX}/bin" ]; then
  export PATH="${CUDA_PREFIX}/bin:$PATH"
  
  # Check if /usr/local/cuda points to the right place
  if [ -L "/usr/local/cuda" ]; then
    CURRENT_TARGET=$(readlink -f /usr/local/cuda)
    if [[ "${CURRENT_TARGET}" == "${CUDA_PREFIX}" ]]; then
      echo "[00] ✓ /usr/local/cuda correctly points to ${CUDA_PREFIX}"
    else
      echo "[00] INFO: /usr/local/cuda points to ${CURRENT_TARGET}, we're using ${CUDA_PREFIX}"
      echo "[00] This is fine - we'll use explicit versioned paths"
    fi
  fi
  
  # Only set up custom ldconfig if we need to override existing libs
  NEED_LDCONFIG_OVERRIDE=false
  CURRENT_NVRTC=$(ldconfig -p | awk '/libnvrtc.so./{print $NF}' | head -1)
  if [[ "${CURRENT_NVRTC}" != "${CUDA_PREFIX}"* ]]; then
    NEED_LDCONFIG_OVERRIDE=true
  fi
  
  if [ "$NEED_LDCONFIG_OVERRIDE" = true ]; then
    echo "[00] Setting up library loader priority for ${CUDA_PREFIX}..."
    echo "${CUDA_PREFIX}/lib64" > /etc/ld.so.conf.d/cuda-our-version.conf
    echo "${CUDA_PREFIX}/targets/x86_64-linux/lib" >> /etc/ld.so.conf.d/cuda-our-version.conf
    ldconfig
  else
    echo "[00] ✓ System libraries already point to ${CUDA_PREFIX}"
  fi
  
  # Verify final library setup
  echo "[00] Final library setup:"
  echo "  libnvrtc.so: $(ldconfig -p | awk '/libnvrtc.so./{print $NF}' | head -1)"
  echo "  libcudart.so: $(ldconfig -p | awk '/libcudart.so./{print $NF}' | head -1)"
  
  # Set up persistent environment in ~/.bashrc for manual shell sessions
  grep -q "${CUDA_PREFIX}/bin" ~/.bashrc || echo "export PATH=\"${CUDA_PREFIX}/bin:\$PATH\"" >> ~/.bashrc
  grep -q "LD_LIBRARY_PATH=.*${CUDA_PREFIX}" ~/.bashrc || echo "export LD_LIBRARY_PATH=\"${CUDA_PREFIX}/lib64:${CUDA_PREFIX}/targets/x86_64-linux/lib:\${LD_LIBRARY_PATH:-}\"" >> ~/.bashrc
  grep -q "CUDA_HOME=" ~/.bashrc || echo "export CUDA_HOME=${CUDA_PREFIX}" >> ~/.bashrc
  grep -q "CUDA_PATH=" ~/.bashrc || echo "export CUDA_PATH=${CUDA_PREFIX}" >> ~/.bashrc
  grep -q "CUDA_ROOT=" ~/.bashrc || echo "export CUDA_ROOT=${CUDA_PREFIX}" >> ~/.bashrc
  grep -q "CUDA_COMPUTE_CAP=" ~/.bashrc || echo "export CUDA_COMPUTE_CAP=89  # L40S = sm_89" >> ~/.bashrc
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

# OS/network tuning (backlog, ports, buffers)
cat >/etc/sysctl.d/99-moshi-net.conf <<'EOF'
net.core.somaxconn = 4096
net.ipv4.tcp_max_syn_backlog = 8192
net.core.netdev_max_backlog = 16384
net.ipv4.ip_local_port_range = 10240 65000
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_tw_reuse = 1
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
EOF
sysctl -p /etc/sysctl.d/99-moshi-net.conf || true

echo "[00] cmake: $(cmake --version | head -n1 || echo N/A)"
echo "[00] nvcc:  $(nvcc --version | head -n1 || echo N/A)"
echo "[00] CUDA:  ${CUDA_PREFIX}"
echo "[00] opus:  $(pkg-config --modversion opus || echo N/A)"
echo "[00] Done."