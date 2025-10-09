# syntax=docker/dockerfile:1.6

# Complete Yap STT API Docker image that replicates scripts/main.sh functionality
# Includes: CUDA 12.4, Rust toolchain, yap-server binary, Python test clients, samples
#
# Build leverages .dockerignore for clean copying:
#   ✅ Includes: server/, test/ (minus client.py), samples/, requirements.txt
#   ❌ Excludes: scripts/, .env files, build artifacts, cache files, test/client.py

ARG CUDA_VERSION=12.4.1
ARG UBUNTU_VERSION=22.04

# ------------ Base (CUDA development + all deps) ------------
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS base
ENV DEBIAN_FRONTEND=noninteractive

# Install all dependencies (replicates 00_prereqs.sh exactly)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core build deps (matches 00_prereqs.sh)
    build-essential git curl pkg-config libssl-dev ca-certificates \
    cmake libopus-dev tmux gnupg ffmpeg \
    # Extra for Docker convenience
    wget libclang-dev clang net-tools iproute2 \
    # Python (always install for tests, matches ENABLE_SMOKE_TEST=1)
    python3 python3-pip python3-venv python3-dev \
    # Audio libraries
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv (matches 00_prereqs.sh with ENABLE_SMOKE_TEST=1)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

# Set file descriptor limits (matches 00_prereqs.sh)
RUN echo '* soft nofile 1048576' > /etc/security/limits.d/moshi-nofile.conf && \
    echo '* hard nofile 1048576' >> /etc/security/limits.d/moshi-nofile.conf

# Optional network tuning (matches 00_prereqs.sh ENABLE_NET_TUNING=1)
RUN echo 'net.core.somaxconn = 4096' > /etc/sysctl.d/99-moshi-net.conf && \
    echo 'net.ipv4.tcp_max_syn_backlog = 8192' >> /etc/sysctl.d/99-moshi-net.conf && \
    echo 'net.core.netdev_max_backlog = 16384' >> /etc/sysctl.d/99-moshi-net.conf && \
    echo 'net.ipv4.ip_local_port_range = 10240 65000' >> /etc/sysctl.d/99-moshi-net.conf && \
    echo 'net.ipv4.tcp_fin_timeout = 15' >> /etc/sysctl.d/99-moshi-net.conf && \
    echo 'net.ipv4.tcp_tw_reuse = 1' >> /etc/sysctl.d/99-moshi-net.conf && \
    echo 'net.core.rmem_max = 67108864' >> /etc/sysctl.d/99-moshi-net.conf && \
    echo 'net.core.wmem_max = 67108864' >> /etc/sysctl.d/99-moshi-net.conf

# Set CUDA environment (matches env.lib.sh exactly)
ENV CUDA_MM=12.4 \
    CUDA_MM_PKG=12-4 \
    CUDA_PREFIX=/usr/local/cuda-12.4 \
    CUDA_HOME=/usr/local/cuda-12.4 \
    CUDA_PATH=/usr/local/cuda-12.4 \
    CUDA_ROOT=/usr/local/cuda-12.4 \
    CUDA_COMPUTE_CAP=89 \
    LD_LIBRARY_PATH=/usr/local/cuda-12.4/lib64:/usr/local/cuda-12.4/targets/x86_64-linux/lib \
    CUDARC_NVRTC_PATH=/usr/local/cuda-12.4/lib64/libnvrtc.so

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

# ------------ Install Rust toolchain (matches 00_prereqs.sh exactly) ------------
FROM base AS rust
# Install latest stable Rust (matches bare metal: --default-toolchain stable)
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain stable
ENV PATH=/root/.cargo/bin:${PATH}

# ------------ Build yap-server (replicates 01_install_yap_server.sh) ------------
FROM rust AS builder
# Copy server source (.dockerignore excludes target/ build artifacts)
COPY server/ /workspace/server/
WORKDIR /workspace/server

# Build with proper CUDA environment (matches 01_install_yap_server.sh exactly)
RUN rm -f Cargo.lock && \
    cargo update --quiet && \
    RUST_BACKTRACE=1 cargo build --release --features cuda -p moshi-server

# ------------ Final runtime image ------------
FROM base AS final
LABEL org.opencontainers.image.title="yap-stt-api" \
      org.opencontainers.image.description="Yap STT Server Running Kyutai STT" \
      org.opencontainers.image.source="https://github.com/Yap-With-AI/moshi"

# Copy compiled yap-server binary
COPY --from=builder /workspace/server/target/release/yap-server /usr/local/bin/yap-server

# Copy application files (leveraging .dockerignore for exclusions)
# .dockerignore excludes: scripts/, .env files, build artifacts, test/client.py, etc.
COPY requirements.txt /workspace/
COPY server/ /workspace/server/
COPY test/ /workspace/test/
COPY samples/ /workspace/samples/

# Install Python test dependencies using uv (matches bare metal)
RUN uv pip install --system --no-cache -r /workspace/requirements.txt

# Create required directories
RUN mkdir -p ${HF_HOME} ${YAP_LOG_DIR}

# Copy Docker scripts for container management
COPY docker/scripts/ /docker-scripts/
RUN chmod +x /docker-scripts/*.sh

# Expose port
EXPOSE 8000

# Use start for API key injection and server startup (matches 03_start_server.sh)
ENTRYPOINT ["/docker-scripts/start.sh"]
CMD ["yap-server", "worker", "--config", "/workspace/server/config-stt-en_fr-hf.toml", "--addr", "0.0.0.0", "--port", "8000"]