#!/usr/bin/env bash
# Default environment for Parakeet service. Edit as needed.

export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8000}

# GPU + scheduling
export PARAKEET_REQUIRE_GPU=${PARAKEET_REQUIRE_GPU:-1}
export PARAKEET_QUEUE_MAX_FACTOR=${PARAKEET_QUEUE_MAX_FACTOR:-16}
export PARAKEET_MAX_QUEUE_WAIT_S=${PARAKEET_MAX_QUEUE_WAIT_S:-2}
export PARAKEET_MICROBATCH_WINDOW_MS=${PARAKEET_MICROBATCH_WINDOW_MS:-4}
export PARAKEET_MICROBATCH_MAX_BATCH=${PARAKEET_MICROBATCH_MAX_BATCH:-16}

# Limits
export PARAKEET_MAX_AUDIO_SECONDS=${PARAKEET_MAX_AUDIO_SECONDS:-600}
export PARAKEET_MAX_UPLOAD_MB=${PARAKEET_MAX_UPLOAD_MB:-64}

# Model selection (FP32 directory by default)
# Ensure absolute path to avoid runtime cwd issues
_DEFAULT_MODEL_DIR="./models/parakeet-fp32"
if [[ -z "${PARAKEET_MODEL_DIR:-}" ]]; then
  # Create the directory if it doesn't exist to ensure path resolution works
  mkdir -p "${_DEFAULT_MODEL_DIR}"
  if command -v readlink >/dev/null 2>&1; then
    export PARAKEET_MODEL_DIR="$(readlink -f "${_DEFAULT_MODEL_DIR}")"
  else
    # macOS: emulate readlink -f
    export PARAKEET_MODEL_DIR="$(cd "${_DEFAULT_MODEL_DIR}" && pwd)"
  fi
fi
export PARAKEET_MODEL_NAME=${PARAKEET_MODEL_NAME:-nemo-parakeet-tdt-0.6b-v2}
export PARAKEET_FP32_REPO=${PARAKEET_FP32_REPO:-istupakov/parakeet-tdt-0.6b-v2-onnx}

# Option B: onnx-asr hub ids (fallback when no local dir)
export PARAKEET_MODEL_ID=${PARAKEET_MODEL_ID:-nemo-parakeet-tdt-0.6b-v2}
export PARAKEET_FALLBACK_MODEL_ID=${PARAKEET_FALLBACK_MODEL_ID:-istupakov/parakeet-tdt-0.6b-v2-onnx}
# Optional: export HF_TOKEN in your shell for authenticated downloads

# Caches (used if/when TensorRT EP is enabled in ORT build)
export TRT_ENGINE_CACHE=${TRT_ENGINE_CACHE:-/models/trt_cache}
export TRT_TIMING_CACHE=${TRT_TIMING_CACHE:-/models/timing.cache}

export PARAKEET_DEVICE_ID=${PARAKEET_DEVICE_ID:-0}
# Prefer the more explicit flag name; PARAKEET_USE_TRT remains supported via src/config.py
export PARAKEET_USE_TENSORRT=${PARAKEET_USE_TENSORRT:-1}
export ORT_INTRA_OP_NUM_THREADS=${ORT_INTRA_OP_NUM_THREADS:-1}

# Auto-fetch FP32 artifacts during setup
export AUTO_FETCH_FP32=${AUTO_FETCH_FP32:-1}
# Optional: install TRT runtime via apt during setup (Ubuntu 22.04 pods). Disabled by default when wheel is present.
export INSTALL_TRT=${INSTALL_TRT:-0}

# CPU/GPU perf knobs
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-6}
export MKL_NUM_THREADS=${MKL_NUM_THREADS:-6}
export OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-6}
export CUDA_MODULE_LOADING=${CUDA_MODULE_LOADING:-LAZY}
