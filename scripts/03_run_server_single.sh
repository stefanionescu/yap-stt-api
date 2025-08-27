#!/usr/bin/env bash
set -euo pipefail

SRV=/opt/sherpa-onnx/build/bin/sherpa-onnx-online-websocket-server
MOD=/opt/sherpa-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20
LOG=/opt/sherpa-logs
mkdir -p "$LOG"

# Important: this CLI expects --key=value format (no spaces).
# Endpointing tuned for ~120–150 ms finalization after trailing silence.
exec "$SRV" \
  --port=8000 \
  --num-work-threads=4 \
  --num-io-threads=2 \
  --tokens="$MOD/tokens.txt" \
  --encoder="$MOD/encoder-epoch-99-avg-1.onnx" \
  --decoder="$MOD/decoder-epoch-99-avg-1.onnx" \
  --joiner="$MOD/joiner-epoch-99-avg-1.onnx" \
  --decoding-method=greedy_search \
  --enable-endpoint=true \
  --rule1-min-trailing-silence=0.12 \
  --rule2-min-trailing-silence=0.15 \
  --rule3-min-trailing-silence=0.00 \
  --max-batch-size=24 \
  --loop-interval-ms=10 \
  --log-file="$LOG/server.log"
