#!/usr/bin/env bash
set -euo pipefail
python3 -m venv ~/.venvs/sensevoice
source ~/.venvs/sensevoice/bin/activate
python -m pip install --upgrade pip wheel setuptools
