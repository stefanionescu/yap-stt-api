#!/usr/bin/env bash
set -euo pipefail
source ~/.venvs/sensevoice/bin/activate
python - <<'PY'
import sys, torch
assert torch.cuda.is_available(), "CUDA not available"
print("GPU:", torch.cuda.get_device_name(0))
PY
