# syntax=docker/dockerfile:1

# CUDA + cuDNN runtime base (no NGC login required)
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv python3-setuptools \
      ffmpeg sox libsndfile1 ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install, including TensorRT Python wheel for CUDA 12
COPY requirements.txt ./
RUN python3 -m pip install --upgrade pip wheel && \
    python3 -m pip install -r requirements.txt && \
    python3 -m pip install "tensorrt-cu12"

# Copy source
COPY . .

# Default envs (can be overridden at runtime)
ENV PARAKEET_MODEL_DIR=/models/parakeet-int8 \
    PARAKEET_USE_DIRECT_ONNX=1 \
    PARAKEET_USE_TENSORRT=1 \
    PARAKEET_DEVICE_ID=0 \
    ORT_INTRA_OP_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    CUDA_MODULE_LOADING=LAZY \
    TRT_ENGINE_CACHE=/models/trt_cache \
    TRT_TIMING_CACHE=/models/timing.cache \
    AUTO_FETCH_INT8=1

# Runtime entrypoint sets LD_LIBRARY_PATH for TRT wheel and starts uvicorn
RUN chmod +x scripts/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/bin/bash","-lc","scripts/entrypoint.sh"]

