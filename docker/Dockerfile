# syntax=docker/dockerfile:1.6

# Complete Yap STT API Docker image that replicates scripts/main.sh functionality
# Includes: CUDA 12.4, Rust toolchain, yap-server binary, Python test clients, samples

ARG CUDA_VERSION=12.4.1
ARG UBUNTU_VERSION=22.04

# ------------ Base (CUDA development + all deps) ------------
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS base
ENV DEBIAN_FRONTEND=noninteractive

# Install all dependencies (replicates 00_prereqs.sh)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core build deps
    ca-certificates curl wget git build-essential pkg-config \
    libssl-dev libclang-dev clang cmake \
    # Python (for test clients and PyO3 bindings)
    python3 python3-pip python3-venv python3-dev \
    # Audio libraries (for opus crate)
    libopus-dev libopus0 \
    # Runtime utilities
    ffmpeg tmux net-tools iproute2 gnupg \
    && rm -rf /var/lib/apt/lists/*

# Set CUDA environment (matches env.lib.sh)
ENV CUDA_HOME=/usr/local/cuda \
    CUDA_PATH=/usr/local/cuda \
    CUDA_ROOT=/usr/local/cuda \
    CUDA_COMPUTE_CAP=89 \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda/targets/x86_64-linux/lib \
    CUDARC_NVRTC_PATH=/usr/local/cuda/lib64/libnvrtc.so

# Set Yap environment (matches env.lib.sh defaults)
ENV HF_HOME=/workspace/hf_cache \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    YAP_ADDR=0.0.0.0 \
    YAP_PORT=8000 \
    YAP_LOG_DIR=/workspace/logs \
    YAP_CLIENT_HOST=127.0.0.1 \
    YAP_CONFIG=/workspace/server/config-stt-en_fr-hf.toml \
    TMUX_SESSION=yap-stt

WORKDIR /workspace

# ------------ Install Rust toolchain ------------
FROM base AS rust
ARG RUST_VERSION=1.82.0
RUN curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain ${RUST_VERSION}
ENV PATH=/root/.cargo/bin:${PATH}

# ------------ Build yap-server (replicates 01_install_yap_server.sh) ------------
FROM rust AS builder
COPY server /workspace/server
WORKDIR /workspace/server

# Build with proper CUDA environment (matches 01_install_yap_server.sh)
RUN rm -f Cargo.lock && \
    cargo update --quiet && \
    RUST_BACKTRACE=1 cargo build --release --features cuda -p moshi-server

# ------------ Final runtime image ------------
FROM base AS final
LABEL org.opencontainers.image.title="yap-stt-api" \
      org.opencontainers.image.description="Yap STT Server Running Kyutai STT" \
      org.opencontainers.image.source="https://github.com/Yap-With-AI/moshi"

# Install Python test dependencies
COPY requirements.txt /workspace/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /workspace/requirements.txt

# Copy compiled yap-server binary
COPY --from=builder /workspace/server/target/release/yap-server /usr/local/bin/yap-server

# Copy server config and all necessary files
COPY server/config-stt-en_fr-hf.toml /workspace/server/config-stt-en_fr-hf.toml
COPY server/LICENSE /workspace/server/LICENSE

# Copy test clients (excluding client.py as requested) and samples
COPY test/warmup.py /workspace/test/warmup.py
COPY test/bench.py /workspace/test/bench.py
COPY test/utils/ /workspace/test/utils/
COPY test/clients/ /workspace/test/clients/
COPY samples/ /workspace/samples/

# Create required directories
RUN mkdir -p ${HF_HOME} ${YAP_LOG_DIR}

# Copy Docker scripts for container management
COPY docker/scripts/ /docker-scripts/
RUN chmod +x /docker-scripts/*.sh

# Expose port
EXPOSE 8000

# Use entrypoint for API key injection and server startup
ENTRYPOINT ["/docker-scripts/entrypoint.sh"]
CMD ["yap-server", "worker", "--config", "/workspace/server/config-stt-en_fr-hf.toml", "--addr", "0.0.0.0", "--port", "8000"]