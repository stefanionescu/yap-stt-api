#!/usr/bin/env bash
# Docker environment configuration (matches env.lib.sh defaults exactly)

# CUDA environment (matches versioned paths from env.lib.sh)
export CUDA_MM="${CUDA_MM:-12.4}"
export CUDA_MM_PKG="${CUDA_MM_PKG:-12-4}"
export CUDA_PREFIX="${CUDA_PREFIX:-/usr/local/cuda-12.4}"
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-12.4}"
export CUDA_PATH="${CUDA_PATH:-/usr/local/cuda-12.4}"
export CUDA_ROOT="${CUDA_ROOT:-/usr/local/cuda-12.4}"
export CUDA_COMPUTE_CAP="${CUDA_COMPUTE_CAP:-89}"
export CUDARC_NVRTC_PATH="${CUDARC_NVRTC_PATH:-/usr/local/cuda-12.4/lib64/libnvrtc.so}"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-/usr/local/cuda-12.4/lib64:/usr/local/cuda-12.4/targets/x86_64-linux/lib}"

# Add CUDA to PATH (matches bare metal scripts)
export PATH="${CUDA_PREFIX}/bin:${PATH:-}"

# HuggingFace environment
export HF_HOME="${HF_HOME:-/workspace/hf_cache}"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"

# Yap server environment
export YAP_ADDR="${YAP_ADDR:-0.0.0.0}"
export YAP_PORT="${YAP_PORT:-8000}"
export YAP_LOG_DIR="${YAP_LOG_DIR:-/workspace/logs}"
export YAP_CLIENT_HOST="${YAP_CLIENT_HOST:-127.0.0.1}"
export YAP_CONFIG="${YAP_CONFIG:-/workspace/server/config-stt-en_fr-hf.toml}"
export TMUX_SESSION="${TMUX_SESSION:-yap-stt}"

# Optional features
# Smoke test controls (preserve backwards compat with ENABLE_SMOKE_TEST)
export ENABLE_SMOKE_TEST="${ENABLE_SMOKE_TEST:-0}"
export RUN_SMOKE_TEST="${RUN_SMOKE_TEST:-${ENABLE_SMOKE_TEST}}"
export SMOKETEST_RTF="${SMOKETEST_RTF:-1}"
