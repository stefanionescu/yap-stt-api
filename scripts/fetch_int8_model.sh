#!/usr/bin/env bash
set -euo pipefail

export PARAKEET_MODEL_DIR=${PARAKEET_MODEL_DIR:-/models/parakeet-int8}
export HF_REPO_ID=${HF_REPO_ID:-"istupakov/parakeet-tdt-0.6b-v2-onnx"}
export HF_REVISION=${HF_REVISION:-"main"}
# Optional: export HF_TOKEN for auth; huggingface-cli will pick it up

mkdir -p "$PARAKEET_MODEL_DIR"

need_download=0
for f in encoder-model.onnx decoder_joint-model.onnx vocab.txt config.json; do
  if [[ ! -s "$PARAKEET_MODEL_DIR/$f" ]]; then
    need_download=1
    break
  fi
done

if [[ "$need_download" -eq 0 ]]; then
  echo "INT8 model already present at $PARAKEET_MODEL_DIR"
  exit 0
fi

echo "Fetching INT8 artifacts from $HF_REPO_ID@$HF_REVISION into $PARAKEET_MODEL_DIR ..."

if command -v huggingface-cli >/dev/null 2>&1; then
  # Download to temp then rename to standardized filenames
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  huggingface-cli download "$HF_REPO_ID" --revision "$HF_REVISION" \
    --local-dir "$tmpdir" --local-dir-use-symlinks False \
    encoder-model.int8.onnx decoder_joint-model.int8.onnx vocab.txt || true
  # Move/rename
  mv -f "$tmpdir/encoder-model.int8.onnx" "$PARAKEET_MODEL_DIR/encoder-model.onnx" 2>/dev/null || true
  mv -f "$tmpdir/decoder_joint-model.int8.onnx" "$PARAKEET_MODEL_DIR/decoder_joint-model.onnx" 2>/dev/null || true
  mv -f "$tmpdir/vocab.txt" "$PARAKEET_MODEL_DIR/vocab.txt" 2>/dev/null || true
  # config.json optional
  if huggingface-cli download "$HF_REPO_ID" --revision "$HF_REVISION" --local-dir "$tmpdir" --local-dir-use-symlinks False config.json; then
    mv -f "$tmpdir/config.json" "$PARAKEET_MODEL_DIR/config.json"
  else
    echo '{"sample_rate":16000,"n_mels":80}' > "$PARAKEET_MODEL_DIR/config.json"
  fi
else
  echo "huggingface-cli not found; falling back to curl." >&2
  base="https://huggingface.co/$HF_REPO_ID/resolve/$HF_REVISION"
  curl_opts=( -L --fail --retry 10 --retry-all-errors --retry-delay 2 --http1.1 -C - )
  if [[ -n "${HF_TOKEN:-}" ]]; then
    curl_opts+=( -H "Authorization: Bearer $HF_TOKEN" )
  fi
  curl "${curl_opts[@]}" "$base/encoder-model.int8.onnx" -o "$PARAKEET_MODEL_DIR/encoder-model.onnx"
  curl "${curl_opts[@]}" "$base/decoder_joint-model.int8.onnx" -o "$PARAKEET_MODEL_DIR/decoder_joint-model.onnx"
  curl "${curl_opts[@]}" "$base/vocab.txt" -o "$PARAKEET_MODEL_DIR/vocab.txt"
  if ! curl "${curl_opts[@]}" "$base/config.json" -o "$PARAKEET_MODEL_DIR/config.json"; then
    echo '{"sample_rate":16000,"n_mels":80}' > "$PARAKEET_MODEL_DIR/config.json"
  fi
fi

echo "INT8 model prepared at $PARAKEET_MODEL_DIR"
