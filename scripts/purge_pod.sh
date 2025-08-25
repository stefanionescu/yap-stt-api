#!/usr/bin/env bash
set -euo pipefail

PORT=${PORT:-8000}
HUGGINGFACE_CACHE_DIR=${HUGGINGFACE_CACHE_DIR:-"$HOME/.cache/huggingface"}
TORCH_CACHE_DIR=${TORCH_CACHE_DIR:-"$HOME/.cache/torch"}
TORCH_EXT_DIR=${TORCH_EXT_DIR:-"$HOME/.cache/torch_extensions"}
NUMBA_CACHE_DIR=${NUMBA_CACHE_DIR:-"$HOME/.cache/numba"}
NEMO_CACHE_DIR=${NEMO_CACHE_DIR:-"$HOME/.cache/nemo"}
NV_COMPUTE_CACHE=${NV_COMPUTE_CACHE:-"$HOME/.nv/ComputeCache"}
PIP_CACHE_DIR=${PIP_CACHE_DIR:-"$HOME/.cache/pip"}
VENV_DIR=${VENV_DIR:-".venv"}
MODELS_DIR_HOST=${MODELS_DIR_HOST:-"models"}
 
# Purge core artifacts by default (no flags needed).
DO_LOGS=1
DO_ENGINES=1
DO_MODELS=1
DO_DEPS=1
DO_REPO=1
DO_APT_CLEAN=1
DO_UNINSTALL_SYS_PY=1
DO_DU_REPORT=1
SELECTIVE=0
DO_UNINSTALL_TRT=0
# Remove system CUDA/toolkit packages via apt-get by default (destructive)
DO_APT_REMOVE_CUDA=1

usage() {
  cat <<EOF
Usage: $0 [--logs] [--models] [--deps] [--repo] [--all]

Stops the gRPC service and purges logs, caches, dependencies, repo bytecode, and local model files.

Defaults: With no flags, purges core artifacts (logs, models, deps, repo bytecode).

Options (for selective purge):
  --logs       Remove logs/ and metrics logs (keeps directory)
  --models     Remove NeMo/Hugging Face caches (~/.cache) and host ./models
  --deps       Remove local Python venv (.venv) and pip cache (~/.cache/pip)
  --repo       Remove repo __pycache__/ *.pyc under src/ and scripts/
  --all        Do all of the above (same as no flags)

Env:
  PORT (default: 8000)
 
  PIP_CACHE_DIR (default: ~/.cache/pip)
  VENV_DIR (default: .venv)
  MODELS_DIR_HOST (default: ./models)
 
 Destructive defaults:
   - Also attempts to uninstall global Python CUDA wheels (cuda, cuda-python, nvidia-*cu11/cu12, etc.)
   - Also attempts to remove system CUDA/toolkit libs via apt-get (cuda-*, nvidia-cuda-toolkit, libcudnn*, etc.)
   - Disable those only by using selective flags that do not include deps, or by editing DO_APT_REMOVE_CUDA
  
EOF
}

for arg in "$@"; do
  case "$arg" in
    --help|-h) usage; exit 0 ;;
    --logs) SELECTIVE=1; DO_LOGS=1; DO_ENGINES=0; DO_MODELS=0; DO_DEPS=0; DO_REPO=0; DO_APT_REMOVE_CUDA=0 ;;
    --models) SELECTIVE=1; DO_LOGS=0; DO_ENGINES=0; DO_MODELS=1; DO_DEPS=0; DO_REPO=0; DO_APT_REMOVE_CUDA=0 ;;
    --deps) SELECTIVE=1; DO_LOGS=0; DO_ENGINES=0; DO_MODELS=0; DO_DEPS=1; DO_REPO=0; DO_APT_REMOVE_CUDA=1 ;;
    --repo) SELECTIVE=1; DO_LOGS=0; DO_ENGINES=0; DO_MODELS=0; DO_DEPS=0; DO_REPO=1; DO_APT_REMOVE_CUDA=0 ;;
    --all) SELECTIVE=0; DO_LOGS=1; DO_ENGINES=0; DO_MODELS=1; DO_DEPS=1; DO_REPO=1; DO_APT_REMOVE_CUDA=1 ;;
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

# Best-effort kill of server processes started via python -m src.server
kill_server_by_pattern() {
  local pids=""
  if command -v pgrep >/dev/null 2>&1; then
    # Match common patterns: python -m src.server or python ... src/server.py
    pids=$(pgrep -f "python .* -m src\\.server|python .*src/server\\.py" || true)
  else
    # Fallback using ps/grep
    pids=$(ps aux | grep -E "python .* -m src\\.server|python .*src/server\\.py" | grep -v grep | awk '{print $2}' || true)
  fi
  if [[ -n "$pids" ]]; then
    echo "Killing server processes by pattern: $pids"
    kill $pids || true
    sleep 1
    for p in $pids; do
      if kill -0 "$p" 2>/dev/null; then kill -9 "$p" || true; fi
    done
  fi
}

