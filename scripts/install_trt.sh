#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Must be root or have sudo
if [[ $EUID -ne 0 ]] && ! command -v sudo >/dev/null 2>&1; then
  echo "ERROR: run as root or install sudo." >&2
  exit 1
fi
SUDO=""
if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

echo "OS release:"; cat /etc/os-release || true
echo "nvidia-smi:"; nvidia-smi || true

# Basics
$SUDO apt-get update -y
$SUDO apt-get install -y wget gnupg lsb-release ca-certificates

# Add CUDA + ML (TensorRT) repos
wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
$SUDO dpkg -i cuda-keyring_1.1-1_all.deb

wget -q https://developer.download.nvidia.com/compute/machine-learning/repos/ubuntu2204/x86_64/nvidia-machine-learning-repo-ubuntu2204_1.0.0-1_amd64.deb
$SUDO dpkg -i nvidia-machine-learning-repo-ubuntu2204_1.0.0-1_amd64.deb

$SUDO apt-get update -y

# cuDNN 9 for CUDA 12 runtime + headers
$SUDO apt-get install -y libcudnn9-cuda-12 libcudnn9-dev-cuda-12

# TensorRT 10 runtime + parsers
$SUDO apt-get install -y \
  libnvinfer10 libnvinfer-plugin10 libnvonnxparsers10 libnvparsers10 \
  python3-libnvinfer tensorrt

# Ensure library paths are visible
echo "/usr/lib/x86_64-linux-gnu" | $SUDO tee /etc/ld.so.conf.d/nvidia-trt.conf >/dev/null
$SUDO ldconfig

# Verify libs + ORT providers
python3 - <<'PY'
import ctypes, onnxruntime as ort
for lib in ["libnvinfer.so.10","libnvinfer_plugin.so.10"]:
    try:
        ctypes.CDLL(lib); print(lib, "OK")
    except OSError as e:
        print(lib, "MISSING:", e)
print("ORT available providers:", ort.get_available_providers())
PY

echo "Done. Set PARAKEET_USE_TENSORRT=1 to enable TRT EP."

