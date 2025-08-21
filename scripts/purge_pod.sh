#!/usr/bin/env bash
set -euo pipefail

PORT=${PORT:-8000}
TRT_ENGINE_CACHE=${TRT_ENGINE_CACHE:-/models/trt_cache}
TRT_TIMING_CACHE=${TRT_TIMING_CACHE:-/models/timing.cache}
ONNX_ASR_CACHE_DIR=${ONNX_ASR_CACHE_DIR:-"$HOME/.cache/onnx-asr"}
PIP_CACHE_DIR=${PIP_CACHE_DIR:-"$HOME/.cache/pip"}
VENV_DIR=${VENV_DIR:-".venv"}
MODELS_DIR_HOST=${MODELS_DIR_HOST:-"models"}
PARAKEET_MODEL_DIR=${PARAKEET_MODEL_DIR:-"/models/parakeet-int8"}

# Purge core artifacts by default (no flags needed). Docker uninstall is opt-in.
DO_LOGS=1
DO_ENGINES=1
DO_MODELS=1
DO_DEPS=1
SELECTIVE=0
DO_UNINSTALL_DOCKER=0
DO_REMOVE_DOCKER_USER=0

usage() {
  cat <<EOF
Usage: $0 [--logs] [--engines] [--models] [--deps] [--all] [--keep-docker] [--remove-docker-user]

Stops the FastAPI service and purges logs, caches, dependencies, and local model files.

Defaults: With no flags, purges core artifacts (logs, engines, models, deps). Docker is preserved.

Options (for selective purge):
  --logs       Remove logs/ and metrics logs (keeps directory)
  --engines    Remove TensorRT engine & timing caches (TRT_ENGINE_CACHE, TRT_TIMING_CACHE)
  --models     Remove onnx-asr model cache (~/.cache/onnx-asr), host ./models, and PARAKEET_MODEL_DIR
  --deps       Remove local Python venv (.venv) and pip cache (~/.cache/pip)
  --all        Purge ALL including Docker uninstall (use --keep-docker to retain Docker)

Additional:
  --keep-docker       Keep Docker installed even when using --all
  --remove-docker-user Remove the non-root Docker user (rdocker) and its home

Env:
  PORT (default: 8000)
  TRT_ENGINE_CACHE (default: /models/trt_cache)
  TRT_TIMING_CACHE (default: /models/timing.cache)
  ONNX_ASR_CACHE_DIR (default: ~/.cache/onnx-asr)
  PIP_CACHE_DIR (default: ~/.cache/pip)
  VENV_DIR (default: .venv)
  MODELS_DIR_HOST (default: ./models)
  PARAKEET_MODEL_DIR (default: /models/parakeet-int8)
EOF
}

for arg in "$@"; do
  case "$arg" in
    --help|-h) usage; exit 0 ;;
    --logs) SELECTIVE=1; DO_LOGS=1; DO_ENGINES=0; DO_MODELS=0; DO_DEPS=0 ;;
    --engines) SELECTIVE=1; DO_LOGS=0; DO_ENGINES=1; DO_MODELS=0; DO_DEPS=0 ;;
    --models) SELECTIVE=1; DO_LOGS=0; DO_ENGINES=0; DO_MODELS=1; DO_DEPS=0 ;;
    --deps) SELECTIVE=1; DO_LOGS=0; DO_ENGINES=0; DO_MODELS=0; DO_DEPS=1 ;;
    --all) SELECTIVE=0; DO_LOGS=1; DO_ENGINES=1; DO_MODELS=1; DO_DEPS=1; DO_UNINSTALL_DOCKER=1 ;;
    --keep-docker) DO_UNINSTALL_DOCKER=0 ;;
    --remove-docker-user) DO_REMOVE_DOCKER_USER=1 ;;
    *) echo "Unknown arg: $arg"; usage; exit 2 ;;
  esac
  shift || true
done

kill_by_pidfile() {
  local pidfile=$1
  if [[ -f "$pidfile" ]]; then
    local pid
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Killing PID $pid from $pidfile"
      kill "$pid" || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        echo "Force killing PID $pid"
        kill -9 "$pid" || true
      fi
    fi
    rm -f "$pidfile"
  fi
}

