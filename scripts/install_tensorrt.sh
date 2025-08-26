#!/usr/bin/env bash
set -euo pipefail

echo "[tensorrt] Installing NVIDIA keyring"
wget -qO /tmp/cuda-keyring.deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i /tmp/cuda-keyring.deb
rm -f /tmp/cuda-keyring.deb

echo "[tensorrt] Installing TensorRT runtime and dev packages"
sudo apt-get update -y
sudo apt-get install -y tensorrt libnvinfer-dev libnvinfer-plugin-dev

echo "[tensorrt] Done. Re-run ./scripts/bootstrap.sh to build ORT with TRT EP if not already."


