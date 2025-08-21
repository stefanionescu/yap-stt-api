#!/usr/bin/env bash
set -euo pipefail

PY=${PY:-python3}
VENV=.venv

$PY -m venv $VENV
source $VENV/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Load default environment
source scripts/env.sh

echo "Venv ready. Activate with: source $VENV/bin/activate"
