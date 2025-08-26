#!/usr/bin/env bash
set -euo pipefail

SUDO=""
if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

TRT_CUDA_SERIES="${TRT_CUDA_SERIES:-cuda12}"

echo "[tensorrt] Installing NVIDIA keyring"
wget -qO /tmp/cuda-keyring.deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
$SUDO dpkg -i /tmp/cuda-keyring.deb
rm -f /tmp/cuda-keyring.deb

echo "[tensorrt] Installing TensorRT runtime and dev packages (pinned to $TRT_CUDA_SERIES)"
$SUDO apt-get update -y

# Find latest versions that match the requested CUDA series (e.g., +cuda12.x)
TRT_V=$($SUDO apt-cache madison tensorrt 2>/dev/null | awk -v pat="$TRT_CUDA_SERIES" '$0 ~ pat {print $3; exit}')
DEV_V=$($SUDO apt-cache madison libnvinfer-dev 2>/dev/null | awk -v pat="$TRT_CUDA_SERIES" '$0 ~ pat {print $3; exit}')
PLG_V=$($SUDO apt-cache madison libnvinfer-plugin-dev 2>/dev/null | awk -v pat="$TRT_CUDA_SERIES" '$0 ~ pat {print $3; exit}')

if [ -n "$TRT_V" ] && [ -n "$DEV_V" ] && [ -n "$PLG_V" ]; then
  echo "[tensorrt] Selected versions: tensorrt=$TRT_V libnvinfer-dev=$DEV_V libnvinfer-plugin-dev=$PLG_V"
  $SUDO apt-get install -y \
    tensorrt="$TRT_V" \
    libnvinfer-dev="$DEV_V" \
    libnvinfer-plugin-dev="$PLG_V"
else
  echo "[tensorrt] Could not find $TRT_CUDA_SERIES variants via apt-cache; installing default packages"
  $SUDO apt-get install -y tensorrt libnvinfer-dev libnvinfer-plugin-dev
fi

echo "[tensorrt] Done. Re-run ./scripts/bootstrap.sh to build ORT with TRT EP if not already."


