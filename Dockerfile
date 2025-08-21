FROM nvcr.io/nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg sox libsndfile1-dev ca-certificates python3-pip curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    TRT_ENGINE_CACHE=/models/trt_cache \
    TRT_TIMING_CACHE=/models/timing.cache \
    HOST=0.0.0.0 PORT=8000 PARAKEET_NUM_LANES=6 \
    PARAKEET_MODEL_DIR=/models/parakeet-int8

EXPOSE 8000
CMD ["bash", "scripts/entrypoint.sh"]
