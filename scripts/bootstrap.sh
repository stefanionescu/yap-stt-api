#!/usr/bin/env bash
set -euo pipefail

# --- SETTINGS ---
ROOT="${ROOT:-$(pwd)}"
PY=python3
ORT_TAG="${ORT_TAG:-v1.18.0}"     # stable with CUDA 12.x
BATCH_DEPS="git cmake ninja-build build-essential pkg-config libsndfile1 ffmpeg curl"

mkdir -p "$ROOT"/{models,repos,logs,trt_cache}
cd "$ROOT"

echo "[1/8] Install system packages"
SUDO=""
if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
$SUDO apt-get update -y
$SUDO apt-get install -y $BATCH_DEPS

echo "[2/8] Python venv + core wheels"
$PY -m venv .venv
source .venv/bin/activate
echo 'export OMP_NUM_THREADS=1' >> "$ROOT/.venv/bin/activate"
echo 'ulimit -n 131072 || true' >> "$ROOT/.venv/bin/activate"
pip install --upgrade pip wheel setuptools
# CUDA EP first; we may replace with a TRT-EP build later
pip install "numpy<2.0" onnx==1.18.0 onnxruntime-gpu==1.22.0 fastapi uvicorn websockets soundfile

echo "[3/8] Install sherpa-onnx from PyPI + clone repo for server scripts"
pip install "sherpa-onnx==1.12.10"
if [ ! -d repos/sherpa-onnx ]; then
  git clone https://github.com/k2-fsa/sherpa-onnx.git repos/sherpa-onnx
fi

# Add CUDA library paths to venv for runtime
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:/usr/local/cuda/lib64:/usr/local/cuda-12.8/targets/x86_64-linux/lib:/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH' >> "$ROOT/.venv/bin/activate"

echo "[4/8] Download Streaming NeMo CTC 80ms ONNX pack (pre-converted)"
# These tarballs are the streaming CTC exports (80/480/1040 ms). We use 80ms.
cd models
if [ ! -d nemo_ctc_80ms ]; then
  mkdir -p nemo_ctc_80ms && cd nemo_ctc_80ms

  PRIMARY="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-streaming-fast-conformer-ctc-en-80ms.tar.bz2"
  FALLBACK="https://github.com/csukuangfj/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-streaming-fast-conformer-ctc-en-80ms.tar.bz2"

  fetch() {
    URL="$1"
    echo "  -> fetching: $URL"
    curl -L --retry 4 --retry-all-errors -o pack.tar.bz2 "$URL" || return 1
    [ -s pack.tar.bz2 ] || return 1
    tar -tjf pack.tar.bz2 >/dev/null 2>&1 || return 1
    return 0
  }

  if ! fetch "$PRIMARY"; then
    echo "  !! primary failed; trying fallback mirror"
    rm -f pack.tar.bz2
    fetch "$FALLBACK" || { echo "  !! failed to download model pack"; exit 2; }
  fi

  tar xf pack.tar.bz2 --strip-components=1
  rm -f pack.tar.bz2
  cd ..
fi
cd "$ROOT"

echo "[5/8] Skipping TensorRT EP build (using CUDA EP for simplicity)"
# TensorRT EP can be added later for additional performance if needed

echo "[6/8] Download PnC model (optional)"
cd models
if [ ! -d pnc ]; then
  mkdir -p pnc
fi
cd pnc
if [ ! -f model.onnx ]; then
  curl -L -o pnc.tar.bz2 \
    https://github.com/k2-fsa/sherpa-onnx/releases/download/punctuation-models/sherpa-onnx-online-punct-en-2024-08-06.tar.bz2
  tar xf pnc.tar.bz2 --strip-components=1
  rm -f pnc.tar.bz2
fi
cd "$ROOT"

echo "[7/9] Tiny sanity check (load model + list I/O)"
python - <<'PY'
import onnxruntime as ort, os
sess = ort.InferenceSession(os.path.join("models","nemo_ctc_80ms","model.onnx"),
                            providers=["CUDAExecutionProvider","CPUExecutionProvider"])
print("Providers:", sess.get_providers())
print("Inputs:", [i.name for i in sess.get_inputs()])
print("Outputs:", [o.name for o in sess.get_outputs()])
PY

echo "[8/9] Build C++ WebSocket server"
bash "$ROOT/scripts/build_ws_server.sh"

echo "[9/9] Done. Use ./scripts/start_server.sh to run the WS server."


