#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
REPO="$ROOT/repos/sherpa-onnx"
BIN_OUT="$ROOT/bin"
ORT_VER="${ORT_VER:-1.18.0}"  # aligns with your ORT Python
CUDA_LIBS="${CUDA_LIBS:-/usr/local/cuda/lib64:/usr/local/cuda-12.8/lib64:/usr/lib/x86_64-linux-gnu}"

mkdir -p "$BIN_OUT" "$ROOT/deps" "$ROOT/logs"

# deps (ssl is needed by sherpa build; ALSA optional)
# Use sudo only if not running as root
if [ "$EUID" -eq 0 ]; then
  apt-get update -y
  apt-get install -y git cmake ninja-build build-essential pkg-config libssl-dev
else
  sudo apt-get update -y
  sudo apt-get install -y git cmake ninja-build build-essential pkg-config libssl-dev
fi

# clone at the tag that matches your pip (v1.12.10)
if [ ! -d "$REPO" ]; then
  git clone https://github.com/k2-fsa/sherpa-onnx.git "$REPO"
fi
cd "$REPO"
git fetch --tags
git checkout v1.12.10

# Download ONNX Runtime **GPU** prebuilt (shared libs)
cd "$ROOT/deps"
if [ ! -d "onnxruntime-gpu-${ORT_VER}" ]; then
  TARBALL="onnxruntime-linux-x64-gpu-${ORT_VER}.tgz"
  curl -L -o "$TARBALL" "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VER}/${TARBALL}"
  mkdir -p "onnxruntime-gpu-${ORT_VER}"
  tar -xzf "$TARBALL" -C "onnxruntime-gpu-${ORT_VER}" --strip-components=1
fi
ORT_ROOT="$ROOT/deps/onnxruntime-gpu-${ORT_VER}"

# Configure + build (GPU, WebSocket, use the preinstalled ORT we just downloaded)
cd "$REPO"
rm -rf build
cmake -S . -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DSHERPA_ONNX_ENABLE_WEBSOCKET=ON \
  -DSHERPA_ONNX_ENABLE_GPU=ON \
  -DSHERPA_ONNX_USE_PRE_INSTALLED_ONNXRUNTIME_IF_AVAILABLE=ON \
  -Dlocation_onnxruntime_header_dir="${ORT_ROOT}/include" \
  -Dlocation_onnxruntime_lib="${ORT_ROOT}/lib" \
  -DSHERPA_ONNX_ENABLE_BINARY=ON
cmake --build build -j

# Copy the websocket server binary out to ./bin
cp build/bin/sherpa-onnx-online-websocket-server "$BIN_OUT/"

# Record a small env file so the binary can find CUDA/ORT libs at runtime
ENVFILE="$ROOT/.env.sherpa_ws"
cat > "$ENVFILE" <<EOF
export LD_LIBRARY_PATH="${ORT_ROOT}/lib:${CUDA_LIBS}:\${LD_LIBRARY_PATH}"
EOF

echo "[build] Done. Binary: $BIN_OUT/sherpa-onnx-online-websocket-server"
echo "[build] Source this before running:  source $ENVFILE"
