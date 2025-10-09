# syntax=docker/dockerfile:1.6

# Multi-stage build for CUDA-enabled yap-server + Python test clients

ARG CUDA_VERSION=12.4.1
ARG UBUNTU_VERSION=22.04

# ------------ Base (CUDA development) ------------
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS base
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget git build-essential pkg-config \
    libssl-dev libclang-dev clang cmake python3 python3-pip python3-venv python3-dev \
    libopus-dev libopus0 \
    ffmpeg tmux net-tools iproute2 && \
    rm -rf /var/lib/apt/lists/*

# CUDA runtime envs
ENV CUDA_HOME=/usr/local/cuda \
    CUDA_PATH=/usr/local/cuda \
    CUDA_ROOT=/usr/local/cuda \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda/targets/x86_64-linux/lib

WORKDIR /workspace

# ------------ Rust toolchain ------------
FROM base AS rust
ARG RUST_VERSION=1.82.0
RUN curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain ${RUST_VERSION}
ENV PATH=/root/.cargo/bin:${PATH}

# ------------ Build yap-server ------------
FROM rust AS builder
# Set CUDA environment for build
ENV CUDA_COMPUTE_CAP=89 \
    CUDARC_NVRTC_PATH=/usr/local/cuda/lib64/libnvrtc.so
COPY server /workspace/server
WORKDIR /workspace/server
# Regenerate lockfile and build with CUDA features
RUN rm -f Cargo.lock && cargo update --quiet && \
    RUST_BACKTRACE=1 cargo build --release --features cuda -p moshi-server

# ------------ Final image ------------
FROM base AS final
LABEL org.opencontainers.image.title="yap-stt-api" \
      org.opencontainers.image.description="Yap STT Server with CUDA and test clients" \
      org.opencontainers.image.source="https://github.com/kyutai-labs/moshi"

# Install Python deps for test clients
COPY requirements.txt /workspace/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /workspace/requirements.txt

# Copy server binary and configs
COPY --from=builder /workspace/server/target/release/yap-server /usr/local/bin/yap-server
COPY server/config-stt-en_fr-hf.toml /workspace/server/config-stt-en_fr-hf.toml

# Copy test clients and samples for in-container testing
COPY test /workspace/test
COPY samples /workspace/samples

# Logs and cache dirs
ENV HF_HOME=/workspace/hf_cache \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    YAP_ADDR=0.0.0.0 \
    YAP_PORT=8000 \
    YAP_LOG_DIR=/workspace/logs \
    YAP_CLIENT_HOST=127.0.0.1

RUN mkdir -p ${HF_HOME} ${YAP_LOG_DIR}

# Entrypoint to inject KYUTAI_API_KEY into runtime config and start server
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["yap-server", "worker", "--config", "/workspace/server/config-stt-en_fr-hf.toml", "--addr", "0.0.0.0", "--port", "8000"]


