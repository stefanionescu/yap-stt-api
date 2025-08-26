#!/usr/bin/env bash
set -euo pipefail
source ~/.venvs/sensevoice/bin/activate
TARGET="${HOME}/streaming-sensevoice/streaming_sensevoice/streaming_sensevoice.py"

# Patch only if the exact line exists; otherwise bail quietly.
if grep -q "encoder_out, _ = self.model.encoder(speech, speech_lengths)" "$TARGET"; then
  cp "$TARGET" "${TARGET}.bak"
  sed -i -E '
    /encoder_out, _ = self\.model\.encoder\(speech, speech_lengths\)/ {
      i\        import torch
      i\        from contextlib import nullcontext
      i\        _amp = torch.autocast(device_type="cuda", dtype=torch.float16) if "cuda" in str(self.device) else nullcontext()
      i\        with _amp:
    }
  ' "$TARGET"
  echo "[amp] autocast added."
else
  echo "[amp] Skip: target line not found."
fi
