#!/usr/bin/env bash
set -euo pipefail
source ~/.venvs/sensevoice/bin/activate
pip install --index-url https://download.pytorch.org/whl/cu121 \
  torch==2.3.1+cu121 torchvision==0.18.1+cu121 torchaudio==2.3.1+cu121
python - <<'PY'
import torch
print("CUDA avail:", torch.cuda.is_available(), "Device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A")
PY
