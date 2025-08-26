#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"

# Options:
#   --trt       Purge TensorRT packages installed via install_tensorrt.sh
#   --trt-all   Also remove cuda-keyring and CUDA repo entries

PURGE_TRT=0
PURGE_CUDA_REPO=0
for arg in "${@:-}"; do
  case "$arg" in
    --trt) PURGE_TRT=1 ;;
    --trt-all) PURGE_TRT=1; PURGE_CUDA_REPO=1 ;;
    --help|-h)
      echo "Usage: $0 [--trt | --trt-all]"
      echo "  --trt      Purge TensorRT packages (tensorrt, libnvinfer*)"
      echo "  --trt-all  Also remove cuda-keyring and CUDA APT repo entries"
      exit 0
      ;;
  esac
done

SUDO=""
if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

# Kill server if running
if [ -f "$ROOT/server.pid" ]; then
  PID=$(cat "$ROOT/server.pid" || true)
  if [ -n "${PID:-}" ] && ps -p "$PID" > /dev/null 2>&1; then
    echo "[stop] Killing PID $PID"
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$ROOT/server.pid"
fi

# Wipe everything created by bootstrap
echo "[wipe] Removing venv, repos, models, logs, TRT cache"
rm -rf "$ROOT/.venv" \
       "$ROOT/repos" \
       "$ROOT/models" \
       "$ROOT/logs" \
       "$ROOT/trt_cache"

if [ $PURGE_TRT -eq 1 ]; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "[wipe] Purging TensorRT packages (this affects system packages)"
    # Try broad patterns; ignore failures if not installed
    $SUDO apt-get purge -y 'tensorrt' 'libnvinfer*' 'libnvinfer-plugin*' || true
    # Some TRT installs pull CUDA 12.x components; attempt to purge common dependents (safe no-ops if absent)
    $SUDO apt-get purge -y 'cuda-cudart-*' 'cuda-nvrtc-*' 'libnvjitlink*' 'libcublas*' 'libcurand*' 'libcufft*' 'libcusolver*' 'libcusparse*' 'libcudnn*' 'libcutensor*' || true
    $SUDO apt-get autoremove -y || true
    $SUDO apt-get clean || true
    # Remove apt caches and lists to reclaim space
    $SUDO rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/* || true
    # Clear user caches (pip, onnxruntime) if present
    PIP_BIN=$(command -v pip || true)
    if [ -n "${PIP_BIN:-}" ]; then $PIP_BIN cache purge || true; fi
    rm -rf "$HOME/.cache/pip" "$HOME/.cache/onnxruntime" "$HOME/.cache"/*trt* || true
  else
    echo "[warn] apt-get not found; cannot purge system TensorRT packages"
  fi
fi

if [ $PURGE_CUDA_REPO -eq 1 ]; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "[wipe] Removing CUDA APT repo entries and cuda-keyring"
    $SUDO apt-get purge -y cuda-keyring || true
    $SUDO rm -f /etc/apt/sources.list.d/cuda* || true
    $SUDO rm -f /etc/apt/trusted.gpg.d/cuda* || true
    $SUDO apt-get update -y || true
    # Also drop apt lists to reclaim disk
    $SUDO rm -rf /var/lib/apt/lists/* || true
  fi
fi

echo "[wipe] Done. Re-run ./scripts/bootstrap.sh to rebuild."


