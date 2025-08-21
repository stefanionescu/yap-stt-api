#!/usr/bin/env bash
set -euo pipefail

# Downloads Parakeet TDT 0.6B v2 INT8 ONNX artifacts from Hugging Face and
# places them under PARAKEET_MODEL_DIR, renaming to encoder-model.onnx and
# decoder_joint-model.onnx so the service can load them directly.
#
# Env:
#   PARAKEET_INT8_REPO   (default: istupakov/parakeet-tdt-0.6b-v2-onnx)
#   PARAKEET_MODEL_DIR   (required)
#   HF_TOKEN             (optional, for private/ratelimited pulls)

REPO=${PARAKEET_INT8_REPO:-istupakov/parakeet-tdt-0.6b-v2-onnx}
TARGET_DIR=${PARAKEET_MODEL_DIR:-}
FORCE=${FORCE_FETCH_INT8:-0}

# Prefer project venv Python if present; otherwise use system python3
if [[ -z "${PY:-}" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    PY=".venv/bin/python"
  else
    PY="$(command -v python3 || command -v python)"
  fi
fi

if [[ -z "${TARGET_DIR}" ]]; then
  echo "ERROR: PARAKEET_MODEL_DIR is not set" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

# Idempotent: if target files exist and not forcing, skip
if [[ "${FORCE}" != "1" ]] && [[ -f "${TARGET_DIR}/encoder-model.onnx" && -f "${TARGET_DIR}/decoder_joint-model.onnx" && -f "${TARGET_DIR}/vocab.txt" ]]; then
  echo "INT8 artifacts already present in ${TARGET_DIR}. Skipping download. (Set FORCE_FETCH_INT8=1 to refetch)"
  exit 0
fi

echo "Fetching INT8 ONNX artifacts from ${REPO} -> ${TARGET_DIR}"

# Ensure huggingface_hub is available for the chosen Python
if ! "${PY}" -c "import huggingface_hub" >/dev/null 2>&1; then
  echo "Installing huggingface_hub for ${PY}..."
  "${PY}" -m pip install --upgrade huggingface_hub >/dev/null
fi

"${PY}" - "$REPO" "$TARGET_DIR" <<'PY'
import os, sys, shutil
from pathlib import Path
from huggingface_hub import hf_hub_download

repo = sys.argv[1]
target_dir = Path(sys.argv[2])
target_dir.mkdir(parents=True, exist_ok=True)

files = [
    ("encoder-model.int8.onnx", "encoder-model.onnx"),
    ("decoder_joint-model.int8.onnx", "decoder_joint-model.onnx"),
    ("vocab.txt", "vocab.txt"),
]

token = os.getenv("HF_TOKEN")
downloaded = []
for src, dst in files:
    path = hf_hub_download(repo_id=repo, filename=src, token=token)
    out = target_dir / dst
    shutil.copyfile(path, out)
    downloaded.append((src, str(out)))

print("Downloaded:")
for src, out in downloaded:
    print(f"  {src} -> {out}")
PY

echo "Done. INT8 models are ready at ${TARGET_DIR}"

