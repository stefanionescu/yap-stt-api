#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(pwd)}"
REPO="$ROOT/repos/sherpa-onnx"
BIN_OUT="$ROOT/bin"
ORT_VER="${ORT_VER:-1.18.0}"   # matches your Python ORT major/minor
CUDA_LIBS_DEFAULT="/usr/local/cuda/lib64:/usr/local/cuda-12.8/lib64:/usr/lib/x86_64-linux-gnu"

mkdir -p "$BIN_OUT" "$ROOT/deps" "$ROOT/logs"

# deps
if [ "${EUID:-0}" -eq 0 ]; then
  apt-get update -y
  apt-get install -y git cmake ninja-build build-essential pkg-config libssl-dev curl
else
  sudo apt-get update -y
  sudo apt-get install -y git cmake ninja-build build-essential pkg-config libssl-dev curl
fi

# clone sherpa-onnx at the tag you used via pip (v1.12.10)
if [ ! -d "$REPO" ]; then
  git clone https://github.com/k2-fsa/sherpa-onnx.git "$REPO"
fi
cd "$REPO"
git fetch --tags
git checkout v1.12.10

# Download official ONNX Runtime GPU (shared libs)
cd "$ROOT/deps"
if [ ! -d "onnxruntime-gpu-${ORT_VER}" ]; then
  TARBALL="onnxruntime-linux-x64-gpu-${ORT_VER}.tgz"
  curl -L -o "$TARBALL" "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VER}/${TARBALL}"
  mkdir -p "onnxruntime-gpu-${ORT_VER}"
  tar -xzf "$TARBALL" -C "onnxruntime-gpu-${ORT_VER}" --strip-components=1
fi

ORT_ROOT="$ROOT/deps/onnxruntime-gpu-${ORT_VER}"
ORT_INC="$ORT_ROOT/include"
ORT_LIBDIR="$ORT_ROOT/lib"
ORT_LIB="$ORT_LIBDIR/libonnxruntime.so"
ORT_CUDA_LIB="$ORT_LIBDIR/libonnxruntime_providers_cuda.so"

# sanity check
[ -f "$ORT_LIB" ] || { echo "Missing $ORT_LIB"; exit 3; }
[ -f "$ORT_CUDA_LIB" ] || { echo "Missing $ORT_CUDA_LIB"; exit 3; }

# Configure + build (GPU, WebSocket) linking to actual .so files
cd "$REPO"
rm -rf build
cmake -S . -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DSHERPA_ONNX_ENABLE_WEBSOCKET=ON \
  -DSHERPA_ONNX_ENABLE_GPU=ON \
  -DSHERPA_ONNX_USE_PRE_INSTALLED_ONNXRUNTIME_IF_AVAILABLE=ON \
  -Dlocation_onnxruntime_header_dir="$ORT_INC" \
  -Dlocation_onnxruntime_lib="$ORT_LIB" \
  -Dlocation_onnxruntime_cuda_lib="$ORT_CUDA_LIB" \
  -DCMAKE_EXE_LINKER_FLAGS="-L$ORT_LIBDIR" \
  -DSHERPA_ONNX_ENABLE_BINARY=ON

cmake --build build -j

# Copy the websocket server binary out to ./bin
cp build/bin/sherpa-onnx-online-websocket-server "$BIN_OUT/"

# Record env file so the binary can find ORT/CUDA libs at runtime
ENVFILE="$ROOT/.env.sherpa_ws"
cat > "$ENVFILE" <<EOF
export LD_LIBRARY_PATH="$ORT_LIBDIR:${CUDA_LIBS:-$CUDA_LIBS_DEFAULT}:\${LD_LIBRARY_PATH:-}"
EOF

echo "[build] Done. Binary: $BIN_OUT/sherpa-onnx-online-websocket-server"
echo "[build] Source this before running:  source $ENVFILE"
