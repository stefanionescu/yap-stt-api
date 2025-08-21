#!/usr/bin/env bash
set -euo pipefail

PORT=${PORT:-8000}
TRT_ENGINE_CACHE=${TRT_ENGINE_CACHE:-/models/trt_cache}
TRT_TIMING_CACHE=${TRT_TIMING_CACHE:-/models/timing.cache}
ONNX_ASR_CACHE_DIR=${ONNX_ASR_CACHE_DIR:-"$HOME/.cache/onnx-asr"}
ONNXRUNTIME_CACHE_DIR=${ONNXRUNTIME_CACHE_DIR:-"$HOME/.cache/onnxruntime"}
HUGGINGFACE_CACHE_DIR=${HUGGINGFACE_CACHE_DIR:-"$HOME/.cache/huggingface"}
TORCH_CACHE_DIR=${TORCH_CACHE_DIR:-"$HOME/.cache/torch"}
PIP_CACHE_DIR=${PIP_CACHE_DIR:-"$HOME/.cache/pip"}
VENV_DIR=${VENV_DIR:-".venv"}
MODELS_DIR_HOST=${MODELS_DIR_HOST:-"models"}
PARAKEET_MODEL_DIR=${PARAKEET_MODEL_DIR:-"/models/parakeet-int8"}

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
Usage: $0 [--logs] [--engines] [--models] [--deps] [--all] [--uninstall-trt]

Stops the FastAPI service and purges logs, caches, dependencies, and local model files.

Defaults: With no flags, purges core artifacts (logs, engines, models, deps).

Options (for selective purge):
  --logs       Remove logs/ and metrics logs (keeps directory)
  --engines    Remove TensorRT engine & timing caches (TRT_ENGINE_CACHE, TRT_TIMING_CACHE)
  --models     Remove onnx-asr model cache (~/.cache/onnx-asr), host ./models, and PARAKEET_MODEL_DIR
  --deps       Remove local Python venv (.venv) and pip cache (~/.cache/pip)
  --all        Do all of the above (same as no flags)

Additional:
  --uninstall-trt     Uninstall TensorRT wheels and remove linked libs (requires write perms)

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
    --all) SELECTIVE=0; DO_LOGS=1; DO_ENGINES=1; DO_MODELS=1; DO_DEPS=1 ;;
    --uninstall-trt) DO_UNINSTALL_TRT=1 ;;
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
  echo "Purging ONNX Runtime cache at $ONNXRUNTIME_CACHE_DIR ..."
  rm -rf "$ONNXRUNTIME_CACHE_DIR" || true
  mkdir -p "$ONNXRUNTIME_CACHE_DIR"
  echo "Purging Hugging Face cache at $HUGGINGFACE_CACHE_DIR ..."
  rm -rf "$HUGGINGFACE_CACHE_DIR" || true
  mkdir -p "$HUGGINGFACE_CACHE_DIR"
  echo "Purging Torch cache at $TORCH_CACHE_DIR ..."
  rm -rf "$TORCH_CACHE_DIR" || true
  mkdir -p "$TORCH_CACHE_DIR"
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

# Attempt to exit active virtualenv if running in the same shell (when sourced)
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  # If script is sourced, BASH_SOURCE[0] != $0, so deactivate will affect current shell
  if [[ "${BASH_SOURCE[0]:-}" != "$0" ]]; then
    deactivate 2>/dev/null || true
  else
    echo "NOTE: An active virtualenv was detected. To exit it in your current shell, run: deactivate" >&2
  fi
fi

if [[ $DO_UNINSTALL_TRT -eq 1 ]]; then
  echo "Uninstalling TensorRT wheels and removing linker configs..."
  if command -v python3 >/dev/null 2>&1; then
    python3 -m pip uninstall -y tensorrt-cu12 tensorrt_cu12_libs tensorrt_cu12_bindings || true
  fi
  # Remove ld.so config entries created by scripts/install_trt.sh
  rm -f /etc/ld.so.conf.d/tensorrt-wheel.conf 2>/dev/null || true
  ldconfig 2>/dev/null || true
  # Best-effort removal of cached wheel contents under site-packages
  python3 - <<'PY'
import sysconfig, glob, shutil, os
roots = [p for k,p in sysconfig.get_paths().items() if k in ("purelib","platlib") and p]
names = ("tensorrt_cu12_libs", "tensorrt_cu12_bindings", "tensorrt")
for root in roots:
    for nm in names:
        for path in glob.glob(os.path.join(root, nm+"*")):
            try:
                if os.path.isdir(path): shutil.rmtree(path)
                elif os.path.isfile(path): os.remove(path)
            except Exception:
                pass
print("[purge] TRT wheels removed from site-packages (best effort)")
PY
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
    pip3 uninstall -y onnxruntime-gpu onnxruntime onnx httpx fastapi uvicorn numpy soundfile soxr huggingface_hub || true
  fi
fi

if [[ $DO_DU_REPORT -eq 1 ]]; then
  echo "Disk usage report (top 10):"
  du -h -d 1 /workspace 2>/dev/null | sort -hr | head -n 10 || true
  du -h -d 2 "$HOME/.cache" 2>/dev/null | sort -hr | head -n 10 || true
  du -h -d 1 /usr/local/lib/python3.11/dist-packages 2>/dev/null | sort -hr | head -n 20 || true
fi

