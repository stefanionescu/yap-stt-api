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
pip install onnx onnxruntime-gpu==1.18.0 fastapi uvicorn websockets soundfile numpy

echo "[3/8] Install sherpa-onnx from PyPI + clone repo for server scripts"
pip install "sherpa-onnx==1.12.10"
if [ ! -d repos/sherpa-onnx ]; then
  git clone https://github.com/k2-fsa/sherpa-onnx.git repos/sherpa-onnx
fi

# Force TRT EP preference in the streaming WS server if available.
# Do it via inline Python to avoid sed escaping issues and survive whitespace changes.
python - <<'PY'
import pathlib, re
root = pathlib.Path(__file__).resolve().parents[1]
srv = root / 'repos' / 'sherpa-onnx' / 'python-api-examples' / 'streaming_server.py'
try:
    text = srv.read_text(encoding='utf-8')
except Exception:
    print('[patch] streaming_server.py not found; skipping provider patch')
else:
    pat = re.compile(r"providers\s*=\s*\[provider\]")
    rep = "providers=[('TensorrtExecutionProvider', {'trt_fp16_enable': True, 'trt_engine_cache_enable': True, 'trt_engine_cache_path': r'%s/trt_cache', 'trt_max_workspace_size': 8589934592}), 'CUDAExecutionProvider', 'CPUExecutionProvider']" % root.as_posix()
    new = pat.sub(rep, text, count=1)
    if new != text:
        srv.write_text(new, encoding='utf-8')
        print('[patch] Injected TRT->CUDA->CPU providers into streaming_server.py')
    else:
        print('[patch] Pattern not found; file may already be patched or changed. Skipping.')
PY

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

echo "[5/8] (Optional) Detect TensorRT and build ONNX Runtime with TRT EP"
# If TensorRT SDK is installed (libnvinfer.so exists), build ORT with TRT EP and install the wheel
TRT_SO=$(ldconfig -p | grep -m1 libnvinfer.so || true)
if [ -n "$TRT_SO" ]; then
  echo "  -> TensorRT detected: $TRT_SO"
  echo "     Building ONNX Runtime $ORT_TAG with TensorRT EP..."
  cd repos
  if [ ! -d onnxruntime ]; then
    git clone --recursive https://github.com/microsoft/onnxruntime.git
  fi
  cd onnxruntime
  git fetch --all --tags
  git checkout $ORT_TAG
  git submodule update --init --recursive

  # infer default paths for CUDA/cuDNN/TRT on Ubuntu 22.04
  # Prefer CUDA 12.x if present; override by exporting CUDA_HOME before running
  if [ -z "${CUDA_HOME:-}" ]; then
    for C in /usr/local/cuda-12.* /usr/local/cuda; do
      if [ -d "$C" ]; then CUDA_HOME="$C"; break; fi
    done
  fi
  CUDNN_HOME=${CUDNN_HOME:-/usr/lib/x86_64-linux-gnu}
  # libnvinfer is typically under /usr/lib/x86_64-linux-gnu; tweak if custom
  TENSORRT_HOME=${TENSORRT_HOME:-/usr/lib/x86_64-linux-gnu}

  ./build.sh --config Release --build_wheel --parallel --skip_tests \
    --update --build \
    --use_tensorrt --tensorrt_home "$TENSORRT_HOME" \
    --cuda_home "$CUDA_HOME" --cudnn_home "$CUDNN_HOME"

  WHEEL=$(ls build/Linux/Release/dist/onnxruntime_gpu-*.whl | tail -n1)
  echo "  -> Installing ORT wheel with TRT EP: $WHEEL"
  pip uninstall -y onnxruntime-gpu || true
  pip install "$WHEEL"

  # set EP env for runtime
  echo "export ORT_TENSORRT_ENGINE_CACHE_ENABLE=1"  >> "$ROOT/.venv/bin/activate"
  echo "export ORT_TENSORRT_CACHE_PATH=$ROOT/trt_cache" >> "$ROOT/.venv/bin/activate"
  echo "export ORT_TENSORRT_FP16_ENABLE=1"         >> "$ROOT/.venv/bin/activate"
  echo "export ORT_TENSORRT_MAX_WORKSPACE_SIZE=8589934592" >> "$ROOT/.venv/bin/activate"
  cd "$ROOT"
else
  echo "  -> TensorRT not detected. Using CUDA EP for now. You can apt-install TensorRT and rerun bootstrap."
fi

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

echo "[7/8] Tiny sanity check (load model + list I/O)"
python - <<'PY'
import onnxruntime as ort, os
sess = ort.InferenceSession(os.path.join("models","nemo_ctc_80ms","model.onnx"),
                            providers=["TensorrtExecutionProvider","CUDAExecutionProvider","CPUExecutionProvider"])
print("Providers:", sess.get_providers())
print("Inputs:", [i.name for i in sess.get_inputs()])
print("Outputs:", [o.name for o in sess.get_outputs()])
PY

echo "[8/8] Done. Use ./scripts/start_server.sh to run the WS server."


