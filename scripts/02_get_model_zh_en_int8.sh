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

# Optional test audio
mkdir -p test_wavs
wget -q --show-progress -O test_wavs/0.wav                     "$BASE/test_wavs/0.wav" || true
wget -q --show-progress -O test_wavs/4.wav                     "$BASE/test_wavs/4.wav" || true

echo "Model ready at $ROOT"
