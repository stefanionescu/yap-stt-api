#!/usr/bin/env bash
set -euo pipefail

# Downloads Parakeet TDT 0.6B v2 FP32 ONNX artifacts (with external data)
# into PARAKEET_MODEL_DIR. Keeps filenames as encoder-model.onnx (+ .data),
# decoder_joint-model.onnx, vocab.txt, and config.json.
#
# Env:
#   PARAKEET_FP32_REPO  (default: istupakov/parakeet-tdt-0.6b-v2-onnx)
#   PARAKEET_MODEL_DIR  (required)
#   HF_TOKEN            (optional)

# Try to source default environment to populate PARAKEET_MODEL_DIR and others
if [[ -z "${PARAKEET_MODEL_DIR:-}" || -z "${PARAKEET_FP32_REPO:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "${SCRIPT_DIR}/env.sh" ]]; then
    # shellcheck disable=SC1090
    source "${SCRIPT_DIR}/env.sh"
  fi
fi

REPO=${PARAKEET_FP32_REPO:-istupakov/parakeet-tdt-0.6b-v2-onnx}
TARGET_DIR=${PARAKEET_MODEL_DIR:-}
FORCE=${FORCE_FETCH_FP32:-0}

if [[ -z "${TARGET_DIR}" ]]; then
  echo "ERROR: PARAKEET_MODEL_DIR is not set" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

# If artifacts already present and not forcing, exit early
if [[ "${FORCE}" != "1" ]] && [[ -f "${TARGET_DIR}/encoder-model.onnx" && -f "${TARGET_DIR}/encoder-model.onnx.data" && -f "${TARGET_DIR}/decoder_joint-model.onnx" && -f "${TARGET_DIR}/vocab.txt" && -f "${TARGET_DIR}/config.json" ]]; then
  echo "FP32 artifacts already present in ${TARGET_DIR}. Skipping download. (Set FORCE_FETCH_FP32=1 to refetch)"
  exit 0
fi

# Choose python
if [[ -z "${PY:-}" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    PY=".venv/bin/python"
  else
    PY="$(command -v python3 || command -v python)"
  fi
fi

# Ensure huggingface_hub is available
if ! "${PY}" -c "import huggingface_hub" >/dev/null 2>&1; then
  echo "Installing huggingface_hub for ${PY}..."
  "${PY}" -m pip install --upgrade huggingface_hub >/dev/null
fi

echo "Fetching FP32 ONNX artifacts from ${REPO} -> ${TARGET_DIR}"

"${PY}" - "$REPO" "$TARGET_DIR" <<'PY'
import os, sys, shutil
from pathlib import Path
from huggingface_hub import hf_hub_download

repo = sys.argv[1]
dst = Path(sys.argv[2])
dst.mkdir(parents=True, exist_ok=True)

files = [
    ("encoder-model.onnx", "encoder-model.onnx"),
    ("encoder-model.onnx.data", "encoder-model.onnx.data"),
    ("decoder_joint-model.onnx", "decoder_joint-model.onnx"),
    ("vocab.txt", "vocab.txt"),
    ("config.json", "config.json"),
]

token = os.getenv("HF_TOKEN")
for src, tgt in files:
    p = hf_hub_download(repo_id=repo, filename=src, token=token)
    shutil.copyfile(p, dst / tgt)

print("FP32 artifacts ready in:", dst)
PY

ls -lh "${TARGET_DIR}" || true
echo "Done. FP32 models are ready at ${TARGET_DIR}"


