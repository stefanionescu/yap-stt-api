#!/usr/bin/env bash
set -euo pipefail

PORT=${PORT:-8000}
HUGGINGFACE_CACHE_DIR=${HUGGINGFACE_CACHE_DIR:-"$HOME/.cache/huggingface"}
TORCH_CACHE_DIR=${TORCH_CACHE_DIR:-"$HOME/.cache/torch"}
PIP_CACHE_DIR=${PIP_CACHE_DIR:-"$HOME/.cache/pip"}
VENV_DIR=${VENV_DIR:-".venv"}
MODELS_DIR_HOST=${MODELS_DIR_HOST:-"models"}
 
# Purge core artifacts by default (no flags needed).
DO_LOGS=1
DO_ENGINES=1
DO_MODELS=1
DO_DEPS=1
DO_APT_CLEAN=1
DO_UNINSTALL_SYS_PY=1
DO_DU_REPORT=1
SELECTIVE=0
DO_UNINSTALL_TRT=0

usage() {
  cat <<EOF
Usage: $0 [--logs] [--models] [--deps] [--all]

Stops the gRPC service and purges logs, caches, dependencies, and local model files.

Defaults: With no flags, purges core artifacts (logs, models, deps).

Options (for selective purge):
  --logs       Remove logs/ and metrics logs (keeps directory)
  --models     Remove NeMo/Hugging Face caches (~/.cache) and host ./models
  --deps       Remove local Python venv (.venv) and pip cache (~/.cache/pip)
  --all        Do all of the above (same as no flags)

Env:
  PORT (default: 8000)
 
  PIP_CACHE_DIR (default: ~/.cache/pip)
  VENV_DIR (default: .venv)
  MODELS_DIR_HOST (default: ./models)
  
EOF
}

for arg in "$@"; do
  case "$arg" in
    --help|-h) usage; exit 0 ;;
    --logs) SELECTIVE=1; DO_LOGS=1; DO_ENGINES=0; DO_MODELS=0; DO_DEPS=0 ;;
    --models) SELECTIVE=1; DO_LOGS=0; DO_ENGINES=0; DO_MODELS=1; DO_DEPS=0 ;;
    --deps) SELECTIVE=1; DO_LOGS=0; DO_ENGINES=0; DO_MODELS=0; DO_DEPS=1 ;;
    --all) SELECTIVE=0; DO_LOGS=1; DO_ENGINES=0; DO_MODELS=1; DO_DEPS=1 ;;
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

if [[ $DO_MODELS -eq 1 ]]; then
  echo "Purging Hugging Face cache at $HUGGINGFACE_CACHE_DIR ..."
  rm -rf "$HUGGINGFACE_CACHE_DIR" || true
  mkdir -p "$HUGGINGFACE_CACHE_DIR"
  echo "Purging Torch cache at $TORCH_CACHE_DIR ..."
  rm -rf "$TORCH_CACHE_DIR" || true
  mkdir -p "$TORCH_CACHE_DIR"
  echo "Purging host models directory at $MODELS_DIR_HOST ..."
  rm -rf "$MODELS_DIR_HOST" || true
  mkdir -p "$MODELS_DIR_HOST"
  # NeMo downloads checkpoints into Hugging Face cache; no local model dir to purge
fi

if [[ $DO_DEPS -eq 1 ]]; then
  echo "Removing virtualenv at $VENV_DIR and pip cache at $PIP_CACHE_DIR ..."
  rm -rf "$VENV_DIR" || true
  rm -rf "$PIP_CACHE_DIR" || true
fi

echo "Done."

# Attempt to exit active virtualenv if running in the same shell (when sourced)
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  # If script is sourced, BASH_SOURCE[0] != $0, so deactivate will affect current shell
  if [[ "${BASH_SOURCE[0]:-}" != "$0" ]]; then
    deactivate 2>/dev/null || true
  else
    echo "NOTE: An active virtualenv was detected. To exit it in your current shell, run: deactivate" >&2
  fi
fi

if [[ $DO_APT_CLEAN -eq 1 ]]; then
  echo "Cleaning apt caches..."
  if command -v apt-get >/dev/null 2>&1; then
    apt-get clean || true
    rm -rf /var/lib/apt/lists/* /var/cache/apt/* || true
  fi
fi

if [[ $DO_UNINSTALL_SYS_PY -eq 1 ]]; then
  echo "Uninstalling heavy system Python packages (global, not venv)..."
  if command -v pip3 >/dev/null 2>&1; then
    pip3 uninstall -y httpx fastapi uvicorn numpy soundfile soxr huggingface_hub || true
  fi
fi

if [[ $DO_DU_REPORT -eq 1 ]]; then
  echo "Disk usage report (top 10):"
  du -h -d 1 /workspace 2>/dev/null | sort -hr | head -n 10 || true
  du -h -d 2 "$HOME/.cache" 2>/dev/null | sort -hr | head -n 10 || true
  du -h -d 1 /usr/local/lib/python3.11/dist-packages 2>/dev/null | sort -hr | head -n 20 || true
fi

