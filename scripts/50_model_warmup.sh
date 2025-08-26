#!/usr/bin/env bash
set -euo pipefail
source ~/.venvs/sensevoice/bin/activate

# Make the repo importable
export PYTHONPATH="${HOME}/streaming-sensevoice:${PYTHONPATH:-}"
cd "${HOME}/streaming-sensevoice"

cat > /tmp/_warmup_gpu.py <<'PY'
import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

def load(model_id):
    from streaming_sensevoice.streaming_sensevoice import StreamingSenseVoice
    m = StreamingSenseVoice(model=model_id, device="cuda:0")
    print("Loaded:", model_id, "on", m.device)
    return m

try:
    m = load("iic/SenseVoiceSmall")  # ModelScope
except Exception as e:
    print("ModelScope failed:", e)
    m = load("FunAudioLLM/SenseVoiceSmall")  # HF mirror
PY

python /tmp/_warmup_gpu.py
echo "[warmup] Done (GPU)."
