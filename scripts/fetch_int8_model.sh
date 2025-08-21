#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR=${PARAKEET_MODEL_DIR:-/models/parakeet-int8}
HF_REPO=${HF_REPO:-"https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx/resolve/main"}

mkdir -p "$MODEL_DIR"

need_download=0
for f in encoder-model.onnx decoder_joint-model.onnx vocab.txt config.json; do
  if [[ ! -f "$MODEL_DIR/$f" ]]; then
    need_download=1
    break
  fi
done

if [[ "$need_download" -eq 0 ]]; then
  echo "INT8 model already present at $MODEL_DIR"
  exit 0
fi

echo "Fetching INT8 artifacts into $MODEL_DIR ..."
curl -L "$HF_REPO/encoder-model.int8.onnx" -o "$MODEL_DIR/encoder-model.onnx"
curl -L "$HF_REPO/decoder_joint-model.int8.onnx" -o "$MODEL_DIR/decoder_joint-model.onnx"
curl -L "$HF_REPO/vocab.txt" -o "$MODEL_DIR/vocab.txt"
# config.json may not exist or may be optional; create minimal if missing
if ! curl -fL "$HF_REPO/config.json" -o "$MODEL_DIR/config.json"; then
  echo '{"sample_rate":16000,"n_mels":80}' > "$MODEL_DIR/config.json"
fi

echo "INT8 model prepared at $MODEL_DIR"
