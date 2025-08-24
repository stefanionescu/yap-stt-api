#!/usr/bin/env bash
set -euo pipefail

PY=${PY:-python3}
VENV=.venv

$PY -m venv $VENV
source $VENV/bin/activate
pip install --upgrade pip
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 || true
pip install -r requirements.txt

echo "Venv ready. Activate with: source $VENV/bin/activate"
