#!/usr/bin/env bash
set -euo pipefail

export PARAKEET_MODEL_DIR=${PARAKEET_MODEL_DIR:-/models/parakeet-int8}
export HF_REPO_ID=${HF_REPO_ID:-"istupakov/parakeet-tdt-0.6b-v2-onnx"}
export HF_REVISION=${HF_REVISION:-"main"}
# Optional: export HF_TOKEN for auth; huggingface-cli and curl will pick it up

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

have_cli=0
if command -v huggingface-cli >/dev/null 2>&1; then
  have_cli=1
fi

fallback_curl() {
  echo "Falling back to curl downloads..." >&2
  local base="https://huggingface.co/$HF_REPO_ID/resolve/$HF_REVISION"
  local curl_opts=( -L --fail --retry 10 --retry-all-errors --retry-delay 2 --http1.1 -C - )
  if [[ -n "${HF_TOKEN:-}" ]]; then
    curl_opts+=( -H "Authorization: Bearer $HF_TOKEN" )
  fi
  curl "${curl_opts[@]}" "$base/encoder-model.int8.onnx" -o "$PARAKEET_MODEL_DIR/encoder-model.onnx"
  curl "${curl_opts[@]}" "$base/decoder_joint-model.int8.onnx" -o "$PARAKEET_MODEL_DIR/decoder_joint-model.onnx"
  curl "${curl_opts[@]}" "$base/vocab.txt" -o "$PARAKEET_MODEL_DIR/vocab.txt"
  if ! curl "${curl_opts[@]}" "$base/config.json" -o "$PARAKEET_MODEL_DIR/config.json"; then
    echo '{"sample_rate":16000,"n_mels":80}' > "$PARAKEET_MODEL_DIR/config.json"
  fi
}

if [[ $have_cli -eq 1 ]]; then
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  set +e
  huggingface-cli download "$HF_REPO_ID" \
    --revision "$HF_REVISION" \
    --local-dir "$tmpdir" \
    --local-dir-use-symlinks False \
    --include "encoder-model.int8.onnx" \
              "decoder_joint-model.int8.onnx" \
              "vocab.txt" \
              "config.json"
  status=$?
  set -e
  if [[ $status -ne 0 ]]; then
    echo "huggingface-cli download failed with status $status" >&2
    fallback_curl
  else
    # Move/standardize filenames if present
    [[ -f "$tmpdir/encoder-model.int8.onnx" ]] && mv -f "$tmpdir/encoder-model.int8.onnx" "$PARAKEET_MODEL_DIR/encoder-model.onnx"
    [[ -f "$tmpdir/decoder_joint-model.int8.onnx" ]] && mv -f "$tmpdir/decoder_joint-model.int8.onnx" "$PARAKEET_MODEL_DIR/decoder_joint-model.onnx"
    [[ -f "$tmpdir/vocab.txt" ]] && mv -f "$tmpdir/vocab.txt" "$PARAKEET_MODEL_DIR/vocab.txt"
    if [[ -f "$tmpdir/config.json" ]]; then
      mv -f "$tmpdir/config.json" "$PARAKEET_MODEL_DIR/config.json"
    else
      echo '{"sample_rate":16000,"n_mels":80}' > "$PARAKEET_MODEL_DIR/config.json"
    fi
  fi
else
  fallback_curl
fi

# Final verify
if [[ ! -s "$PARAKEET_MODEL_DIR/encoder-model.onnx" || ! -s "$PARAKEET_MODEL_DIR/decoder_joint-model.onnx" || ! -s "$PARAKEET_MODEL_DIR/vocab.txt" ]]; then
  echo "INT8 model files missing after download. Check connectivity or set HF_TOKEN." >&2
  exit 1
fi

echo "INT8 model prepared at $PARAKEET_MODEL_DIR"