kill_uvicorn_by_pattern() {
  if command -v pgrep >/dev/null 2>&1; then
    local pids
    pids=$(pgrep -f "uvicorn .*src.server:app" || true)
    if [[ -n "$pids" ]]; then
      echo "Killing uvicorn PIDs: $pids"
      kill $pids || true
      sleep 1
      for p in $pids; do
        if kill -0 "$p" 2>/dev/null; then kill -9 "$p" || true; fi
      done
    fi
  fi
}

kill_by_port() {
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids=$(lsof -ti :"$PORT" || true)
    if [[ -n "$pids" ]]; then
      echo "Killing PIDs on port $PORT: $pids"
      kill $pids || true
      sleep 1
      for p in $pids; do
        if kill -0 "$p" 2>/dev/null; then kill -9 "$p" || true; fi
      done
    fi
  fi
}

echo "Stopping service..."
kill_by_pidfile logs/server.pid
kill_uvicorn_by_pattern
kill_by_port

echo "Service stopped. Beginning purge..."

if [[ $DO_LOGS -eq 1 ]]; then
  echo "Purging logs..."
  mkdir -p logs logs/metrics
  rm -f logs/*.log || true
  rm -f logs/metrics/*.log* || true
fi

if [[ $DO_ENGINES -eq 1 ]]; then
  echo "Purging TensorRT caches..."
  rm -rf "$TRT_ENGINE_CACHE" || true
  mkdir -p "$TRT_ENGINE_CACHE"
  rm -f "$TRT_TIMING_CACHE" || true
fi

if [[ $DO_MODELS -eq 1 ]]; then
  echo "Purging onnx-asr model cache at $ONNX_ASR_CACHE_DIR ..."
  rm -rf "$ONNX_ASR_CACHE_DIR" || true
  mkdir -p "$ONNX_ASR_CACHE_DIR"
  echo "Purging host models directory at $MODELS_DIR_HOST ..."
  rm -rf "$MODELS_DIR_HOST" || true
  mkdir -p "$MODELS_DIR_HOST"
  echo "Purging downloaded model at $PARAKEET_MODEL_DIR ..."
  rm -rf "$PARAKEET_MODEL_DIR" || true
fi

if [[ $DO_DEPS -eq 1 ]]; then
  echo "Removing virtualenv at $VENV_DIR and pip cache at $PIP_CACHE_DIR ..."
  rm -rf "$VENV_DIR" || true
  rm -rf "$PIP_CACHE_DIR" || true
fi

echo "Done."

if [[ $DO_UNINSTALL_DOCKER -eq 1 ]]; then
  echo "Attempting to uninstall Docker Engine and remove Docker data..."
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed or not in PATH. Skipping uninstall."
    exit 0
  fi
  docker compose down || true
  if command -v systemctl >/dev/null 2>&1; then
    systemctl stop docker || true
    systemctl stop containerd || true
  fi
  if command -v apt-get >/dev/null 2>&1; then
    apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras || true
    apt-get autoremove -y || true
    rm -f /etc/apt/sources.list.d/docker.list || true
    rm -f /etc/apt/keyrings/docker.gpg || true
    apt-get update -y || true
  else
    echo "apt-get not available; skipping package purge."
  fi
  rm -rf /var/lib/docker || true
  rm -rf /var/lib/containerd || true
  echo "Docker uninstall step completed."
fi

# Attempt to exit active virtualenv if running in the same shell (when sourced)
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  # If script is sourced, BASH_SOURCE[0] != $0, so deactivate will affect current shell
  if [[ "${BASH_SOURCE[0]:-}" != "$0" ]]; then
    deactivate 2>/dev/null || true
  else
    echo "NOTE: An active virtualenv was detected. To exit it in your current shell, run: deactivate" >&2
  fi
fi

# Optionally remove non-root Docker user
if [[ $DO_REMOVE_DOCKER_USER -eq 1 ]]; then
  if id -u rdocker >/dev/null 2>&1; then
    echo "Removing user 'rdocker' and its home..."
    userdel -r rdocker || true
  else
    echo "User 'rdocker' not found; skipping."
  fi
fi
