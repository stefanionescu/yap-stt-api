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
export PARAKEET_MODEL_ID=${PARAKEET_MODEL_ID:-nemo-parakeet-tdt-0.6b-v2}
export PARAKEET_MODEL_DIR=${PARAKEET_MODEL_DIR:-/models/parakeet-int8}
export HF_REPO_ID=${HF_REPO_ID:-istupakov/parakeet-tdt-0.6b-v2-onnx}
export HF_REVISION=${HF_REVISION:-main}
# Optional: export HF_TOKEN in your shell for authenticated downloads

# Caches (used if/when TensorRT EP is enabled in ORT build)
export TRT_ENGINE_CACHE=${TRT_ENGINE_CACHE:-/models/trt_cache}
export TRT_TIMING_CACHE=${TRT_TIMING_CACHE:-/models/timing.cache}
