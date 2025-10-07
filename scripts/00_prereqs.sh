#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.lib.sh"

adjust_cuda_version_for_os() {
  local env_file="${ROOT_DIR}/.env"
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [ "${ID}" = "ubuntu" ] && [[ "${VERSION_ID}" == 24.04* ]] && [[ "${CUDA_MM}" == 12.4* ]]; then
      local new_cuda="12.6"
      echo "[00] NOTE: Ubuntu 24.04 detected; switching CUDA target from ${CUDA_MM} to ${new_cuda}."
      CUDA_MM="${new_cuda}"
      export CUDA_MM
      if [ -f "${env_file}" ]; then
        if grep -q '^CUDA_MM=' "${env_file}"; then
          sed -i "s/^CUDA_MM=.*/CUDA_MM=${CUDA_MM}/" "${env_file}"
        else
          echo "CUDA_MM=${CUDA_MM}" >> "${env_file}"
        fi
        if grep -q '^CUDA_MM_PKG=' "${env_file}"; then
          sed -i "s/^CUDA_MM_PKG=.*/CUDA_MM_PKG=${CUDA_MM//./-}/" "${env_file}"
        else
          echo "CUDA_MM_PKG=${CUDA_MM//./-}" >> "${env_file}"
        fi
      fi
    fi
  fi
}

strip_cuda_from_pathlike() {
  local original="${1:-}"
  local trimmed=""
  local part
  IFS=':' read -r -a parts <<< "${original}"
  for part in "${parts[@]}"; do
    if [[ -n "${part}" && ${part} != /usr/local/cuda-* ]]; then
      if [ -n "${trimmed}" ]; then
        trimmed+=":${part}"
      else
        trimmed="${part}"
      fi
    fi
  done
  printf '%s' "${trimmed}"
}

refresh_cuda_env_vars() {
  export CUDA_MM_PKG="${CUDA_MM//./-}"
  export CUDA_PREFIX="/usr/local/cuda-${CUDA_MM}"

  local base_path
  base_path=$(strip_cuda_from_pathlike "${PATH:-}")
  if [ -n "${base_path}" ]; then
    export PATH="${CUDA_PREFIX}/bin:${base_path}"
  else
    export PATH="${CUDA_PREFIX}/bin"
  fi

  local base_ld
  base_ld=$(strip_cuda_from_pathlike "${LD_LIBRARY_PATH:-}")
  if [ -n "${base_ld}" ]; then
    export LD_LIBRARY_PATH="${CUDA_PREFIX}/lib64:${CUDA_PREFIX}/targets/x86_64-linux/lib:${base_ld}"
  else
    export LD_LIBRARY_PATH="${CUDA_PREFIX}/lib64:${CUDA_PREFIX}/targets/x86_64-linux/lib"
  fi

  export CUDA_HOME="${CUDA_PREFIX}"
  export CUDA_PATH="${CUDA_PREFIX}"
  export CUDA_ROOT="${CUDA_PREFIX}"
}

adjust_cuda_version_for_os
refresh_cuda_env_vars

echo "[00] Installing prerequisites… (driver supports CUDA ${CUDA_MM})"

# Require Kyutai API key early to avoid wasted setup time
if [ -z "${KYUTAI_API_KEY:-}" ]; then
  echo "[00] ERROR: KYUTAI_API_KEY not set. Please 'export KYUTAI_API_KEY=your_secret' before running scripts." >&2
  exit 1
fi

# Feature flags
ENABLE_SMOKE_TEST="${ENABLE_SMOKE_TEST:-0}"
ENABLE_NET_TUNING="${ENABLE_NET_TUNING:-0}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
# Core build/runtime deps (minimal)
apt-get install -y --no-install-recommends \
  build-essential git curl pkg-config libssl-dev ca-certificates \
  cmake libopus-dev tmux gnupg ffmpeg

# Optional: smoke-test tooling (Python, ffmpeg, uv)
if [ "${ENABLE_SMOKE_TEST}" = "1" ]; then
  apt-get install -y --no-install-recommends python3 python3-venv python3-pip
fi

# Add NVIDIA CUDA repo matching the host distribution + requested CUDA version
CUDA_REPO_SUFFIX="ubuntu2204"
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}" in
    ubuntu)
      case "${VERSION_ID:-}" in
        24.04*)
          if [[ "${CUDA_MM}" == 12.4* ]]; then
            CUDA_REPO_SUFFIX="ubuntu2204"  # 12.4 not published for noble yet
          else
            CUDA_REPO_SUFFIX="ubuntu2404"
          fi
          ;;
        22.04*) CUDA_REPO_SUFFIX="ubuntu2204" ;;
        20.04*) CUDA_REPO_SUFFIX="ubuntu2004" ;;
      esac
      ;;
    debian)
      case "${VERSION_ID:-}" in
        12*) CUDA_REPO_SUFFIX="debian12" ;;
        11*) CUDA_REPO_SUFFIX="debian11" ;;
      esac
      ;;
  esac
