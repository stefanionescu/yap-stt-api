#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/sherpa-models/zh-en-zipformer-2023-02-20
mkdir -p "$ROOT" && cd "$ROOT"

BASE="https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/resolve/main"

# Required files (INT8 encoder/joiner + FP decoder)
wget -q --show-progress -O tokens.txt                          "$BASE/tokens.txt"
wget -q --show-progress -O encoder-epoch-99-avg-1.int8.onnx    "$BASE/encoder-epoch-99-avg-1.int8.onnx"
wget -q --show-progress -O decoder-epoch-99-avg-1.onnx         "$BASE/decoder-epoch-99-avg-1.onnx"
wget -q --show-progress -O joiner-epoch-99-avg-1.int8.onnx     "$BASE/joiner-epoch-99-avg-1.int8.onnx"

# Optional test audio (these may fail to download - not critical)
mkdir -p test_wavs
echo "Downloading test audio files (optional)..."
wget -q --show-progress -O test_wavs/0.wav "$BASE/test_wavs/0.wav" || echo "  ⚠ test_wavs/0.wav download failed"
wget -q --show-progress -O test_wavs/4.wav "$BASE/test_wavs/4.wav" || echo "  ⚠ test_wavs/4.wav download failed"

# Verify downloaded files
for wav in test_wavs/*.wav; do
    if [ -f "$wav" ]; then
        # Check if file is a valid WAV (has RIFF header)
        if ! head -c 4 "$wav" 2>/dev/null | grep -q "RIFF"; then
            echo "  ⚠ $wav appears corrupted, removing"
            rm -f "$wav"
        fi
    fi
done

echo "Model ready at $ROOT"
