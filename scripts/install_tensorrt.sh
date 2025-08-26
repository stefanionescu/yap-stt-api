#!/usr/bin/env bash
set -euo pipefail

SUDO=""
if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

echo "[tensorrt] Installing NVIDIA keyring"
wget -qO /tmp/cuda-keyring.deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
$SUDO dpkg -i /tmp/cuda-keyring.deb
rm -f /tmp/cuda-keyring.deb

echo "[tensorrt] Installing TensorRT runtime and dev packages"
$SUDO apt-get update -y
$SUDO apt-get install -y tensorrt libnvinfer-dev libnvinfer-plugin-dev

echo "[tensorrt] Done. Re-run ./scripts/bootstrap.sh to build ORT with TRT EP if not already."


