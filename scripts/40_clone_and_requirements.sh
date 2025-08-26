#!/usr/bin/env bash
set -euo pipefail
source ~/.venvs/sensevoice/bin/activate

REPO_DIR="${HOME}/streaming-sensevoice"
if [ ! -d "$REPO_DIR" ]; then
  git clone https://github.com/pengzhendong/streaming-sensevoice.git "$REPO_DIR"
else
  git -C "$REPO_DIR" pull --ff-only
fi
cd "$REPO_DIR"

pip install -r requirements.txt
pip install fastapi uvicorn pydantic-settings loguru
pip install modelscope huggingface_hub
