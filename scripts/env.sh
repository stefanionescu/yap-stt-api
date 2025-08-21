#!/usr/bin/env bash
# Default environment for Parakeet service. Edit as needed.

export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8000}

# GPU + scheduling
export PARAKEET_REQUIRE_GPU=${PARAKEET_REQUIRE_GPU:-1}
export PARAKEET_NUM_LANES=${PARAKEET_NUM_LANES:-6}
export PARAKEET_QUEUE_MAX_FACTOR=${PARAKEET_QUEUE_MAX_FACTOR:-2}
export PARAKEET_MAX_QUEUE_WAIT_S=${PARAKEET_MAX_QUEUE_WAIT_S:-30}

# Limits
export PARAKEET_MAX_AUDIO_SECONDS=${PARAKEET_MAX_AUDIO_SECONDS:-600}
export PARAKEET_MAX_UPLOAD_MB=${PARAKEET_MAX_UPLOAD_MB:-64}

# Model selection
# Option A (recommended for performance): local INT8 model directory with files:
#   encoder-model.onnx, decoder_joint-model.onnx, vocab.txt
export PARAKEET_MODEL_DIR=${PARAKEET_MODEL_DIR:-./models/parakeet-int8}

# Option B: onnx-asr hub ids (fallback when no local dir)
export PARAKEET_MODEL_ID=${PARAKEET_MODEL_ID:-nemo-parakeet-tdt-0.6b-v2}
export PARAKEET_FALLBACK_MODEL_ID=${PARAKEET_FALLBACK_MODEL_ID:-istupakov/parakeet-tdt-0.6b-v2-onnx}
# Optional: export HF_TOKEN in your shell for authenticated downloads

# Caches (used if/when TensorRT EP is enabled in ORT build)
export TRT_ENGINE_CACHE=${TRT_ENGINE_CACHE:-/models/trt_cache}
export TRT_TIMING_CACHE=${TRT_TIMING_CACHE:-/models/timing.cache}

# Direct ONNX runtime path (own ORT providers; leave off to keep current path)
export PARAKEET_USE_DIRECT_ONNX=${PARAKEET_USE_DIRECT_ONNX:-1}
export PARAKEET_DEVICE_ID=${PARAKEET_DEVICE_ID:-0}
export PARAKEET_USE_TRT=${PARAKEET_USE_TRT:-1}
export ORT_INTRA_OP_NUM_THREADS=${ORT_INTRA_OP_NUM_THREADS:-1}

# Auto-fetch INT8 artifacts during setup (set to 0 to disable)
export AUTO_FETCH_INT8=${AUTO_FETCH_INT8:-1}

# CPU/GPU perf knobs
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}
export MKL_NUM_THREADS=${MKL_NUM_THREADS:-1}
export CUDA_MODULE_LOADING=${CUDA_MODULE_LOADING:-LAZY}