fi

CUDA_REPO_URL="https://developer.download.nvidia.com/compute/cuda/repos/${CUDA_REPO_SUFFIX}/x86_64/"
if [ ! -f /usr/share/keyrings/cuda-archive-keyring.gpg ]; then
  curl -fsSL "${CUDA_REPO_URL}3bf863cc.pub" \
    | gpg --dearmor -o /usr/share/keyrings/cuda-archive-keyring.gpg
fi
echo "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] ${CUDA_REPO_URL} /" \
  > /etc/apt/sources.list.d/cuda.list
apt-get update -y

# Detect and handle pre-existing CUDA installations (nuke >12.4)
echo "[00] Auditing existing CUDA installations..."
if [ -L "/usr/local/cuda" ]; then
  EXISTING_CUDA_TARGET=$(readlink -f /usr/local/cuda)
  echo "[00] Found existing /usr/local/cuda -> ${EXISTING_CUDA_TARGET}"
elif [ -d "/usr/local/cuda" ]; then
  echo "[00] Found existing /usr/local/cuda directory (not symlink)"
  EXISTING_CUDA_TARGET="/usr/local/cuda"
fi

# If an existing CUDA > 12.4 is present, purge conflicting packages
if [ -n "${EXISTING_CUDA_TARGET:-}" ]; then
  if [[ "${EXISTING_CUDA_TARGET}" =~ cuda-([0-9]+)\.([0-9]+)$ ]]; then
    EXISTING_MAJOR=${BASH_REMATCH[1]}
    EXISTING_MINOR=${BASH_REMATCH[2]}
    if (( EXISTING_MAJOR > 12 )) || { (( EXISTING_MAJOR == 12 )) && (( EXISTING_MINOR > 4 )); }; then
      echo "[00] Detected CUDA ${EXISTING_MAJOR}.${EXISTING_MINOR} (> 12.4). Purging to install 12.4..."
      # Remove CUDA meta packages that can override libs
      apt-get remove --purge -y 'cuda-*' nvidia-cuda-toolkit 2>/dev/null || true
      rm -f /etc/ld.so.conf.d/cuda-our-version.conf || true
      ldconfig || true
      rm -f /usr/local/cuda || true
    fi
  fi
fi

# Show any system-wide CUDA libs that might conflict (robust under pipefail)
echo "[00] System CUDA libraries found:"
(
  set +e
  find /usr/lib/x86_64-linux-gnu/ /lib/x86_64-linux-gnu/ /usr/local/ \
    \( -name "*cuda*" -o -name "*nvrtc*" \) 2>/dev/null \
    | sed -n '1,10{s/^/  /;p;}'
) || true

# Always install the requested CUDA toolkit if not present
CUDA_SENTINEL="/var/lib/yap/cuda-${CUDA_MM}.installed"

ensure_libtinfo5() {
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [ "${ID}" = "ubuntu" ] && [[ "${VERSION_ID}" == 24.04* ]]; then
      if ! dpkg -s libtinfo5 >/dev/null 2>&1; then
        echo "[00] Installing libtinfo5 compatibility package for Ubuntu 24.04..."
        TMP_DEB=$(mktemp /tmp/libtinfo5_XXXX.deb)
        curl -fsSL http://archive.ubuntu.com/ubuntu/pool/main/n/ncurses/libtinfo5_6.3-2_amd64.deb -o "${TMP_DEB}"
        dpkg -i "${TMP_DEB}" 2>/dev/null || apt-get -y --fix-broken install
        rm -f "${TMP_DEB}"
      fi
    fi
  fi
}

install_cuda_toolkit() {
  local attempt=1
  while [ $attempt -le 2 ]; do
    echo "[00] Installing cuda-toolkit-${CUDA_MM_PKG} (attempt ${attempt})…"
    if apt-get install -y --no-install-recommends -o Dpkg::Options::="--force-overwrite" "cuda-toolkit-${CUDA_MM_PKG}"; then
      mkdir -p "$(dirname "${CUDA_SENTINEL}")"
      touch "${CUDA_SENTINEL}"
      return 0
    fi
    echo "[00] cuda-toolkit-${CUDA_MM_PKG} install failed." >&2
    if [ $attempt -eq 1 ]; then
      ensure_libtinfo5
      apt-get -y --fix-broken install || true
      apt-get remove --purge -y "cuda-toolkit-${CUDA_MM_PKG}" "cuda-compiler-${CUDA_MM_PKG}" \
        "cuda-minimal-build-${CUDA_MM_PKG}" "cuda-command-line-tools-${CUDA_MM_PKG}" \
        "cuda-nvcc-${CUDA_MM_PKG}" "cuda-nvrtc-${CUDA_MM_PKG}" "cuda-nvrtc-dev-${CUDA_MM_PKG}" \
        "cuda-cudart-${CUDA_MM_PKG}" "cuda-cudart-dev-${CUDA_MM_PKG}" "cuda-cccl-${CUDA_MM_PKG}" 2>/dev/null || true
      apt-get autoremove -y 2>/dev/null || true
    else
      break
    fi
    attempt=$((attempt + 1))
  done
  echo "[00] ERROR: Failed to install cuda-toolkit-${CUDA_MM_PKG}." >&2
  exit 1
}

