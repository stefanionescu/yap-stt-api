#!/usr/bin/env bash
set -euo pipefail
echo "[00] Installing prerequisites…"

export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  build-essential git curl pkg-config libssl-dev ca-certificates \
  python3 python3-venv python3-pip ffmpeg tmux jq

# Rust toolchain
if ! command -v cargo >/dev/null 2>&1; then
  curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain stable
  # shellcheck disable=SC2016
  echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
  export PATH="$HOME/.cargo/bin:$PATH"
fi

# uv (Python task runner used by Kyutai scripts)
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # uv installs to ~/.local/bin
  # shellcheck disable=SC2016
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  export PATH="$HOME/.local/bin:$PATH"
fi

# Hugging Face cache
mkdir -p "${HF_HOME}"
# shellcheck disable=SC2016
grep -q 'HF_HOME' ~/.bashrc || echo 'export HF_HOME=/workspace/hf_cache' >> ~/.bashrc
# shellcheck disable=SC2016
grep -q 'HF_HUB_ENABLE_HF_TRANSFER' ~/.bashrc || echo 'export HF_HUB_ENABLE_HF_TRANSFER=1' >> ~/.bashrc

# Generous FD limit for lots of websockets
sudo bash -c 'cat >/etc/security/limits.d/moshi-nofile.conf <<EOF
* soft nofile 1048576
* hard nofile 1048576
EOF'
ulimit -n 1048576 || true

mkdir -p "${MOSHI_LOG_DIR}"
echo "[00] Prereqs installed."
