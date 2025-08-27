#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/sherpa-models
mkdir -p "$ROOT" && cd "$ROOT"

# Download the full model package (includes both FP32 and INT8 versions)
echo "Downloading Sherpa-ONNX bilingual model..."
wget -q --show-progress "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2"

echo "Extracting model..."
tar xf sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2
rm sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2

# Verify model files are present
MODEL_DIR="$ROOT/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
if [ ! -f "$MODEL_DIR/encoder-epoch-99-avg-1.onnx" ] || [ ! -f "$MODEL_DIR/decoder-epoch-99-avg-1.onnx" ] || [ ! -f "$MODEL_DIR/joiner-epoch-99-avg-1.onnx" ]; then
    echo "❌ Error: Required model files not found after extraction"
    exit 1
fi

echo "✓ Model files verified:"
ls -lh "$MODEL_DIR"/*.onnx | head -3

echo ""
echo "Model ready at $MODEL_DIR"