if dpkg -s "cuda-toolkit-${CUDA_MM_PKG}" >/dev/null 2>&1; then
  echo "[00] cuda-toolkit-${CUDA_MM_PKG} already installed."
  mkdir -p "$(dirname "${CUDA_SENTINEL}")"
  touch "${CUDA_SENTINEL}"
elif [ -f "${CUDA_SENTINEL}" ] && [ -x "${CUDA_PREFIX}/bin/nvcc" ]; then
  echo "[00] CUDA ${CUDA_MM} previously installed."
else
  ensure_libtinfo5
  install_cuda_toolkit
fi

# Set up CUDA 12.4 environment
if [ -d "${CUDA_PREFIX}/bin" ]; then
  export PATH="${CUDA_PREFIX}/bin:$PATH"
  
  # Check if /usr/local/cuda points to the right place
  if [ -L "/usr/local/cuda" ]; then
    CURRENT_TARGET=$(readlink -f /usr/local/cuda)
    if [[ "${CURRENT_TARGET}" == "${CUDA_PREFIX}" ]]; then
      echo "[00] ✓ /usr/local/cuda correctly points to ${CUDA_PREFIX}"
    else
      echo "[00] Fixing /usr/local/cuda symlink to ${CUDA_PREFIX}"
      rm -f /usr/local/cuda
      ln -s "${CUDA_PREFIX}" /usr/local/cuda
    fi
  else
    ln -s "${CUDA_PREFIX}" /usr/local/cuda || true
  fi
  
  # Only set up custom ldconfig if we need to override existing libs
  NEED_LDCONFIG_OVERRIDE=false
  CURRENT_NVRTC=$(ldconfig -p | awk '/libnvrtc\.so\./{print $NF; exit}')
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
  echo "  libnvrtc.so: $(ldconfig -p | awk '/libnvrtc\.so\./{print $NF; exit}')"
  echo "  libcudart.so: $(ldconfig -p | awk '/libcudart\.so\./{print $NF; exit}')"
  
  # Set up persistent environment in ~/.bashrc for manual shell sessions
  grep -q "${CUDA_PREFIX}/bin" ~/.bashrc || echo "export PATH=\"${CUDA_PREFIX}/bin:\$PATH\"" >> ~/.bashrc
  grep -q "LD_LIBRARY_PATH=.*${CUDA_PREFIX}" ~/.bashrc || echo "export LD_LIBRARY_PATH=\"${CUDA_PREFIX}/lib64:${CUDA_PREFIX}/targets/x86_64-linux/lib:\${LD_LIBRARY_PATH:-}\"" >> ~/.bashrc
  grep -q "CUDA_HOME=" ~/.bashrc || echo "export CUDA_HOME=${CUDA_PREFIX}" >> ~/.bashrc
  grep -q "CUDA_PATH=" ~/.bashrc || echo "export CUDA_PATH=${CUDA_PREFIX}" >> ~/.bashrc
  grep -q "CUDA_ROOT=" ~/.bashrc || echo "export CUDA_ROOT=${CUDA_PREFIX}" >> ~/.bashrc
  grep -q "CUDA_COMPUTE_CAP=" ~/.bashrc || echo "export CUDA_COMPUTE_CAP=89  # L40S = sm_89" >> ~/.bashrc
fi

# Rust & optional uv
if ! command -v cargo >/dev/null 2>&1; then
  curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain stable
  echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
fi
export PATH="$HOME/.cargo/bin:$PATH"

if [ "${ENABLE_SMOKE_TEST}" = "1" ]; then
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  fi
  export PATH="$HOME/.local/bin:$PATH"
fi

# FD limits
bash -c 'cat >/etc/security/limits.d/moshi-nofile.conf <<EOF
* soft nofile 1048576
* hard nofile 1048576
EOF'
ulimit -n 1048576 || true

# OS/network tuning (optional)
if [ "${ENABLE_NET_TUNING}" = "1" ] && [ -w /proc/sys ]; then
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
else
  echo "[00] Skipping net tuning (ENABLE_NET_TUNING=0 or read-only fs)"
fi

echo "[00] cmake: $(cmake --version | head -n1 || echo N/A)"
echo "[00] nvcc:  $(nvcc --version | head -n1 || echo N/A)"
echo "[00] CUDA:  ${CUDA_PREFIX}"
echo "[00] opus:  $(pkg-config --modversion opus || echo N/A)"
echo "[00] Done."
