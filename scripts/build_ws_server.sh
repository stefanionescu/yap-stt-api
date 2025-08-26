#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$(pwd)}"
SUDO=""
command -v sudo >/dev/null 2>&1 && SUDO="sudo"

# deps for C++ build + websocket (openssl)
$SUDO apt-get update -y
$SUDO apt-get install -y git cmake ninja-build build-essential pkg-config libssl-dev

# clone (or reuse) repo
mkdir -p "$ROOT/repos"
cd "$ROOT/repos"
if [ ! -d sherpa-onnx ]; then
  git clone https://github.com/k2-fsa/sherpa-onnx.git sherpa-onnx
fi

cd sherpa-onnx
# optional: stay near your Python wheel version to avoid surprises
git fetch --all --tags
git checkout v1.12.10 || true

# out-of-tree build
mkdir -p build && cd build
cmake -GNinja -DCMAKE_BUILD_TYPE=Release \
      -DSHERPA_ONNX_ENABLE_CUDA=ON \
      -DSHERPA_ONNX_ENABLE_WEBSOCKET=ON \
      -DBUILD_SHARED_LIBS=OFF \
      -DSHERPA_ONNX_ENABLE_PYTHON=OFF \
      ..
ninja -j"$(nproc)"

# expose the server in a stable path
mkdir -p "$ROOT/bin"
cp -f bin/sherpa-onnx-online-websocket-server "$ROOT/bin/"
echo "[build] sherpa-onnx-online-websocket-server -> $ROOT/bin/"