echo "Stopping service..."
kill_by_pidfile logs/server.pid
kill_server_by_pattern
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
  echo "Purging Torch extensions at $TORCH_EXT_DIR ..."
  rm -rf "$TORCH_EXT_DIR" || true
  mkdir -p "$TORCH_EXT_DIR"
  echo "Purging NeMo cache at $NEMO_CACHE_DIR ..."
  rm -rf "$NEMO_CACHE_DIR" || true
  mkdir -p "$NEMO_CACHE_DIR"
  echo "Purging NumPy/Numba caches at $NUMBA_CACHE_DIR ..."
  rm -rf "$NUMBA_CACHE_DIR" || true
  mkdir -p "$NUMBA_CACHE_DIR"
  echo "Purging NVIDIA ComputeCache at $NV_COMPUTE_CACHE ..."
  rm -rf "$NV_COMPUTE_CACHE" || true
  mkdir -p "$NV_COMPUTE_CACHE"
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

if [[ $DO_REPO -eq 1 ]]; then
  echo "Removing repo bytecode (__pycache__/ *.pyc) under src/ and scripts/..."
  find src -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
  find scripts -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
  find src -name "*.py[co]" -delete 2>/dev/null || true
  find scripts -name "*.py[co]" -delete 2>/dev/null || true
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
    # Try to remove the heaviest wheels first
    PKGS=(
      torch torchaudio torchvision torchtext triton xformers
      nemo_toolkit nemo_text_processing pytorch_lightning lightning
      onnx onnxruntime onnxruntime-gpu
      transformers sentencepiece datasets accelerate
      librosa scipy numba
      huggingface_hub httpx fastapi uvicorn numpy soundfile soxr
      # CUDA wheels and CUDA-toolkits packaged for pip
      cuda cuda-python \
      nvidia-cublas-cu11 nvidia-cublas-cu12 \
      nvidia-cuda-runtime-cu11 nvidia-cuda-runtime-cu12 \
      nvidia-cudnn-cu11 nvidia-cudnn-cu12 \
      nvidia-cusparse-cu11 nvidia-cusparse-cu12 \
      nvidia-cufft-cu11 nvidia-cufft-cu12 \
      nvidia-curand-cu11 nvidia-curand-cu12 \
      nvidia-cusolver-cu11 nvidia-cusolver-cu12 \
      nvidia-nvjitlink-cu12 tensorrt
    )
    # Uninstall in multiple passes to handle dependency ordering
    for i in 1 2; do
      pip3 uninstall -y "${PKGS[@]}" || true
    done
    # Dynamically uninstall any leftover nvidia-* CUDA wheels
    EXTRA=$(pip3 list --format=freeze | awk -F'=' '{print $1}' | grep -E '^(cuda|cuda-python|nvidia-.*cu(11|12)|nvidia-.*cuda|nvidia-.*cudnn|nvidia-.*nvjitlink|tensorrt)$' || true)
    if [[ -n "$EXTRA" ]]; then
      echo "Uninstalling detected CUDA-related wheels: $EXTRA"
      pip3 uninstall -y $EXTRA || true
    fi
    # Purge pip cache as well
    pip3 cache purge || true
  fi
fi

if [[ $DO_APT_REMOVE_CUDA -eq 1 ]]; then
  echo "Removing system CUDA/toolkit packages via apt-get (destructive)..."
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive

    # Helper: remove only currently installed packages matching patterns
    apt_remove_installed() {
      local patterns=("$@")
      local to_remove=()
      local pat names
      for pat in "${patterns[@]}"; do
        names=$(dpkg -l "$pat" 2>/dev/null | awk '/^ii/ {print $2}')
        if [[ -n "$names" ]]; then
          while IFS= read -r n; do
            # de-duplicate
            if [[ -n "$n" && ! " ${to_remove[*]} " =~ " $n " ]]; then
              to_remove+=("$n")
            fi
          done <<< "$names"
        fi
      done
      if [[ ${#to_remove[@]} -gt 0 ]]; then
        echo "Purging: ${to_remove[*]}"
        apt-get remove -y --purge --allow-change-held-packages "${to_remove[@]}" || true
      fi
    }

    apt_remove_installed \
      'cuda-*' 'nvidia-cuda-toolkit' 'nvidia-cuda-runtime*' \
      'cuda-compat-*' 'cuda-drivers*' \
      'libcudart*' 'libcudnn*' 'libnvinfer*' 'libcublas*' 'libcurand*' 'libcusolver*' 'libcusparse*' 'libcufft*' \
      'libnvjitlink*' 'libnvfatbin*' 'libnvjpeg*' 'libnpp*' 'libcufile*' 'cuda-keyring'

    apt-get autoremove -y --purge || true
    apt-get clean || true
    rm -rf /var/lib/apt/lists/* /var/cache/apt/* || true
  fi
  # Remove common CUDA install directories if present
  rm -rf /usr/local/cuda* /usr/local/nvidia /opt/nvidia 2>/dev/null || true
fi

if [[ $DO_DU_REPORT -eq 1 ]]; then
  echo "Disk usage report (top 10):"
  du -h -d 1 . 2>/dev/null | sort -hr | head -n 10 || true
  du -h -d 2 "$HOME/.cache" 2>/dev/null | sort -hr | head -n 10 || true
  if command -v python3 >/dev/null 2>&1; then
    PY_BASE=$(python3 -c 'import sys,site; import os; print(os.path.dirname(site.getsitepackages()[0]))' 2>/dev/null || echo "/usr/local/lib/python3.11")
    du -h -d 1 "$PY_BASE" 2>/dev/null | sort -hr | head -n 20 || true
  fi
fi

