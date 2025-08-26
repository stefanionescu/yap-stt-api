#!/usr/bin/env bash
set -euo pipefail
source ~/.venvs/sensevoice/bin/activate
cd "${HOME}/streaming-sensevoice"

cat > /tmp/_warmup_gpu.py <<'PY'
from streaming_sensevoice.streaming_sensevoice import StreamingSenseVoice
m = StreamingSenseVoice(model="iic/SenseVoiceSmall", device="cuda:0")
print("Loaded on:", m.device)
PY

python /tmp/_warmup_gpu.py
echo "[warmup] Done (GPU)."
